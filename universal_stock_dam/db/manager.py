from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import String, cast, create_engine, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, joinedload, sessionmaker

from universal_stock_dam.core.paths import data_path
from universal_stock_dam.core.raw_loader import extract_preview_rgb, is_raw_format
from universal_stock_dam.db.models import (
    Base,
    CalendarEvent,
    Collection,
    ImageCandidate,
    ImageQuality,
    StockUpload,
    Tag,
    VisionAnalysis,
    WatchedFolder,
)


class DatabaseManager:
    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = str(data_path("assets.db"))
        full_path = Path(db_path).expanduser().resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)

        self.database_path = str(full_path)
        self.engine = create_engine(f"sqlite+pysqlite:///{full_path}", future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)
        Base.metadata.create_all(self.engine)
        self._ensure_collection_columns()
        self._ensure_vision_analysis_columns()

    def _ensure_collection_columns(self) -> None:
        inspector = sa_inspect(self.engine)
        if "collections" not in inspector.get_table_names():
            return

        columns = {column["name"] for column in inspector.get_columns("collections")}
        if "is_smart" not in columns:
            with self.engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE collections ADD COLUMN is_smart BOOLEAN NOT NULL DEFAULT 0")
        if "search_spec" not in columns:
            with self.engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE collections ADD COLUMN search_spec JSON NOT NULL DEFAULT '{}' ")

    def _ensure_vision_analysis_columns(self) -> None:
        inspector = sa_inspect(self.engine)
        if "vision_analysis" not in inspector.get_table_names():
            return

        columns = {column["name"] for column in inspector.get_columns("vision_analysis")}
        migrations = [
            ("stock_site", "ALTER TABLE vision_analysis ADD COLUMN stock_site VARCHAR(128) NOT NULL DEFAULT ''"),
            ("stock_notes", "ALTER TABLE vision_analysis ADD COLUMN stock_notes TEXT NOT NULL DEFAULT ''"),
            ("stock_location", "ALTER TABLE vision_analysis ADD COLUMN stock_location VARCHAR(256) NOT NULL DEFAULT ''"),
            ("stock_usage_notes", "ALTER TABLE vision_analysis ADD COLUMN stock_usage_notes TEXT NOT NULL DEFAULT ''"),
        ]
        with self.engine.begin() as connection:
            for column_name, ddl in migrations:
                if column_name not in columns:
                    connection.exec_driver_sql(ddl)

    def add_or_update_candidate(
        self,
        path: str,
        filename: str,
        ext: str,
        size_bytes: int | None = None,
        width: int | None = None,
        height: int | None = None,
        bit_depth: int | None = None,
        color_space: str | None = None,
    ) -> ImageCandidate:
        normalized_path = str(Path(path).expanduser().resolve())
        normalized_ext = ext.lower().lstrip(".")

        with self.session_factory() as session:
            stmt = select(ImageCandidate).where(ImageCandidate.path == normalized_path)
            candidate = session.execute(stmt).scalar_one_or_none()

            megapixels = None
            aspect_ratio = None
            if width and height and width > 0 and height > 0:
                megapixels = round((width * height) / 1_000_000.0, 2)
                aspect_ratio = round(width / float(height), 6)

            if candidate is None:
                candidate = ImageCandidate(
                    path=normalized_path,
                    filename=filename,
                    ext=normalized_ext,
                )
                session.add(candidate)

            candidate.filename = filename
            candidate.ext = normalized_ext
            candidate.size_bytes = size_bytes
            candidate.width = width
            candidate.height = height
            candidate.megapixels = megapixels
            candidate.aspect_ratio = aspect_ratio
            candidate.bit_depth = bit_depth
            candidate.color_space = color_space
            session.commit()
            session.refresh(candidate)
            return candidate

    def set_candidate_favorite(self, candidate_id: int, is_favorite: bool) -> ImageCandidate:
        with self.session_factory() as session:
            candidate = session.get(ImageCandidate, candidate_id)
            if candidate is None:
                raise ValueError(f"Candidate {candidate_id} not found")
            candidate.is_favorite = bool(is_favorite)
            session.commit()
            session.refresh(candidate)
            return candidate

    def delete_candidate(self, candidate_id: int) -> str:
        with self.session_factory() as session:
            candidate = session.get(ImageCandidate, candidate_id)
            if candidate is None:
                raise ValueError(f"Candidate {candidate_id} not found")

            filename = candidate.filename
            for event in session.execute(
                select(CalendarEvent).where(CalendarEvent.candidate_id == candidate_id)
            ).scalars():
                event.candidate_id = None
            session.delete(candidate)
            session.commit()
            return filename

    @staticmethod
    def _calendar_event_payload(event: CalendarEvent, candidate_filename: str = "") -> dict[str, object]:
        return {
            "id": int(event.id),
            "title": event.title,
            "description": event.description,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "candidate_id": int(event.candidate_id) if event.candidate_id is not None else None,
            "candidate_filename": candidate_filename,
        }

    def list_calendar_events(
        self,
        starts_before: datetime | None = None,
        ends_after: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, object]]:
        stmt = (
            select(CalendarEvent, ImageCandidate.filename)
            .outerjoin(ImageCandidate, ImageCandidate.id == CalendarEvent.candidate_id)
            .order_by(CalendarEvent.starts_at.asc(), CalendarEvent.id.asc())
        )
        if starts_before is not None:
            stmt = stmt.where(CalendarEvent.starts_at < starts_before)
        if ends_after is not None:
            stmt = stmt.where(CalendarEvent.ends_at >= ends_after)
        stmt = stmt.limit(max(1, min(int(limit), 10000)))
        with self.session_factory() as session:
            rows = session.execute(stmt).all()
            return [self._calendar_event_payload(event, filename or "") for event, filename in rows]

    def get_calendar_event(self, event_id: int) -> dict[str, object] | None:
        with self.session_factory() as session:
            row = session.execute(
                select(CalendarEvent, ImageCandidate.filename)
                .outerjoin(ImageCandidate, ImageCandidate.id == CalendarEvent.candidate_id)
                .where(CalendarEvent.id == int(event_id))
            ).one_or_none()
            if row is None:
                return None
            event, filename = row
            return self._calendar_event_payload(event, filename or "")

    def list_calendar_asset_choices(self) -> list[dict[str, object]]:
        with self.session_factory() as session:
            rows = session.execute(
                select(ImageCandidate.id, ImageCandidate.filename, ImageCandidate.path)
                .order_by(ImageCandidate.filename.asc(), ImageCandidate.id.asc())
            ).all()
            return [
                {"id": int(candidate_id), "filename": filename, "path": path}
                for candidate_id, filename, path in rows
            ]

    def save_calendar_event(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        description: str = "",
        candidate_id: int | None = None,
        event_id: int | None = None,
    ) -> dict[str, object]:
        normalized_title = " ".join(title.split()).strip()
        if not normalized_title:
            raise ValueError("Event title cannot be empty")
        if len(normalized_title) > 256:
            raise ValueError("Event title cannot exceed 256 characters")
        if len(description) > 4000:
            raise ValueError("Event description cannot exceed 4000 characters")
        if ends_at <= starts_at:
            raise ValueError("Event end time must be after its start time")

        with self.session_factory() as session:
            if candidate_id is not None and session.get(ImageCandidate, int(candidate_id)) is None:
                raise ValueError(f"Asset {candidate_id} not found")
            event = session.get(CalendarEvent, int(event_id)) if event_id is not None else None
            if event_id is not None and event is None:
                raise ValueError(f"Calendar event {event_id} not found")
            if event is None:
                event = CalendarEvent(title=normalized_title, starts_at=starts_at, ends_at=ends_at)
                session.add(event)
            event.title = normalized_title
            event.description = description.strip()
            event.starts_at = starts_at
            event.ends_at = ends_at
            event.candidate_id = int(candidate_id) if candidate_id is not None else None
            session.commit()
            session.refresh(event)
            filename = ""
            if event.candidate_id is not None:
                candidate = session.get(ImageCandidate, event.candidate_id)
                filename = candidate.filename if candidate is not None else ""
            return self._calendar_event_payload(event, filename)

    def delete_calendar_event(self, event_id: int) -> None:
        with self.session_factory() as session:
            event = session.get(CalendarEvent, int(event_id))
            if event is not None:
                session.delete(event)
                session.commit()

    def detect_duplicate_groups(self, limit: int = 1000, max_distance: int = 5) -> list[dict[str, object]]:
        with self.session_factory() as session:
            candidates = list(
                session.execute(
                    select(ImageCandidate)
                    .options(joinedload(ImageCandidate.quality), joinedload(ImageCandidate.vision))
                    .order_by(ImageCandidate.created_at.desc())
                    .limit(max(1, limit))
                ).scalars()
            )

        signatures: list[tuple[ImageCandidate, int]] = []
        for candidate in candidates:
            try:
                signatures.append((candidate, self._image_signature(Path(candidate.path))))
            except Exception:
                continue

        groups: list[dict[str, object]] = []
        visited: set[int] = set()
        for idx, (candidate, signature) in enumerate(signatures):
            if candidate.id in visited:
                continue

            cluster = [(candidate, signature)]
            visited.add(candidate.id)
            for other, other_signature in signatures[idx + 1 :]:
                if other.id in visited:
                    continue
                distance = (signature ^ other_signature).bit_count()
                if distance <= max_distance:
                    cluster.append((other, other_signature))
                    visited.add(other.id)

            if len(cluster) > 1:
                members = []
                for member, member_signature in cluster:
                    quality_score = member.quality.overall_score if member.quality else None
                    members.append(
                        {
                            "id": int(member.id),
                            "filename": member.filename,
                            "path": member.path,
                            "signature": member_signature,
                            "quality": quality_score,
                        }
                    )
                groups.append(
                    {
                        "group_size": len(cluster),
                        "distance_threshold": max_distance,
                        "members": members,
                    }
                )

        return groups

    def upsert_quality(self, candidate_id: int, metrics: dict[str, float | bool]) -> ImageQuality:
        with self.session_factory() as session:
            stmt = select(ImageQuality).where(ImageQuality.candidate_id == candidate_id)
            quality = session.execute(stmt).scalar_one_or_none()
            if quality is None:
                quality = ImageQuality(candidate_id=candidate_id)
                session.add(quality)

            for key, value in metrics.items():
                if hasattr(quality, key):
                    setattr(quality, key, value)

            if quality.overall_score >= 70.0:
                candidate = session.get(ImageCandidate, candidate_id)
                if candidate is not None:
                    candidate.recommended = True

            session.commit()
            session.refresh(quality)
            return quality

    def upsert_vision_analysis(self, candidate_id: int, payload: dict) -> VisionAnalysis:
        with self.session_factory() as session:
            stmt = select(VisionAnalysis).where(VisionAnalysis.candidate_id == candidate_id)
            vision = session.execute(stmt).scalar_one_or_none()
            if vision is None:
                vision = VisionAnalysis(candidate_id=candidate_id)
                session.add(vision)

            for key, value in payload.items():
                if key == "keywords":
                    setattr(vision, key, self._keywords_to_list(value))
                elif hasattr(vision, key):
                    setattr(vision, key, value)

            session.commit()
            session.refresh(vision)
            return vision

    def list_candidates(self, page: int = 1, page_size: int = 60) -> tuple[list[ImageCandidate], int]:
        return self.query_candidates(page=page, page_size=page_size)

    def query_candidates(
        self,
        *,
        page: int = 1,
        page_size: int = 60,
        min_quality: int = 0,
        max_quality: int = 100,
        formats: list[str] | None = None,
        sort: str = "newest",
        search: str = "",
        tag_query: str = "",
        collection_id: int | None = None,
        favorite_only: bool = False,
        recommended_only: bool = False,
        camera_query: str = "",
        lens_query: str = "",
    ) -> tuple[list[ImageCandidate], int]:
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 60

        normalized_formats = None
        if formats:
            normalized_formats = [f.lower().lstrip(".") for f in formats if str(f).strip()]

        with self.session_factory() as session:
            stmt = (
                select(ImageCandidate)
                .options(
                    joinedload(ImageCandidate.quality),
                    joinedload(ImageCandidate.vision),
                    joinedload(ImageCandidate.tags),
                )
                .outerjoin(ImageQuality, ImageQuality.candidate_id == ImageCandidate.id)
            )

            if min_quality > 0:
                stmt = stmt.where(func.coalesce(ImageQuality.overall_score, 0.0) >= float(min_quality))
            if max_quality < 100:
                stmt = stmt.where(func.coalesce(ImageQuality.overall_score, 0.0) <= float(max_quality))

            if normalized_formats:
                stmt = stmt.where(ImageCandidate.ext.in_(normalized_formats))

            if favorite_only:
                stmt = stmt.where(ImageCandidate.is_favorite.is_(True))
            if recommended_only:
                stmt = stmt.where(ImageCandidate.recommended.is_(True))

            if collection_id is not None:
                stmt = stmt.where(ImageCandidate.collections.any(Collection.id == int(collection_id)))

            normalized_tag_query = tag_query.strip()
            if normalized_tag_query:
                tag_terms = [term.strip() for term in normalized_tag_query.split(",") if term.strip()]
                for term in tag_terms:
                    stmt = stmt.where(ImageCandidate.tags.any(Tag.name.ilike(f"%{term}%")))

            normalized_search = search.strip()
            if normalized_search:
                pattern = f"%{normalized_search}%"
                stmt = stmt.where(
                    or_(
                        ImageCandidate.filename.ilike(pattern),
                        ImageCandidate.path.ilike(pattern),
                        VisionAnalysis.title.ilike(pattern),
                        VisionAnalysis.description.ilike(pattern),
                        VisionAnalysis.caption.ilike(pattern),
                        cast(VisionAnalysis.keywords, String).ilike(pattern),
                        VisionAnalysis.mood.ilike(pattern),
                        VisionAnalysis.scene_type.ilike(pattern),
                    )
                ).outerjoin(VisionAnalysis, VisionAnalysis.candidate_id == ImageCandidate.id)

            metadata_filters = []
            if camera_query.strip():
                metadata_filters.append(
                    func.lower(func.coalesce(func.json_extract(VisionAnalysis.exif_data, "$.camera_model"), "")).ilike(
                        f"%{camera_query.strip().lower()}%"
                    )
                )
            if lens_query.strip():
                metadata_filters.append(
                    func.lower(func.coalesce(func.json_extract(VisionAnalysis.exif_data, "$.lens"), "")).ilike(
                        f"%{lens_query.strip().lower()}%"
                    )
                )
            if metadata_filters:
                stmt = stmt.outerjoin(VisionAnalysis, VisionAnalysis.candidate_id == ImageCandidate.id)
                for expression in metadata_filters:
                    stmt = stmt.where(expression)

            if sort == "oldest":
                stmt = stmt.order_by(ImageCandidate.created_at.asc(), ImageCandidate.id.asc())
            elif sort == "quality_desc":
                stmt = stmt.order_by(func.coalesce(ImageQuality.overall_score, 0.0).desc(), ImageCandidate.id.desc())
            elif sort == "quality_asc":
                stmt = stmt.order_by(func.coalesce(ImageQuality.overall_score, 0.0).asc(), ImageCandidate.id.desc())
            else:
                stmt = stmt.order_by(ImageCandidate.created_at.desc(), ImageCandidate.id.desc())

            total_stmt = select(func.count()).select_from(stmt.subquery())
            total = int(session.execute(total_stmt).scalar_one())

            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            rows = list(session.execute(stmt).unique().scalars())
            return rows, total

    def get_candidate_by_id(self, candidate_id: int) -> ImageCandidate | None:
        with self.session_factory() as session:
            stmt = (
                select(ImageCandidate)
                .options(
                    joinedload(ImageCandidate.quality),
                    joinedload(ImageCandidate.vision),
                    joinedload(ImageCandidate.tags),
                )
                .where(ImageCandidate.id == candidate_id)
            )
            return session.execute(stmt).unique().scalar_one_or_none()

    def get_database_stats(self) -> dict[str, int | float | str]:
        with self.session_factory() as session:
            image_count = int(session.execute(select(func.count(ImageCandidate.id))).scalar_one())
            tag_count = int(session.execute(select(func.count(Tag.id))).scalar_one())
            collection_count = int(session.execute(select(func.count(Collection.id))).scalar_one())

            avg_quality = float(
                session.execute(select(func.coalesce(func.avg(ImageQuality.overall_score), 0.0))).scalar_one()
            )
            analyzed_count = int(session.execute(select(func.count(ImageQuality.id))).scalar_one())

        db_size_bytes = Path(self.database_path).stat().st_size if Path(self.database_path).exists() else 0
        analyzed_pct = 0.0 if image_count == 0 else (analyzed_count * 100.0 / image_count)

        return {
            "images": image_count,
            "tags": tag_count,
            "collections": collection_count,
            "avg_quality": round(avg_quality, 2),
            "analyzed_count": analyzed_count,
            "analyzed_pct": round(analyzed_pct, 2),
            "db_size_bytes": db_size_bytes,
            "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "database_path": self.database_path,
        }

    def get_quality_histogram(self, bin_count: int = 10) -> list[int]:
        bins = [0] * max(1, bin_count)
        width = 100.0 / len(bins)

        with self.session_factory() as session:
            scores = list(session.execute(select(ImageQuality.overall_score)).scalars())

        for score in scores:
            value = max(0.0, min(float(score), 100.0))
            idx = int(value // width) if width > 0 else 0
            if idx >= len(bins):
                idx = len(bins) - 1
            bins[idx] += 1

        return bins

    def get_quality_buckets(self, limit_per_bucket: int = 200) -> dict[str, list[dict[str, object]]]:
        with self.session_factory() as session:
            unanalyzed_stmt = (
                select(ImageCandidate)
                .outerjoin(ImageQuality, ImageQuality.candidate_id == ImageCandidate.id)
                .where(ImageQuality.id.is_(None))
                .order_by(ImageCandidate.created_at.desc())
                .limit(limit_per_bucket)
            )
            high_stmt = (
                select(ImageCandidate, ImageQuality)
                .join(ImageQuality, ImageQuality.candidate_id == ImageCandidate.id)
                .where(ImageQuality.overall_score >= 70.0)
                .order_by(ImageQuality.overall_score.desc())
                .limit(limit_per_bucket)
            )
            medium_stmt = (
                select(ImageCandidate, ImageQuality)
                .join(ImageQuality, ImageQuality.candidate_id == ImageCandidate.id)
                .where(ImageQuality.overall_score >= 40.0, ImageQuality.overall_score < 70.0)
                .order_by(ImageQuality.overall_score.desc())
                .limit(limit_per_bucket)
            )
            low_stmt = (
                select(ImageCandidate, ImageQuality)
                .join(ImageQuality, ImageQuality.candidate_id == ImageCandidate.id)
                .where(ImageQuality.overall_score < 40.0)
                .order_by(ImageQuality.overall_score.asc())
                .limit(limit_per_bucket)
            )

            unanalyzed = [
                {"id": row.id, "filename": row.filename, "path": row.path}
                for row in session.execute(unanalyzed_stmt).scalars()
            ]
            high = [
                {
                    "id": candidate.id,
                    "filename": candidate.filename,
                    "path": candidate.path,
                    "score": quality.overall_score,
                }
                for candidate, quality in session.execute(high_stmt).all()
            ]
            medium = [
                {
                    "id": candidate.id,
                    "filename": candidate.filename,
                    "path": candidate.path,
                    "score": quality.overall_score,
                }
                for candidate, quality in session.execute(medium_stmt).all()
            ]
            low = [
                {
                    "id": candidate.id,
                    "filename": candidate.filename,
                    "path": candidate.path,
                    "score": quality.overall_score,
                }
                for candidate, quality in session.execute(low_stmt).all()
            ]

        return {
            "unanalyzed": unanalyzed,
            "high": high,
            "medium": medium,
            "low": low,
        }

    def list_candidate_paths_for_quality(self, mode: str = "unanalyzed", limit: int = 500) -> list[str]:
        capped_limit = max(1, min(limit, 5000))

        with self.session_factory() as session:
            if mode == "all":
                stmt = (
                    select(ImageCandidate.path)
                    .order_by(ImageCandidate.created_at.desc())
                    .limit(capped_limit)
                )
            else:
                stmt = (
                    select(ImageCandidate.path)
                    .outerjoin(ImageQuality, ImageQuality.candidate_id == ImageCandidate.id)
                    .where(ImageQuality.id.is_(None))
                    .order_by(ImageCandidate.created_at.desc())
                    .limit(capped_limit)
                )

            return [str(path) for path in session.execute(stmt).scalars()]

    def list_candidate_paths_by_ids(self, candidate_ids: list[int]) -> list[str]:
        if not candidate_ids:
            return []

        normalized_ids = [int(i) for i in candidate_ids]
        with self.session_factory() as session:
            stmt = (
                select(ImageCandidate.path)
                .where(ImageCandidate.id.in_(normalized_ids))
                .order_by(ImageCandidate.created_at.desc())
            )
            return [str(path) for path in session.execute(stmt).scalars()]

    def add_or_get_tag(self, name: str, color: str = "#4b5563", description: str = "") -> Tag:
        normalized_name = " ".join(name.split()).strip()
        if not normalized_name:
            raise ValueError("Tag name cannot be empty")

        with self.session_factory() as session:
            stmt = select(Tag).where(Tag.name == normalized_name)
            tag = session.execute(stmt).scalar_one_or_none()
            if tag is None:
                tag = Tag(name=normalized_name, color=color, description=description)
                session.add(tag)
                session.commit()
                session.refresh(tag)
            return tag

    def list_tags(self) -> list[Tag]:
        with self.session_factory() as session:
            stmt = select(Tag).order_by(Tag.name.asc())
            return list(session.execute(stmt).scalars())

    def list_tag_summaries(self) -> list[dict[str, object]]:
        with self.session_factory() as session:
            stmt = (
                select(Tag, func.count(ImageCandidate.id))
                .outerjoin(Tag.images)
                .group_by(Tag.id)
                .order_by(Tag.name.asc())
            )
            rows = session.execute(stmt).all()

        return [
            {
                "id": int(tag.id),
                "name": tag.name,
                "color": tag.color,
                "usage_count": int(count),
            }
            for tag, count in rows
        ]

    def update_tag(self, tag_id: int, *, name: str | None = None, color: str | None = None) -> Tag:
        with self.session_factory() as session:
            tag = session.get(Tag, tag_id)
            if tag is None:
                raise ValueError(f"Tag {tag_id} not found")

            if name is not None:
                normalized_name = " ".join(name.split()).strip()
                if not normalized_name:
                    raise ValueError("Tag name cannot be empty")
                tag.name = normalized_name
            if color is not None:
                tag.color = color.strip() or tag.color

            session.commit()
            session.refresh(tag)
            return tag

    def delete_tag(self, tag_id: int) -> None:
        with self.session_factory() as session:
            tag = session.get(Tag, tag_id)
            if tag is None:
                return
            session.delete(tag)
            session.commit()

    def add_tag_to_candidate(self, candidate_id: int, tag_name: str) -> None:
        with self.session_factory() as session:
            candidate = session.get(ImageCandidate, candidate_id)
            if candidate is None:
                raise ValueError(f"Candidate {candidate_id} does not exist")

            normalized_name = " ".join(tag_name.split()).strip()
            if not normalized_name:
                return

            tag_stmt = select(Tag).where(Tag.name == normalized_name)
            tag = session.execute(tag_stmt).scalar_one_or_none()
            if tag is None:
                tag = Tag(name=normalized_name)
                session.add(tag)
                session.flush()

            if tag not in candidate.tags:
                candidate.tags.append(tag)

            session.commit()

    def add_or_get_collection(self, name: str, description: str = "") -> Collection:
        normalized_name = " ".join(name.split()).strip()
        if not normalized_name:
            raise ValueError("Collection name cannot be empty")

        with self.session_factory() as session:
            stmt = select(Collection).where(Collection.name == normalized_name)
            collection = session.execute(stmt).scalar_one_or_none()
            if collection is None:
                collection = Collection(name=normalized_name, description=description)
                session.add(collection)
                session.commit()
                session.refresh(collection)
            return collection

    def create_or_update_smart_collection(
        self,
        name: str,
        search_spec: dict[str, object],
        description: str = "",
    ) -> Collection:
        normalized_name = " ".join(name.split()).strip()
        if not normalized_name:
            raise ValueError("Collection name cannot be empty")

        with self.session_factory() as session:
            stmt = select(Collection).where(Collection.name == normalized_name)
            collection = session.execute(stmt).scalar_one_or_none()
            if collection is None:
                collection = Collection(name=normalized_name, description=description, is_smart=True, search_spec=search_spec)
                session.add(collection)
            else:
                collection.description = description
                collection.is_smart = True
                collection.search_spec = search_spec

            session.commit()
            session.refresh(collection)
            return collection

    def list_collections(self) -> list[Collection]:
        with self.session_factory() as session:
            stmt = select(Collection).order_by(Collection.created_at.desc(), Collection.name.asc())
            return list(session.execute(stmt).scalars())

    def list_collection_summaries(self) -> list[dict[str, object]]:
        with self.session_factory() as session:
            collections = list(session.execute(select(Collection).order_by(Collection.created_at.desc(), Collection.name.asc())).scalars())

        summaries: list[dict[str, object]] = []
        for collection in collections:
            if collection.is_smart:
                count = self.count_candidates_from_spec(collection.search_spec or {})
            else:
                with self.session_factory() as session:
                    count = int(
                        session.execute(
                            select(func.count(ImageCandidate.id))
                            .select_from(ImageCandidate)
                            .where(ImageCandidate.collections.any(Collection.id == collection.id))
                        ).scalar_one()
                    )

            summaries.append(
                {
                    "id": int(collection.id),
                    "name": collection.name,
                    "description": collection.description,
                    "is_smart": bool(collection.is_smart),
                    "search_spec": collection.search_spec or {},
                    "image_count": int(count),
                }
            )
        return summaries

    def update_collection(
        self,
        collection_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Collection:
        with self.session_factory() as session:
            collection = session.get(Collection, collection_id)
            if collection is None:
                raise ValueError(f"Collection {collection_id} not found")

            if name is not None:
                normalized_name = " ".join(name.split()).strip()
                if not normalized_name:
                    raise ValueError("Collection name cannot be empty")
                collection.name = normalized_name
            if description is not None:
                collection.description = description

            session.commit()
            session.refresh(collection)
            return collection

    def update_smart_collection_spec(self, collection_id: int, search_spec: dict[str, object]) -> Collection:
        with self.session_factory() as session:
            collection = session.get(Collection, collection_id)
            if collection is None:
                raise ValueError(f"Collection {collection_id} not found")
            collection.is_smart = True
            collection.search_spec = search_spec
            session.commit()
            session.refresh(collection)
            return collection

    def get_collection(self, collection_id: int) -> Collection | None:
        with self.session_factory() as session:
            return session.get(Collection, collection_id)

    def count_candidates_from_spec(self, search_spec: dict[str, object]) -> int:
        _, total = self.query_candidates(
            page=1,
            page_size=1,
            min_quality=int(search_spec.get("min_quality", 0) or 0),
            max_quality=int(search_spec.get("max_quality", 100) or 100),
            formats=[str(fmt) for fmt in search_spec.get("formats", []) if str(fmt).strip()],
            sort=str(search_spec.get("sort", "newest")),
            search=str(search_spec.get("search", "")),
            tag_query=str(search_spec.get("tag_query", "")),
            collection_id=search_spec.get("collection_id"),
            favorite_only=bool(search_spec.get("favorite_only", False)),
            recommended_only=bool(search_spec.get("recommended_only", False)),
            camera_query=str(search_spec.get("camera_query", "")),
            lens_query=str(search_spec.get("lens_query", "")),
        )
        return total

    def query_candidates_from_spec(
        self,
        search_spec: dict[str, object],
        *,
        page: int = 1,
        page_size: int = 60,
    ) -> tuple[list[ImageCandidate], int]:
        return self.query_candidates(
            page=page,
            page_size=page_size,
            min_quality=int(search_spec.get("min_quality", 0) or 0),
            max_quality=int(search_spec.get("max_quality", 100) or 100),
            formats=[str(fmt) for fmt in search_spec.get("formats", []) if str(fmt).strip()],
            sort=str(search_spec.get("sort", "newest")),
            search=str(search_spec.get("search", "")),
            tag_query=str(search_spec.get("tag_query", "")),
            collection_id=search_spec.get("collection_id"),
            favorite_only=bool(search_spec.get("favorite_only", False)),
            recommended_only=bool(search_spec.get("recommended_only", False)),
            camera_query=str(search_spec.get("camera_query", "")),
            lens_query=str(search_spec.get("lens_query", "")),
        )

    def batch_relocate_candidates(
        self,
        candidate_ids: list[int],
        *,
        target_dir: str,
        filename_template: str = "{stem}",
        move_files: bool = True,
    ) -> dict[str, object]:
        if not candidate_ids:
            return {"moved": [], "failed": [], "total": 0}

        normalized_target = Path(target_dir).expanduser().resolve()
        normalized_target.mkdir(parents=True, exist_ok=True)
        filename_template = filename_template.strip() or "{stem}"

        with self.session_factory() as session:
            candidates = [session.get(ImageCandidate, int(candidate_id)) for candidate_id in candidate_ids]
            candidates = [candidate for candidate in candidates if candidate is not None]

        moved: list[dict[str, str]] = []
        staged_paths: list[tuple[Path, Path]] = []
        db_updates: list[tuple[int, str, str]] = []

        try:
            for index, candidate in enumerate(candidates, start=1):
                source_path = Path(candidate.path)
                if not source_path.exists():
                    raise FileNotFoundError(f"File not found: {source_path}")

                extension = source_path.suffix.lstrip(".") or candidate.ext
                target_name = self._format_candidate_filename(
                    candidate=candidate,
                    template=filename_template,
                    index=index,
                    total=len(candidates),
                    extension=extension,
                )
                target_path = self._unique_target_path(normalized_target / target_name)

                if move_files or source_path.resolve() != target_path.resolve():
                    if source_path.resolve() == target_path.resolve():
                        staged_paths.append((target_path, source_path))
                        db_updates.append((int(candidate.id), str(target_path), target_path.name))
                        moved.append({"source": str(source_path), "target": str(target_path)})
                        continue
                    shutil.move(str(source_path), str(target_path))
                staged_paths.append((target_path, source_path))
                db_updates.append((int(candidate.id), str(target_path), target_path.name))
                moved.append({"source": str(source_path), "target": str(target_path)})

            with self.session_factory() as session:
                for candidate_id, new_path, new_name in db_updates:
                    candidate = session.get(ImageCandidate, candidate_id)
                    if candidate is None:
                        raise ValueError(f"Candidate {candidate_id} not found")
                    candidate.path = new_path
                    candidate.filename = new_name
                    candidate.ext = Path(new_path).suffix.lstrip(".") or candidate.ext
                session.commit()

        except Exception:
            for new_path, old_path in reversed(staged_paths):
                if new_path.exists() and not old_path.exists():
                    shutil.move(str(new_path), str(old_path))
            raise

        return {"moved": moved, "failed": [], "total": len(candidates)}

    def delete_collection(self, collection_id: int) -> None:
        with self.session_factory() as session:
            collection = session.get(Collection, collection_id)
            if collection is None:
                return
            session.delete(collection)
            session.commit()

    def assign_candidates_to_collection(self, collection_id: int, candidate_ids: list[int]) -> int:
        if not candidate_ids:
            return 0

        with self.session_factory() as session:
            collection = session.get(Collection, collection_id)
            if collection is None:
                raise ValueError(f"Collection {collection_id} not found")

            assigned = 0
            for candidate_id in candidate_ids:
                candidate = session.get(ImageCandidate, int(candidate_id))
                if candidate is None:
                    continue
                if candidate not in collection.images:
                    collection.images.append(candidate)
                    assigned += 1

            session.commit()
            return assigned

    def save_inspector_metadata(
        self,
        candidate_id: int,
        *,
        title: str,
        keywords: Iterable[str] | str,
    ) -> VisionAnalysis:
        normalized_title = " ".join(str(title or "").strip().split())
        keyword_list = self._keywords_to_list(keywords)
        if not normalized_title:
            raise ValueError("Title cannot be empty")

        with self.session_factory() as session:
            candidate = session.get(ImageCandidate, int(candidate_id))
            if candidate is None:
                raise ValueError(f"Candidate {candidate_id} not found")

            stmt = select(VisionAnalysis).where(VisionAnalysis.candidate_id == candidate.id)
            vision = session.execute(stmt).scalar_one_or_none()
            if vision is None:
                vision = VisionAnalysis(candidate_id=candidate.id)
                session.add(vision)

            vision.title = normalized_title
            vision.keywords = keyword_list

            for keyword in keyword_list:
                clean_name = " ".join(str(keyword).split()).strip()
                if not clean_name:
                    continue
                tag_stmt = select(Tag).where(Tag.name == clean_name)
                tag = session.execute(tag_stmt).scalar_one_or_none()
                if tag is None:
                    tag = Tag(name=clean_name)
                    session.add(tag)
                    session.flush()
                if tag not in candidate.tags:
                    candidate.tags.append(tag)

            session.commit()
            session.refresh(vision)
            return vision

    def _image_signature(self, image_path: Path) -> int:
        if is_raw_format(image_path):
            rgb = extract_preview_rgb(image_path, half_size=True)
            image = Image.fromarray(rgb, mode="RGB")
        else:
            with Image.open(image_path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")

        grayscale = image.resize((8, 8), Image.Resampling.LANCZOS).convert("L")
        pixels = np.asarray(grayscale, dtype=np.float32)
        average = float(pixels.mean())
        bits = (pixels > average).astype(np.uint8).flatten()
        signature = 0
        for bit in bits:
            signature = (signature << 1) | int(bit)
        return signature

    def _unique_target_path(self, target_path: Path) -> Path:
        if not target_path.exists():
            return target_path

        counter = 1
        stem = target_path.stem
        suffix = target_path.suffix
        while True:
            candidate = target_path.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _format_candidate_filename(
        self,
        *,
        candidate: ImageCandidate,
        template: str,
        index: int,
        total: int,
        extension: str,
    ) -> str:
        payload = {
            "stem": Path(candidate.filename).stem,
            "filename": candidate.filename,
            "index": index,
            "total": total,
            "ext": extension,
            "name": Path(candidate.filename).stem,
        }
        try:
            formatted = template.format_map(payload)
        except Exception:
            formatted = Path(candidate.filename).stem

        cleaned = "".join("_" if ch in '<>:\\/*?\"|' else ch for ch in str(formatted)).strip().strip(".")
        cleaned = cleaned or Path(candidate.filename).stem
        if not cleaned.lower().endswith(f".{extension.lower()}"):
            cleaned = f"{cleaned}.{extension.lstrip('.')}"
        return cleaned

    def set_upload_status(
        self,
        candidate_id: int,
        site: str,
        status: str,
        upload_id: str = "",
        notes: str = "",
    ) -> StockUpload:
        normalized_site = site.strip().lower()
        if not normalized_site:
            raise ValueError("site is required")

        with self.session_factory() as session:
            stmt = select(StockUpload).where(
                StockUpload.candidate_id == candidate_id,
                StockUpload.site == normalized_site,
            )
            record = session.execute(stmt).scalar_one_or_none()
            if record is None:
                record = StockUpload(candidate_id=candidate_id, site=normalized_site)
                session.add(record)

            record.status = status
            record.upload_id = upload_id
            record.notes = notes

            now = datetime.utcnow()
            if status == "uploaded":
                record.uploaded_at = now
            elif status == "approved":
                record.approved_at = now
            elif status == "rejected":
                record.rejected_at = now

            session.commit()
            session.refresh(record)
            return record

    def add_or_update_watched_folder(
        self, path: str, is_active: bool = True, last_scanned: datetime | None = None
    ) -> WatchedFolder:
        normalized_path = str(Path(path).expanduser().resolve())
        with self.session_factory() as session:
            stmt = select(WatchedFolder).where(WatchedFolder.path == normalized_path)
            folder = session.execute(stmt).scalar_one_or_none()
            if folder is None:
                folder = WatchedFolder(path=normalized_path)
                session.add(folder)

            folder.is_active = is_active
            if last_scanned is not None:
                folder.last_scanned = last_scanned

            session.commit()
            session.refresh(folder)
            return folder

    def backup_database(self, backup_dir: str = "universal_stock_dam/backups") -> str:
        source = Path(self.database_path)
        if not source.exists():
            raise FileNotFoundError(f"Database not found at {source}")

        target_dir = Path(backup_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target_path = target_dir / f"assets_{timestamp}.db"

        shutil.copy2(source, target_path)
        return str(target_path)

    def reset_database(self, backup_dir: str = "universal_stock_dam/backups") -> str:
        backup_path = self.backup_database(backup_dir=backup_dir)
        inspector = sa_inspect(self.engine)
        existing_tables = set(inspector.get_table_names())

        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in existing_tables:
                    connection.exec_driver_sql(f'DELETE FROM "{table.name}"')
            if "sqlite_sequence" in existing_tables:
                connection.exec_driver_sql("DELETE FROM sqlite_sequence")
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")

        return backup_path

    def restore_database(self, backup_path: str) -> None:
        backup = Path(backup_path).expanduser().resolve()
        if not backup.exists():
            raise FileNotFoundError(f"Backup not found: {backup}")

        destination = Path(self.database_path)
        self.engine.dispose()
        shutil.copy2(backup, destination)
        self.engine = create_engine(f"sqlite+pysqlite:///{destination}", future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    def remove_missing_candidates(self) -> int:
        deleted = 0
        with self.session_factory() as session:
            stmt = select(ImageCandidate)
            candidates = list(session.execute(stmt).scalars())
            for candidate in candidates:
                if not Path(candidate.path).exists():
                    session.delete(candidate)
                    deleted += 1
            session.commit()
        return deleted

    def vacuum_database(self) -> None:
        with self.engine.connect() as conn:
            conn.exec_driver_sql("VACUUM")

    def enforce_thumbnail_cache_lru(self, thumbnail_root: str, max_cache_bytes: int) -> dict[str, int]:
        if max_cache_bytes <= 0:
            return {"removed_files": 0, "freed_bytes": 0, "current_bytes": 0}

        root = Path(thumbnail_root).expanduser().resolve()
        if not root.exists():
            return {"removed_files": 0, "freed_bytes": 0, "current_bytes": 0}

        files = [p for p in root.rglob("*") if p.is_file()]
        total_size = sum(p.stat().st_size for p in files)
        if total_size <= max_cache_bytes:
            return {"removed_files": 0, "freed_bytes": 0, "current_bytes": total_size}

        files.sort(key=lambda p: p.stat().st_mtime)

        removed = 0
        freed = 0
        for file_path in files:
            if total_size <= max_cache_bytes:
                break
            size = file_path.stat().st_size
            try:
                file_path.unlink()
                removed += 1
                freed += size
                total_size -= size
            except OSError:
                continue

        return {"removed_files": removed, "freed_bytes": freed, "current_bytes": total_size}

    @staticmethod
    def _keywords_to_list(keywords: Iterable[str] | str) -> list[str]:
        if isinstance(keywords, str):
            items = [chunk.strip() for chunk in keywords.split(",")]
        else:
            items = [str(chunk).strip() for chunk in keywords]

        seen: set[str] = set()
        ordered: list[str] = []
        for keyword in items:
            if not keyword:
                continue
            key = keyword.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(keyword)

        return ordered
