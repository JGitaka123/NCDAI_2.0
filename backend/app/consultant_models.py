"""Separate consultant database: immutable handoffs and independent opinions.

No patient directory, passwords or sessions are replicated here. Authentication
and facility authorization are checked against the primary service on every call.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, JSON, ForeignKey, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .models import utcnow

CONSULTANT_SCHEMA = 'consultant-20260913-1'


class ConsultantBase(DeclarativeBase):
    pass


class ConsultantSchema(ConsultantBase):
    __tablename__ = 'consultant_schema'
    version: Mapped[str] = mapped_column(String(50), primary_key=True)


class ConsultantCase(ConsultantBase):
    __tablename__ = 'consultant_cases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    facility_id: Mapped[str] = mapped_column(String(36), index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsultantOpinion(ConsultantBase):
    __tablename__ = 'consultant_opinions'
    case_id: Mapped[str] = mapped_column(ForeignKey('consultant_cases.id'), primary_key=True)
    reviewer_id: Mapped[str] = mapped_column(String(36))
    opinion: Mapped[dict] = mapped_column(JSON)
    opinion_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
