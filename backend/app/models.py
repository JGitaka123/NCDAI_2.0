from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Integer, Boolean, Date, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, JSON, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    record_mode: Mapped[str] = mapped_column(String(30), default="synthetic", server_default="synthetic")
    __table_args__ = (CheckConstraint("record_mode IN ('synthetic', 'clinical_testing')", name="ck_facility_record_mode"),)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('clinician', 'supervisor', 'admin')", name="ck_user_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_change_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("facility_id", "external_id"), UniqueConstraint("facility_id", "id"),
                     CheckConstraint("sex IN ('female', 'male', 'other', 'unknown')", name="ck_patient_sex"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(80))
    given_name: Mapped[str] = mapped_column(String(100))
    family_name: Mapped[str] = mapped_column(String(100))
    date_of_birth: Mapped[datetime] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(20))
    female_pregnancy_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Encounter(Base):
    __tablename__ = "encounters"
    __table_args__ = (UniqueConstraint("facility_id", "id", "patient_id"),
                     ForeignKeyConstraint(["facility_id", "patient_id"], ["patients.facility_id", "patients.id"]),
                     CheckConstraint("version >= 1", name="ck_encounter_version"),
                     CheckConstraint("status IN ('draft', 'reviewed')", name="ck_encounter_status"),
                     CheckConstraint("status != 'reviewed' OR (assessment IS NOT NULL AND review IS NOT NULL)", name="ck_review_requires_assessment"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    data: Mapped[dict] = mapped_column(JSON)
    assessment: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    review: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (ForeignKeyConstraint(["facility_id", "encounter_id", "patient_id"], ["encounters.facility_id", "encounters.id", "encounters.patient_id"]),
                     CheckConstraint("status IN ('requested', 'accepted', 'completed', 'cancelled')", name="ck_referral_status"),
                     CheckConstraint("urgency IN ('routine', 'soon', 'urgent', 'emergency')", name="ck_referral_urgency"),
                     CheckConstraint("status != 'completed' OR (outcome IS NOT NULL AND length(outcome) > 0)", name="ck_referral_outcome"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    destination: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="requested")
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (UniqueConstraint("facility_id", "sequence"), Index("ix_audit_facility_created", "facility_id", "created_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    previous_hash: Mapped[str] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64))


class ConsultationRequest(Base):
    """Immutable durable outbox; delivery may be safely repeated."""
    __tablename__ = "consultation_requests"
    __table_args__ = (ForeignKeyConstraint(["facility_id", "encounter_id", "patient_id"], ["encounters.facility_id", "encounters.id", "encounters.patient_id"]),
                     UniqueConstraint("requested_by", "idempotency_key"), UniqueConstraint("facility_id", "id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    encounter_id: Mapped[str] = mapped_column(String(36), index=True)
    patient_id: Mapped[str] = mapped_column(String(36))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(36))
    payload_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsultationDisposition(Base):
    """Primary clinician's final action; never rewrites an earlier assessment."""
    __tablename__ = "consultation_dispositions"
    request_id: Mapped[str] = mapped_column(ForeignKey("consultation_requests.id"), primary_key=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    opinion_hash: Mapped[str] = mapped_column(String(64))
    opinion_snapshot: Mapped[dict] = mapped_column(JSON)
    action: Mapped[str] = mapped_column(String(20))
    action_taken: Mapped[str] = mapped_column(Text)
    current_encounter_version: Mapped[int] = mapped_column(Integer)
    snapshot_was_stale: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(["facility_id", "request_id"], ["consultation_requests.facility_id", "consultation_requests.id"]), CheckConstraint("action IN ('accepted', 'modified', 'not_followed')", name="ck_consult_disposition_action"),)
