"""Explicit environment and facility configuration; defaults remain synthetic-only."""
from dataclasses import dataclass, field
import os
import secrets
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("NCDAI_ENV", "local"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./ncdai.db"))
    secret_key: str = field(default_factory=lambda: os.getenv("NCDAI_SECRET_KEY", secrets.token_urlsafe(48)))
    secure_cookies: bool = field(default_factory=lambda: os.getenv("NCDAI_SECURE_COOKIES", "false").lower() == "true")
    public_origin: str = field(default_factory=lambda: os.getenv("NCDAI_PUBLIC_ORIGIN", ""))
    session_hours: int = 8
    cookie_name: str = "ncdai_session"
    allow_demo_seed: bool = field(default_factory=lambda: os.getenv("NCDAI_ALLOW_DEMO_SEED", "false").lower() == "true")
    auto_create_schema: bool = False
    synthetic_only: bool = field(default_factory=lambda: os.getenv("NCDAI_SYNTHETIC_ONLY", "true").lower() != "false")
    clinical_facility_id: str = field(default_factory=lambda: os.getenv("NCDAI_CLINICAL_FACILITY_ID", ""))
    real_patient_ai: bool = field(default_factory=lambda: os.getenv("NCDAI_REAL_PATIENT_AI", "false").lower() == "true")
    incident_contact: str = field(default_factory=lambda: os.getenv("NCDAI_INCIDENT_CONTACT", ""))
    clinical_lead_contact: str = field(default_factory=lambda: os.getenv("NCDAI_CLINICAL_LEAD_CONTACT", ""))
    consultant_database_url: str = field(default_factory=lambda: os.getenv("NCDAI_CONSULTANT_DATABASE_URL", ""))

    def validate(self) -> None:
        if self.environment not in {"local", "test", "production"}:
            raise ValueError("NCDAI_ENV must be local, test or production")
        if not self.synthetic_only:
            from uuid import UUID
            try:
                UUID(self.clinical_facility_id)
            except (ValueError, TypeError):
                raise ValueError("An explicit clinical testing facility ID is required") from None
        if self.real_patient_ai and self.synthetic_only:
            raise ValueError("Real-patient AI requires an explicitly enabled clinical facility")
        if self.consultant_database_url:
            from sqlalchemy.engine import make_url
            primary, consultant = make_url(self.database_url), make_url(self.consultant_database_url)
            def database_identity(url):
                host = (url.host or "").replace("-pooler.", ".")
                if url.drivername.startswith("sqlite"):
                    from pathlib import Path
                    return ("sqlite", str(Path(url.database or ":memory:").resolve()))
                return (host, url.port or 5432, url.database)
            if database_identity(primary) == database_identity(consultant):
                raise ValueError("Consultant records require a separate database")
            if self.environment == "production" and not self.consultant_database_url.startswith("postgresql"):
                raise ValueError("The production consultant database must be PostgreSQL")
        if self.public_origin:
            origin = urlsplit(self.public_origin)
            try:
                _ = origin.port
            except ValueError:
                raise ValueError("NCDAI_PUBLIC_ORIGIN must be an exact HTTP(S) origin") from None
            if (origin.scheme not in {"http", "https"} or not origin.hostname or
                    origin.username or origin.password or origin.path not in {"", "/"} or
                    origin.query or origin.fragment or "*" in origin.netloc or
                    any(c.isspace() for c in self.public_origin)):
                raise ValueError("NCDAI_PUBLIC_ORIGIN must be an exact HTTP(S) origin")
        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if len(self.secret_key) < 48 or len(set(self.secret_key)) < 16:
                raise ValueError("Production requires a strong NCDAI_SECRET_KEY")
            if "NCDAI_SECRET_KEY" not in os.environ:
                raise ValueError("Production requires an explicitly configured NCDAI_SECRET_KEY")
            if not self.secure_cookies or self.allow_demo_seed or self.auto_create_schema:
                raise ValueError("Production requires secure cookies, migrations and disabled demo seed")
            if not self.public_origin.startswith("https://"):
                raise ValueError("Production requires an explicit HTTPS NCDAI_PUBLIC_ORIGIN")
        if self.session_hours < 1 or self.session_hours > 24:
            raise ValueError("Session lifetime must be between 1 and 24 hours")
