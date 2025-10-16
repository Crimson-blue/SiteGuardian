from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, BigInteger
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from config.database import Base
import enum

class ScheduleType(enum.Enum):
    interval = "interval"
    daily = "daily"
    cron = "cron"

class Website(Base):
    __tablename__ = "websites"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    crawl_depth: Mapped[int] = mapped_column(Integer, default=1)
    include_images: Mapped[bool] = mapped_column(Boolean, default=True)
    include_css: Mapped[bool] = mapped_column(Boolean, default=True)
    include_js: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_type: Mapped[ScheduleType] = mapped_column(Enum(ScheduleType), default=ScheduleType.interval)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    daily_time: Mapped[str | None] = mapped_column(String, nullable=True)  # "HH:MM"
    cron_expression: Mapped[str | None] = mapped_column(String, nullable=True)
    retention_limit: Mapped[int] = mapped_column(Integer, default=10)
    compress_old: Mapped[bool] = mapped_column(Boolean, default=True)
    max_workers: Mapped[int] = mapped_column(Integer, default=8)
    email_notify: Mapped[bool] = mapped_column(Boolean, default=False)
    email_to: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    snapshots: Mapped[list["BackupSnapshot"]] = relationship("BackupSnapshot", back_populates="website", cascade="all, delete-orphan")

class BackupSnapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id"), nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)  # e.g. 20250103_235912
    path: Mapped[str] = mapped_column(String, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    website: Mapped[Website] = relationship("Website", back_populates="snapshots")
    files: Mapped[list["BackupFile"]] = relationship("BackupFile", back_populates="snapshot", cascade="all, delete-orphan")

class BackupFile(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    rel_path: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot: Mapped[BackupSnapshot] = relationship("BackupSnapshot", back_populates="files")