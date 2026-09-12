"""Facility-scoped clinical workflows. Production runs behind HTTPS ingress."""
from contextlib import asynccontextmanager, nullcontext
import asyncio
import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import threading
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, update, func, or_, text, delete
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from .config import Settings
from .db import Base, make_engine, make_sessions, SCHEMA_REVISION
from .models import Facility, User, AuthSession, LoginAttempt, Patient, Encounter, Referral, AuditEvent, uid, utcnow
from .schemas import Login, UserCreate, PatientCreate, EncounterCreate, EncounterPatch, ReviewCreate, ReferralCreate, ReferralPatch, AIBriefingRequest
from .security import hash_password, verify_password, token_hash, csrf_token
from .audit import append_audit, verify_chain
from .interop import patient_resource, encounter_bundle, iso
from .middleware import SecurityEnvelope


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    settings.validate()
    engine = make_engine(settings.database_url)
    session_factory = make_sessions(engine)
    write_lock = threading.Lock()
    dummy_password = hash_password(secrets.token_urlsafe(24))
    if settings.auto_create_schema:
        Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(_):
        yield
        engine.dispose()

    api = FastAPI(title="NCDAI 2.0", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs" if settings.environment != "production" else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if settings.environment != "production" else None)
    api.state.settings = settings
    api.state.engine = engine
    api.state.session_factory = session_factory

    @api.middleware("http")
    async def response_security(request, call_next):
        # Cookie-authenticated API has no CORS allowance: frontend uses same-origin /api.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            # A reverse proxy can preserve an internal upstream Host. Trust a
            # configured public origin, never client-supplied forwarding headers.
            allowed_origin = settings.public_origin or str(request.base_url)
            if origin and origin.rstrip("/") != allowed_origin.rstrip("/"):
                return JSONResponse(status_code=403, content={"detail": "Cross-origin mutation is not permitted"})
        response = await call_next(request)
        return response

    api.add_middleware(SecurityEnvelope, secure=settings.secure_cookies)

    @api.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        # Do not reflect password/clinical-note values through validation errors or logs.
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @api.exception_handler(IntegrityError)
    async def conflict_error(_, exc):
        return JSONResponse(status_code=409, content={"detail": "Record conflicts with existing data; reload and retry"})

    @api.exception_handler(OperationalError)
    async def unavailable_error(_, exc):
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable; retry safely"})

    def get_db(request: Request):
        # Local SQLite mutations must serialize before reads to avoid stale audit chains.
        path = request.scope["path"]
        lock = write_lock if engine.dialect.name == "sqlite" and not path.endswith("/ai-briefing") and (request.method != "GET" or "/fhir/" in path) else None
        if lock:
            lock.acquire()
        try:
            with session_factory() as db:
                try:
                    yield db
                except Exception:
                    db.rollback()
                    raise
        finally:
            if lock:
                lock.release()

    DB = Annotated[Session, Depends(get_db)]

    def authenticated(request: Request, db: DB):
        raw = request.cookies.get(settings.cookie_name)
        if not raw or len(raw) > 256:
            raise HTTPException(401, "Sign in required")
        stored = db.get(AuthSession, token_hash(raw))
        if stored is None:
            raise HTTPException(401, "Session expired or invalid")
        # PostgreSQL returns timestamptz in its session timezone; preserve the
        # represented instant. SQLite stores our UTC timestamp without an offset.
        expires_at = stored.expires_at
        expires_at = (expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None
                      else expires_at.astimezone(timezone.utc))
        if expires_at <= utcnow():
            raise HTTPException(401, "Session expired or invalid")
        user = db.get(User, stored.user_id)
        if user is None or not user.active:
            raise HTTPException(401, "Session expired or invalid")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(supplied.encode("utf-8"), csrf_token(raw, settings.secret_key).encode("ascii")):
                raise HTTPException(403, "Valid CSRF token required")
        return user

    AUTH = Annotated[User, Depends(authenticated)]

    def clinical_user(user: AUTH):
        if user.role not in {"clinician", "supervisor"}:
            raise HTTPException(403, "Clinical role required")
        return user

    CLINICAL = Annotated[User, Depends(clinical_user)]

    def privileged(user: AUTH):
        if user.role not in {"supervisor", "admin"}:
            raise HTTPException(403, "Supervisor or administrator role required")
        return user

    PRIVILEGED = Annotated[User, Depends(privileged)]

    def scoped(db, model, entity_id, user):
        obj = db.scalar(select(model).where(model.id == entity_id, model.facility_id == user.facility_id))
        if obj is None:
            raise HTTPException(404, "Record not found")
        return obj

    def user_json(db, user):
        return {"id": user.id, "email": user.email, "display_name": user.display_name,
                "role": user.role, "facility_id": user.facility_id, "facility_name": db.get(Facility, user.facility_id).name}

    def patient_json(patient):
        return {field: getattr(patient, field) for field in ["id", "facility_id", "external_id", "given_name", "family_name", "date_of_birth", "sex", "female_pregnancy_status", "phone", "synthetic"]}

    def encounter_json(encounter):
        obj = {field: getattr(encounter, field) for field in ["id", "patient_id", "version", "status", "data", "assessment", "review"]}
        obj.update(created_at=iso(encounter.created_at), updated_at=iso(encounter.updated_at))
        return obj

    def referral_json(referral, db):
        obj = {field: getattr(referral, field) for field in ["id", "encounter_id", "patient_id", "destination", "reason", "urgency", "status", "outcome"]}
        obj["created_at"] = iso(referral.created_at)
        patient = db.scalar(select(Patient).where(Patient.id == referral.patient_id, Patient.facility_id == referral.facility_id))
        obj["patient_external_id"] = patient.external_id if patient else None
        obj["patient_name"] = f"{patient.given_name} {patient.family_name}" if patient else None
        return obj

    def commit_change(db, user, action, entity_type, entity_id):
        db.flush()
        append_audit(db, user, action, entity_type, entity_id)
        db.commit()

    def change_encounter(db, user, encounter, expected_version, **values):
        if encounter.status == "reviewed":
            raise HTTPException(409, "Reviewed encounters are immutable; create a new encounter")
        result = db.execute(update(Encounter).where(Encounter.id == encounter.id, Encounter.facility_id == user.facility_id,
                            Encounter.version == expected_version, Encounter.status == "draft")
                            .values(version=expected_version + 1, updated_at=utcnow(), **values).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, "Encounter changed; reload before continuing")
        db.expire(encounter)
        db.refresh(encounter)

    @api.get("/api/health/live")
    def live():
        return {"status": "live", "version": "0.1.0", "synthetic_only": settings.synthetic_only}

    @api.get("/api/health/ready")
    def ready(db: DB):
        try:
            db.execute(select(Facility.id).limit(1))
            if not settings.auto_create_schema:
                if db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != SCHEMA_REVISION:
                    raise RuntimeError("Schema migration does not match application")
            from . import clinical, evidence
            if not callable(getattr(clinical, "assess", None)):
                raise RuntimeError("Rules unavailable")
            if not evidence.is_ready():
                raise RuntimeError("Evidence unavailable")
            return {"status": "ready", "database": "connected", "rules": "loaded", "synthetic_only": True}
        except Exception:
            raise HTTPException(503, "Database, migration or clinical evidence unavailable")

    @api.post("/api/auth/login")
    def login(payload: Login, request: Request, response: Response, db: DB):
        email = payload.email.lower()
        ip = request.client.host if request.client else "unknown"
        # Store keyed digests, not email/IP pairs in the throttle table.
        limits = [(f"pair:{email}|{ip}", 10), (f"account:{email}", 30), (f"source:{ip}", 100)]
        keys = [(hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest(), limit) for value, limit in limits]
        # Serialize each throttle bucket across PostgreSQL workers, always in the
        # same order. Local SQLite writes already hold the application lock.
        if engine.dialect.name == "postgresql":
            for key, _ in sorted(keys):
                lock_id = int.from_bytes(bytes.fromhex(key[:16]), "big", signed=True)
                db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
        cutoff = utcnow() - timedelta(minutes=10)
        for key, limit in keys:
            attempts = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == key, LoginAttempt.created_at >= cutoff))
            if attempts >= limit:
                raise HTTPException(429, "Too many sign-in attempts; wait ten minutes", headers={"Retry-After": "600"})
        db.add_all([LoginAttempt(key=key) for key, _ in keys])
        db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < utcnow() - timedelta(days=1)))
        user = db.scalar(select(User).where(User.email == email))
        valid = verify_password(payload.password, user.password_hash if user else dummy_password)
        if not user or not valid or not user.active:
            db.commit()
            raise HTTPException(401, "Email or password is incorrect")
        old = request.cookies.get(settings.cookie_name)
        if old:
            db.execute(delete(AuthSession).where(AuthSession.id == token_hash(old)))
        raw = secrets.token_urlsafe(48)
        db.add(AuthSession(id=token_hash(raw), user_id=user.id, expires_at=utcnow() + timedelta(hours=settings.session_hours)))
        db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
        commit_change(db, user, "auth.login", "user", user.id)
        response.set_cookie(settings.cookie_name, raw, httponly=True, secure=settings.secure_cookies, samesite="strict", path="/api", max_age=settings.session_hours * 3600)
        return {"user": user_json(db, user), "csrf_token": csrf_token(raw, settings.secret_key)}

    @api.get("/api/auth/session")
    def session(request: Request, db: DB, user: AUTH):
        return {"user": user_json(db, user), "csrf_token": csrf_token(request.cookies[settings.cookie_name], settings.secret_key)}

    @api.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response, db: DB, user: AUTH):
        db.execute(delete(AuthSession).where(AuthSession.id == token_hash(request.cookies[settings.cookie_name])))
        commit_change(db, user, "auth.logout", "user", user.id)
        response.delete_cookie(settings.cookie_name, path="/api", httponly=True, secure=settings.secure_cookies, samesite="strict")

    @api.get("/api/users")
    def users(db: DB, user: AUTH):
        if user.role != "admin":
            raise HTTPException(403, "Administrator role required")
        return [user_json(db, item) for item in db.scalars(select(User).where(User.facility_id == user.facility_id).limit(200))]

    @api.post("/api/users", status_code=201)
    def create_user(payload: UserCreate, db: DB, user: AUTH):
        if user.role != "admin":
            raise HTTPException(403, "Administrator role required")
        record = User(id=uid(), facility_id=user.facility_id, email=payload.email.lower(), display_name=payload.display_name,
                      role=payload.role, password_hash=hash_password(payload.password))
        db.add(record)
        commit_change(db, user, "user.create", "user", record.id)
        return user_json(db, record)

    @api.get("/api/patients")
    def patients(db: DB, user: CLINICAL, search: str = Query(default="", max_length=100), limit: int = Query(default=100, ge=1, le=200)):
        query = select(Patient).where(Patient.facility_id == user.facility_id)
        if search:
            value = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(or_(Patient.external_id.ilike(f"%{value}%", escape="\\"), Patient.given_name.ilike(f"%{value}%", escape="\\"), Patient.family_name.ilike(f"%{value}%", escape="\\")))
        return [patient_json(item) for item in db.scalars(query.order_by(Patient.created_at.desc()).limit(limit))]

    @api.post("/api/patients", status_code=201)
    def create_patient(payload: PatientCreate, db: DB, user: CLINICAL):
        patient = Patient(id=uid(), facility_id=user.facility_id, **payload.model_dump())
        db.add(patient)
        commit_change(db, user, "patient.create", "patient", patient.id)
        return patient_json(patient)

    @api.get("/api/patients/{patient_id}")
    def get_patient(patient_id: str, db: DB, user: CLINICAL):
        return patient_json(scoped(db, Patient, patient_id, user))

    @api.get("/api/patients/{patient_id}/encounters")
    def patient_encounters(patient_id: str, db: DB, user: CLINICAL, limit: int = Query(default=100, ge=1, le=200)):
        scoped(db, Patient, patient_id, user)
        return [encounter_json(item) for item in db.scalars(select(Encounter).where(Encounter.patient_id == patient_id, Encounter.facility_id == user.facility_id).order_by(Encounter.created_at.desc()).limit(limit))]

    @api.post("/api/encounters", status_code=201)
    def create_encounter(payload: EncounterCreate, db: DB, user: CLINICAL):
        patient = scoped(db, Patient, payload.patient_id, user)
        today = date.today()
        age = today.year - patient.date_of_birth.year - ((today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day))
        if not 18 <= age <= 120:
            raise HTTPException(422, "Adult clinical scope required")
        encounter = Encounter(id=uid(), facility_id=user.facility_id, patient_id=patient.id, data=payload.data.model_dump(mode="json"), created_by=user.id)
        db.add(encounter)
        commit_change(db, user, "encounter.create", "encounter", encounter.id)
        return encounter_json(encounter)

    @api.get("/api/encounters/{encounter_id}")
    def get_encounter(encounter_id: str, db: DB, user: CLINICAL):
        return encounter_json(scoped(db, Encounter, encounter_id, user))

    @api.patch("/api/encounters/{encounter_id}")
    def patch_encounter(encounter_id: str, payload: EncounterPatch, db: DB, user: CLINICAL):
        encounter = scoped(db, Encounter, encounter_id, user)
        change_encounter(db, user, encounter, payload.expected_version, data=payload.data.model_dump(mode="json"), assessment=None, review=None)
        commit_change(db, user, "encounter.update", "encounter", encounter.id)
        return encounter_json(encounter)

    @api.post("/api/encounters/{encounter_id}/assess")
    def assess_encounter(encounter_id: str, db: DB, user: CLINICAL):
        encounter = scoped(db, Encounter, encounter_id, user)
        if encounter.status == "reviewed":
            raise HTTPException(409, "Reviewed encounters are immutable; create a new encounter")
        patient = scoped(db, Patient, encounter.patient_id, user)
        today = date.today()
        age = today.year - patient.date_of_birth.year - ((today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day))
        from .clinical import assess
        assessment = assess(encounter.data, age, patient.sex)
        assessment.update(id=uid(), generated_at=iso(utcnow()))
        assessment.setdefault("model_info", {"mode": "rules", "status": "no_external_model"})
        change_encounter(db, user, encounter, encounter.version, assessment=assessment, review=None)
        commit_change(db, user, "encounter.assess", "encounter", encounter.id)
        return encounter_json(encounter)

    @api.post("/api/encounters/{encounter_id}/ai-briefing")
    def ai_briefing(encounter_id: str, payload: AIBriefingRequest, request: Request, db: DB, user: CLINICAL):
        encounter = scoped(db, Encounter, encounter_id, user)
        if encounter.status != "draft" or encounter.version != payload.expected_version:
            raise HTTPException(409, "Encounter changed or is reviewed; reload before continuing")
        if not encounter.assessment or encounter.assessment["id"] != payload.assessment_id:
            raise HTTPException(409, "Assessment changed or is missing; reload and reassess")
        patient = scoped(db, Patient, encounter.patient_id, user)
        snapshot = copy.deepcopy(encounter.assessment)
        snapshot.pop("ai_briefing", None)
        synthetic = patient.synthetic
        # Never retain a transaction or SQLite writer lock during provider latency.
        db.rollback()
        from .ai import build_briefing
        briefing = asyncio.run(build_briefing(snapshot, synthetic=synthetic))
        with write_lock if engine.dialect.name == "sqlite" else nullcontext():
            db.expire_all()
            current_user = authenticated(request, db)
            if current_user.role not in {"clinician", "supervisor"}:
                raise HTTPException(403, "Clinical access changed; sign in again")
            current = scoped(db, Encounter, encounter_id, current_user)
            if not current.assessment or current.assessment["id"] != payload.assessment_id:
                raise HTTPException(409, "Assessment changed while preparing briefing; reload")
            updated = {**current.assessment, "ai_briefing": briefing}
            change_encounter(db, current_user, current, payload.expected_version, assessment=updated)
            commit_change(db, current_user, "encounter.ai_briefing", "encounter", current.id)
            return encounter_json(current)

    @api.post("/api/encounters/{encounter_id}/review")
    def review_encounter(encounter_id: str, payload: ReviewCreate, db: DB, user: CLINICAL):
        encounter = scoped(db, Encounter, encounter_id, user)
        if not encounter.assessment or encounter.assessment["id"] != payload.assessment_id:
            raise HTTPException(409, "Assessment changed or is missing; reload and reassess")
        expected = {item["id"] for item in encounter.assessment["recommendations"]}
        actual = [item.recommendation_id for item in payload.decisions]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise HTTPException(422, "Exactly one decision is required for every current recommendation")
        snapshot = {"reviewer_id": user.id, "reviewer_name": user.display_name, "reviewed_at": iso(utcnow()),
                    "assessment_id": payload.assessment_id, "input_version": payload.expected_version,
                    "input_snapshot": encounter.data, "assessment_snapshot": encounter.assessment,
                    "decisions": [item.model_dump(mode="json") for item in payload.decisions], "note": payload.note}
        change_encounter(db, user, encounter, payload.expected_version, status="reviewed", review=snapshot)
        commit_change(db, user, "encounter.review", "encounter", encounter.id)
        return encounter_json(encounter)

    @api.post("/api/encounters/{encounter_id}/referrals", status_code=201)
    def create_referral(encounter_id: str, payload: ReferralCreate, db: DB, user: CLINICAL):
        encounter = scoped(db, Encounter, encounter_id, user)
        referral = Referral(id=uid(), facility_id=user.facility_id, encounter_id=encounter.id, patient_id=encounter.patient_id, **payload.model_dump())
        db.add(referral)
        commit_change(db, user, "referral.create", "referral", referral.id)
        return referral_json(referral, db)

    @api.get("/api/referrals")
    def referrals(db: DB, user: CLINICAL, limit: int = Query(default=100, ge=1, le=200)):
        return [referral_json(item, db) for item in db.scalars(select(Referral).where(Referral.facility_id == user.facility_id).order_by(Referral.created_at.desc()).limit(limit))]

    @api.patch("/api/referrals/{referral_id}")
    def patch_referral(referral_id: str, payload: ReferralPatch, db: DB, user: CLINICAL):
        referral = scoped(db, Referral, referral_id, user)
        allowed = {"requested": {"accepted", "cancelled"}, "accepted": {"completed", "cancelled"}, "completed": set(), "cancelled": set()}
        if payload.status not in allowed.get(referral.status, set()):
            raise HTTPException(409, "Referral transition is not permitted")
        result = db.execute(update(Referral).where(Referral.id == referral.id, Referral.facility_id == user.facility_id, Referral.status == referral.status)
                            .values(status=payload.status, outcome=payload.outcome).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, "Referral changed; reload before continuing")
        db.expire(referral)
        db.refresh(referral)
        commit_change(db, user, "referral." + payload.status, "referral", referral.id)
        return referral_json(referral, db)

    @api.get("/api/dashboard")
    def dashboard(db: DB, user: AUTH):
        patient_count = db.scalar(select(func.count()).select_from(Patient).where(Patient.facility_id == user.facility_id))
        count = db.scalar(select(func.count()).select_from(Encounter).where(Encounter.facility_id == user.facility_id))
        reviewed = db.scalar(select(func.count()).select_from(Encounter).where(Encounter.facility_id == user.facility_id, Encounter.status == "reviewed"))
        open_referrals = db.scalar(select(func.count()).select_from(Referral).where(Referral.facility_id == user.facility_id, Referral.status.in_(["requested", "accepted"])))
        urgent = db.scalar(select(func.count()).select_from(Encounter).where(Encounter.facility_id == user.facility_id, Encounter.assessment["urgency"].as_string().in_(["urgent", "emergency"])))
        return {"patients": patient_count, "encounters": count, "reviewed": reviewed, "open_referrals": open_referrals, "urgent_assessments": urgent}

    @api.get("/api/audit/verify")
    def audit_verify(db: DB, user: PRIVILEGED):
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == user.facility_id).order_by(AuditEvent.sequence)))
        return {"valid": verify_chain(events), "events": len(events), "head_hash": events[-1].chain_hash if events else None,
                "limitation": "Hash chain detects modification against retained history; external anchoring is required to detect full-history rewrite or tail deletion."}

    @api.get("/api/audit")
    def audit(db: DB, user: PRIVILEGED, limit: int = Query(default=100, ge=1, le=200)):
        return [{"id": event.id, "action": event.action, "entity_type": event.entity_type, "entity_id": event.entity_id,
                 "actor_id": event.actor_id, "created_at": iso(event.created_at), "chain_hash": event.chain_hash}
                for event in db.scalars(select(AuditEvent).where(AuditEvent.facility_id == user.facility_id).order_by(AuditEvent.sequence.desc()).limit(limit))]

    @api.get("/api/fhir/Patient/{patient_id}")
    def fhir_patient(patient_id: str, db: DB, user: CLINICAL):
        patient = scoped(db, Patient, patient_id, user)
        output = patient_resource(patient)
        commit_change(db, user, "export.fhir_patient", "patient", patient.id)
        return JSONResponse(output, media_type="application/fhir+json")

    @api.get("/api/fhir/Bundle/{encounter_id}")
    def fhir_bundle(encounter_id: str, db: DB, user: CLINICAL):
        encounter = scoped(db, Encounter, encounter_id, user)
        patient = scoped(db, Patient, encounter.patient_id, user)
        output = encounter_bundle(patient, encounter)
        commit_change(db, user, "export.fhir_bundle", "encounter", encounter.id)
        return JSONResponse(output, media_type="application/fhir+json")

    return api


app = create_app()
