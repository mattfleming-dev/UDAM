from __future__ import annotations

import io
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import Image, ExifTags

try:
    import rawpy as _rawpy
except Exception:  # pragma: no cover
    _rawpy = None


EXIF_TAG_NAMES = {key: value for key, value in ExifTags.TAGS.items()}

XMP_NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
}

for prefix, uri in XMP_NS.items():
    ET.register_namespace(prefix, uri)


class ExifEngine:
    def __init__(self, exiftool_path: str | None = None) -> None:
        self.exiftool_path = exiftool_path

    def extract_metadata(self, image_path: str) -> dict[str, Any]:
        path = Path(image_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        payload: dict[str, Any] = {}
        is_raw = path.suffix.lower() in {".cr2", ".cr3", ".nef", ".arw", ".raf", ".dng"}

        exiftool_data = self._extract_with_exiftool(path)
        if exiftool_data:
            payload.update(exiftool_data)

        if is_raw and _rawpy is not None:
            # Handle RAW files with rawpy
            try:
                raw = _rawpy.imread(str(path))
                payload.setdefault("width", raw.sizes.width)
                payload.setdefault("height", raw.sizes.height)
                payload.setdefault("format", "RAW")
                # Extract basic EXIF from metadata if available
                if hasattr(raw, "metadata"):
                    meta = raw.metadata
                    payload.setdefault("camera_make", getattr(meta, "make", "") or "")
                    payload.setdefault("camera_model", getattr(meta, "model", "") or "")
                    payload.setdefault("iso", getattr(meta, "iso_speed", "") or "")
                    payload.setdefault("aperture", getattr(meta, "aperture", "") or "")
                    payload.setdefault("focal_length", getattr(meta, "focal_length", "") or "")
                    payload.setdefault("shutter_speed", getattr(meta, "shutter_speed", "") or "")
                payload.setdefault("exif", {})
            except Exception as exc:
                # RAW extraction failed, use safe defaults
                payload.setdefault("width", 0)
                payload.setdefault("height", 0)
                payload.setdefault("format", "RAW")
                payload.setdefault("camera_make", "")
                payload.setdefault("camera_model", "")
                payload.setdefault("iso", "")
                payload.setdefault("aperture", "")
                payload.setdefault("focal_length", "")
                payload.setdefault("shutter_speed", "")
                payload.setdefault("exif", {})
        else:
            # Standard image handling with PIL
            try:
                with Image.open(path) as img:
                    payload.setdefault("width", img.width)
                    payload.setdefault("height", img.height)
                    payload.setdefault("format", img.format)

                    exif_data = img.getexif()
                    parsed = {}
                    for tag_id, value in exif_data.items():
                        name = EXIF_TAG_NAMES.get(tag_id, str(tag_id))
                        parsed[name] = self._serialize_exif_value(value)
                    if parsed:
                        payload["exif"] = parsed

                    payload.setdefault("camera_make", parsed.get("Make", ""))
                    payload.setdefault("camera_model", parsed.get("Model", ""))
                    payload.setdefault("lens", parsed.get("LensModel", ""))
                    payload.setdefault("iso", parsed.get("ISOSpeedRatings", ""))
                    payload.setdefault("aperture", parsed.get("FNumber", ""))
                    payload.setdefault("focal_length", parsed.get("FocalLength", ""))
                    payload.setdefault("shutter_speed", parsed.get("ExposureTime", ""))
            except Exception:
                # Fallback for unsupported formats
                payload.setdefault("width", 0)
                payload.setdefault("height", 0)
                payload.setdefault("format", path.suffix.upper())
                payload.setdefault("camera_make", "")
                payload.setdefault("camera_model", "")
                payload.setdefault("lens", "")
                payload.setdefault("iso", "")
                payload.setdefault("aperture", "")
                payload.setdefault("focal_length", "")
                payload.setdefault("shutter_speed", "")
                payload.setdefault("exif", {})

        sidecar = self.read_xmp_sidecar(path)
        if sidecar:
            payload["xmp"] = sidecar
            payload["title"] = sidecar.get("title") or payload.get("title", "")
            payload["keywords"] = sidecar.get("keywords") or payload.get("keywords", [])
            payload["source_path"] = sidecar.get("source_path", "")

        return payload

    def _extract_with_exiftool(self, path: Path) -> dict[str, Any]:
        executable = self.exiftool_path or shutil.which("exiftool")
        if not executable:
            return {}

        try:
            result = subprocess.run(
                [executable, "-j", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return {}

        if result.returncode != 0:
            return {}

        try:
            rows = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}

        if not rows:
            return {}

        row = rows[0] if isinstance(rows[0], dict) else {}
        normalized = self._normalize_exiftool_row(row)
        payload: dict[str, Any] = {}
        if normalized.get("width"):
            payload["width"] = normalized["width"]
        if normalized.get("height"):
            payload["height"] = normalized["height"]
        if normalized.get("format"):
            payload["format"] = normalized["format"]
        if normalized.get("camera_make"):
            payload["camera_make"] = normalized["camera_make"]
        if normalized.get("camera_model"):
            payload["camera_model"] = normalized["camera_model"]
        if normalized.get("lens"):
            payload["lens"] = normalized["lens"]
        if normalized.get("iso"):
            payload["iso"] = normalized["iso"]
        if normalized.get("aperture"):
            payload["aperture"] = normalized["aperture"]
        if normalized.get("focal_length"):
            payload["focal_length"] = normalized["focal_length"]
        if normalized.get("shutter_speed"):
            payload["shutter_speed"] = normalized["shutter_speed"]
        if row:
            payload["exif"] = normalized
        return payload

    @staticmethod
    def _normalize_exiftool_row(row: dict[str, Any]) -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, value in row.items():
            text_key = str(key)
            short_key = text_key.split(":", 1)[-1]
            flattened[text_key.lower()] = value
            flattened[short_key.lower()] = value

        def pick(*names: str) -> Any:
            for name in names:
                value = flattened.get(name.lower())
                if value not in (None, "", []):
                    return value
            return ""

        return {
            "width": pick("ImageWidth", "ExifImageWidth", "SourceImageWidth"),
            "height": pick("ImageHeight", "ExifImageHeight", "SourceImageHeight"),
            "format": pick("FileType", "MIMEType"),
            "camera_make": pick("Make"),
            "camera_model": pick("Model"),
            "lens": pick("LensModel", "Lens"),
            "iso": pick("ISO", "ISOSpeedRatings", "PhotographicSensitivity"),
            "aperture": pick("FNumber", "Aperture"),
            "focal_length": pick("FocalLength"),
            "shutter_speed": pick("ExposureTime", "ShutterSpeed"),
        }

    def write_stock_metadata(
        self,
        target_jpeg_path: str,
        source_raw_path: str,
        title: str,
        keywords: list[str],
    ) -> dict[str, object]:
        target_path = Path(target_jpeg_path).expanduser().resolve()
        source_path = Path(source_raw_path).expanduser().resolve()

        if not target_path.exists():
            raise FileNotFoundError(f"Target JPEG not found: {target_path}")
        if not source_path.exists():
            raise FileNotFoundError(f"Source RAW not found: {source_path}")

        normalized_title = self._normalize_title(title)
        normalized_keywords = self._normalize_keywords(keywords)

        payload: dict[str, object] = {
            "XMP:Headline": normalized_title,
            "IPTC:Headline": normalized_title,
            "XMP:Description": normalized_title,
            "EXIF:ImageDescription": normalized_title,
            "XMP:Subject": normalized_keywords,
            "IPTC:Keywords": normalized_keywords,
            "XMP:Source": str(source_path),
        }

        if ExifToolHelper is None:
            self.write_xmp_sidecar(target_path, normalized_title, normalized_keywords, str(source_path))
            return {
                "target": str(target_path),
                "source": str(source_path),
                "title": normalized_title,
                "keywords": normalized_keywords,
            }

        helper_kwargs = {}
        if self.exiftool_path:
            helper_kwargs["executable"] = self.exiftool_path

        with ExifToolHelper(**helper_kwargs) as et:
            et.set_tags(
                files=[str(target_path)],
                tags=payload,
                params=["-P", "-overwrite_original"],
            )

        self.write_xmp_sidecar(target_path, normalized_title, normalized_keywords, str(source_path))

        return {
            "target": str(target_path),
            "source": str(source_path),
            "title": normalized_title,
            "keywords": normalized_keywords,
        }

    def read_xmp_sidecar(self, image_path: Path) -> dict[str, Any]:
        sidecar_path = self._sidecar_path(image_path)
        if not sidecar_path.exists():
            return {}

        try:
            tree = ET.parse(sidecar_path)
        except Exception:
            return {}

        root = tree.getroot()
        title = self._find_text(root, "dc:title") or self._find_text(root, "photoshop:Headline") or ""
        description = self._find_text(root, "dc:description") or self._find_text(root, "xmp:Description") or ""
        source_path = self._find_text(root, "xmp:Source") or ""
        keywords = self._find_list(root, "dc:subject")

        return {
            "title": title,
            "description": description,
            "source_path": source_path,
            "keywords": keywords,
            "sidecar_path": str(sidecar_path),
        }

    def write_xmp_sidecar(
        self,
        target_path: Path,
        title: str,
        keywords: list[str],
        source_path: str = "",
    ) -> Path:
        sidecar_path = self._sidecar_path(target_path)

        xmpmeta = ET.Element(f"{{{XMP_NS['x']}}}xmpmeta")
        rdf = ET.SubElement(xmpmeta, f"{{{XMP_NS['rdf']}}}RDF")
        description = ET.SubElement(rdf, f"{{{XMP_NS['rdf']}}}Description")

        title_node = ET.SubElement(description, f"{{{XMP_NS['dc']}}}title")
        title_alt = ET.SubElement(title_node, f"{{{XMP_NS['rdf']}}}Alt")
        title_li = ET.SubElement(title_alt, f"{{{XMP_NS['rdf']}}}li")
        title_li.text = title

        desc_node = ET.SubElement(description, f"{{{XMP_NS['dc']}}}description")
        desc_alt = ET.SubElement(desc_node, f"{{{XMP_NS['rdf']}}}Alt")
        desc_li = ET.SubElement(desc_alt, f"{{{XMP_NS['rdf']}}}li")
        desc_li.text = title

        source_node = ET.SubElement(description, f"{{{XMP_NS['xmp']}}}Source")
        source_node.text = source_path

        headline_node = ET.SubElement(description, f"{{{XMP_NS['photoshop']}}}Headline")
        headline_node.text = title

        subject_node = ET.SubElement(description, f"{{{XMP_NS['dc']}}}subject")
        subject_bag = ET.SubElement(subject_node, f"{{{XMP_NS['rdf']}}}Bag")
        for keyword in keywords:
            li = ET.SubElement(subject_bag, f"{{{XMP_NS['rdf']}}}li")
            li.text = keyword

        xmp_packet = ET.ElementTree(xmpmeta)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        xmp_packet.write(sidecar_path, encoding="utf-8", xml_declaration=True)
        return sidecar_path

    @staticmethod
    def _serialize_exif_value(value: Any) -> Any:
        if isinstance(value, bytes):
            return value.hex()
        try:
            return str(value)
        except Exception:
            return repr(value)

    @staticmethod
    def _normalize_title(title: str) -> str:
        normalized = " ".join((title or "").strip().split())
        if not normalized:
            raise ValueError("Title cannot be empty.")
        return normalized

    @staticmethod
    def _normalize_keywords(keywords: list[str]) -> list[str]:
        ordered_keywords: list[str] = []
        seen: set[str] = set()

        for keyword in keywords:
            clean = " ".join(str(keyword).strip().split())
            if not clean:
                continue
            key = clean.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered_keywords.append(clean)

        if not ordered_keywords:
            raise ValueError("At least one keyword is required.")

        return ordered_keywords

    @staticmethod
    def _sidecar_path(image_path: Path) -> Path:
        return image_path.with_suffix(".xmp")

    @staticmethod
    def _find_text(root: ET.Element, tag: str) -> str:
        namespace, local_name = tag.split(":", 1)
        node = root.find(f".//{{{XMP_NS[namespace]}}}{local_name}")
        if node is None:
            return ""
        value = "".join(node.itertext()).strip()
        return value

    @staticmethod
    def _find_list(root: ET.Element, tag: str) -> list[str]:
        namespace, local_name = tag.split(":", 1)
        values: list[str] = []
        for li in root.findall(f".//{{{XMP_NS[namespace]}}}{local_name}//{{{XMP_NS['rdf']}}}li"):
            text = " ".join((li.text or "").split()).strip()
            if text:
                values.append(text)
        return values
