from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


image_tags = Table(
    "image_tags",
    Base.metadata,
    Column("image_id", ForeignKey("image_candidates.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


collection_images = Table(
    "collection_images",
    Base.metadata,
    Column("collection_id", ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
    Column("image_id", ForeignKey("image_candidates.id", ondelete="CASCADE"), primary_key=True),
)


class WatchedFolder(Base):
    __tablename__ = "watched_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scanned: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("image_candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ImageCandidate(Base):
    __tablename__ = "image_candidates"
    __table_args__ = (UniqueConstraint("path", name="uq_image_candidate_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    ext: Mapped[str] = mapped_column(String(16), nullable=False)

    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    megapixels: Mapped[float | None] = mapped_column(Float)
    aspect_ratio: Mapped[float | None] = mapped_column(Float)
    bit_depth: Mapped[int | None] = mapped_column(Integer)
    color_space: Mapped[str | None] = mapped_column(String(128))

    size_bytes: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meets_min_resolution: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vision: Mapped[VisionAnalysis | None] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", uselist=False
    )
    quality: Mapped[ImageQuality | None] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", uselist=False
    )
    uploads: Mapped[list[StockUpload]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=image_tags, back_populates="images"
    )
    collections: Mapped[list[Collection]] = relationship(
        secondary=collection_images, back_populates="images"
    )


class VisionAnalysis(Base):
    __tablename__ = "vision_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("image_candidates.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    title_short: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    title_poetic: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    title_descriptive: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stock_site: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    stock_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stock_location: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    stock_usage_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    mood: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    scene_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    objects_detected: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    color_palette: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    exif_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    candidate: Mapped[ImageCandidate] = relationship(back_populates="vision")


class ImageQuality(Base):
    __tablename__ = "image_quality"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("image_candidates.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    overall_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sharpness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    contrast: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exposure: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    noise_level: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dynamic_range: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    edge_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    color_cast_deviation: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    shadow_clipping: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    highlight_clipping: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    is_blurry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_overexposed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_underexposed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_high_noise: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    low_contrast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_color_cast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    candidate: Mapped[ImageCandidate] = relationship(back_populates="quality")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#4b5563", nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    images: Mapped[list[ImageCandidate]] = relationship(
        secondary=image_tags, back_populates="tags"
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_smart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    search_spec: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    images: Mapped[list[ImageCandidate]] = relationship(
        secondary=collection_images, back_populates="collections"
    )


class StockUpload(Base):
    __tablename__ = "stock_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("image_candidates.id", ondelete="CASCADE"))
    site: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="pending", nullable=False)
    upload_id: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejection_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    candidate: Mapped[ImageCandidate] = relationship(back_populates="uploads")
