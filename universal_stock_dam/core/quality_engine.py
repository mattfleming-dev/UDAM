from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass(slots=True)
class QualityMetrics:
    overall_score: float
    sharpness: float
    contrast: float
    exposure: float
    noise_level: float
    dynamic_range: float
    edge_density: float
    color_cast_deviation: float
    shadow_clipping: float
    highlight_clipping: float
    is_blurry: bool
    is_overexposed: bool
    is_underexposed: bool
    has_high_noise: bool
    low_contrast: bool
    has_color_cast: bool

    def to_dict(self) -> dict[str, float | bool]:
        return asdict(self)


class QualityEngine:
    def analyze_bgr(self, bgr: np.ndarray) -> QualityMetrics:
        if bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError("Expected BGR image with shape [H, W, 3]")

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        sharpness = self._sharpness_score(gray)
        contrast = self._contrast_score(gray)
        exposure, shadow_clip, highlight_clip = self._exposure_scores(gray)
        noise = self._noise_score(gray)
        dynamic_range = self._dynamic_range_score(gray)
        edge_density = self._edge_density_score(gray)
        color_cast = self._color_cast_score(bgr)

        overall = self._overall_score(
            sharpness=sharpness,
            contrast=contrast,
            exposure=exposure,
            noise=noise,
            dynamic_range=dynamic_range,
            edge_density=edge_density,
            color_cast=color_cast,
            shadow_clip=shadow_clip,
            highlight_clip=highlight_clip,
        )

        return QualityMetrics(
            overall_score=float(overall),
            sharpness=float(sharpness),
            contrast=float(contrast),
            exposure=float(exposure),
            noise_level=float(noise),
            dynamic_range=float(dynamic_range),
            edge_density=float(edge_density),
            color_cast_deviation=float(color_cast),
            shadow_clipping=float(shadow_clip),
            highlight_clipping=float(highlight_clip),
            is_blurry=sharpness < 35.0,
            is_overexposed=exposure < 45.0 and highlight_clip > 12.0,
            is_underexposed=exposure < 45.0 and shadow_clip > 12.0,
            has_high_noise=noise < 40.0,
            low_contrast=contrast < 35.0,
            has_color_cast=color_cast > 18.0,
        )

    def analyze_rgb(self, rgb: np.ndarray) -> QualityMetrics:
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return self.analyze_bgr(bgr)

    @staticmethod
    def _sharpness_score(gray: np.ndarray) -> float:
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        score = min(lap_var / 15.0, 100.0)
        return max(score, 0.0)

    @staticmethod
    def _contrast_score(gray: np.ndarray) -> float:
        g = gray.astype(np.float32)
        min_v = float(np.percentile(g, 2))
        max_v = float(np.percentile(g, 98))
        denom = max(max_v + min_v, 1e-6)
        michelson = (max_v - min_v) / denom
        return float(np.clip(michelson * 120.0, 0.0, 100.0))

    @staticmethod
    def _exposure_scores(gray: np.ndarray) -> tuple[float, float, float]:
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        hist = hist / max(hist.sum(), 1e-6)

        mean_luma = float(gray.mean())
        target = 127.0
        deviation = abs(mean_luma - target) / target
        exposure_score = float(np.clip(100.0 * (1.0 - deviation), 0.0, 100.0))

        shadow_clip = float(hist[:5].sum() * 100.0)
        highlight_clip = float(hist[-5:].sum() * 100.0)
        return exposure_score, shadow_clip, highlight_clip

    @staticmethod
    def _noise_score(gray: np.ndarray) -> float:
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        residual = gray.astype(np.float32) - blur.astype(np.float32)
        sigma = float(residual.std())
        return float(np.clip(100.0 - sigma * 4.0, 0.0, 100.0))

    @staticmethod
    def _dynamic_range_score(gray: np.ndarray) -> float:
        low = float(np.percentile(gray, 5))
        high = float(np.percentile(gray, 95))
        span = max(high - low, 0.0)
        return float(np.clip(span / 2.2, 0.0, 100.0))

    @staticmethod
    def _edge_density_score(gray: np.ndarray) -> float:
        edges = cv2.Canny(gray, 100, 200)
        density = float((edges > 0).mean() * 100.0)
        return float(np.clip(density * 4.0, 0.0, 100.0))

    @staticmethod
    def _color_cast_score(bgr: np.ndarray) -> float:
        channel_means = bgr.reshape(-1, 3).mean(axis=0)
        avg = float(channel_means.mean())
        deviation = float(np.abs(channel_means - avg).mean())
        return float(np.clip(deviation, 0.0, 100.0))

    @staticmethod
    def _overall_score(
        *,
        sharpness: float,
        contrast: float,
        exposure: float,
        noise: float,
        dynamic_range: float,
        edge_density: float,
        color_cast: float,
        shadow_clip: float,
        highlight_clip: float,
    ) -> float:
        clipping_penalty = float(np.clip((shadow_clip + highlight_clip) * 0.8, 0.0, 25.0))
        color_cast_penalty = float(np.clip(color_cast * 0.6, 0.0, 20.0))

        weighted = (
            sharpness * 0.22
            + contrast * 0.14
            + exposure * 0.16
            + noise * 0.14
            + dynamic_range * 0.12
            + edge_density * 0.10
            + max(100.0 - color_cast, 0.0) * 0.12
        )
        return float(np.clip(weighted - clipping_penalty - color_cast_penalty * 0.2, 0.0, 100.0))
