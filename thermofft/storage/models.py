"""SQLAlchemy модели для хранения прогонов, стадий, алертов, кэша."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    input_path: Mapped[str] = mapped_column(Text)
    input_signature: Mapped[str] = mapped_column(String(128), index=True)
    config_json: Mapped[str] = mapped_column(Text)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="ok")

    clean_points: Mapped[int] = mapped_column(Integer, default=0)
    amp_in_robust: Mapped[float] = mapped_column(Float, default=0.0)
    amp_out_robust: Mapped[float] = mapped_column(Float, default=0.0)
    attenuation_robust: Mapped[float] = mapped_column(Float, default=0.0)
    pearson: Mapped[float] = mapped_column(Float, default=0.0)
    lag_hours: Mapped[float] = mapped_column(Float, default=0.0)
    out_of_range_pct: Mapped[float] = mapped_column(Float, default=0.0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)

    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    spectrum_json: Mapped[str] = mapped_column(Text, default="{}")
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    forecast_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    interpretation: Mapped[str] = mapped_column(Text, default="")
    artifacts_dir: Mapped[str] = mapped_column(Text, default="")

    stages: Mapped[list["StageLog"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    alerts: Mapped[list["AlertEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class StageLog(Base):
    __tablename__ = "stage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    message: Mapped[str] = mapped_column(Text, default="")

    run: Mapped[AnalysisRun] = relationship(back_populates="stages")


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    threshold: Mapped[float] = mapped_column(Float, default=0.0)

    run: Mapped[AnalysisRun] = relationship(back_populates="alerts")


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_hit_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text)
    run_uid: Mapped[str] = mapped_column(String(64), default="")

    __table_args__ = (UniqueConstraint("cache_key", name="uq_cache_entries_key"),)
