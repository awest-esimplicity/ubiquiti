"""SQLAlchemy ORM models for persisting owners, devices, schedules, and audit events."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


class OwnerModel(Base):
    """ORM model representing dashboard owners."""

    __tablename__ = "owners"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pin: Mapped[str] = mapped_column(String(64), nullable=False)


class DeviceModel(Base):
    """ORM model representing registered devices."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mac: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(64), nullable=False)


class ScheduleModel(Base):
    """ORM model representing device lock schedules."""

    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    targets_json: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    end_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    window_start: Mapped[str] = mapped_column(String(64), nullable=False)
    window_end: Mapped[str] = mapped_column(String(64), nullable=False)
    recurrence_json: Mapped[str] = mapped_column(Text, nullable=False)
    exceptions_json: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class ScheduleMetadataModel(Base):
    """Stores configuration metadata shared across schedules."""

    __tablename__ = "schedule_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class EventModel(Base):
    """Audit log entries for significant system actions."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_type: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
