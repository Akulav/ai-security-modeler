"""Database tables. Passwords are deliberately not modelled: only their *type* is stored."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    email: Mapped[str | None] = mapped_column(String(254), default=None)
    security_level: Mapped[str] = mapped_column(String(20), default="medium")
    password_type: Mapped[str] = mapped_column(String(30), default="unknown")
    os: Mapped[str | None] = mapped_column(String(20), default=None)
    os_version: Mapped[str | None] = mapped_column(String(64), default=None)
    encryption: Mapped[str] = mapped_column(String(20), default="unknown")
    defenses: Mapped[list | None] = mapped_column(JSON, default=list)
    # An app listed inside an Apps node.
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str] = mapped_column(Text, default="")
    pos_x: Mapped[float] = mapped_column(Float, default=0)
    pos_y: Mapped[float] = mapped_column(Float, default=0)

    # Result of the latest HIBP check; the checked address is kept so editing the
    # email can invalidate a result that belonged to the previous address.
    breaches: Mapped[list | None] = mapped_column(JSON, default=None)
    breach_checked_email: Mapped[str | None] = mapped_column(String(254), default=None)
    breach_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    breach_advice: Mapped[str | None] = mapped_column(Text, default=None)


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    relation: Mapped[str] = mapped_column(String(40))
    # None means "use the relationship's default"; see catalog.RELATIONS.
    loss_mode: Mapped[str | None] = mapped_column(String(20), default=None)
    notes: Mapped[str] = mapped_column(Text, default="")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class SavedAnswer(Base):
    """The latest AI answer to each question, kept for reopening and for the PDF report."""
    __tablename__ = "saved_answers"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    report: Mapped[dict] = mapped_column(JSON)
