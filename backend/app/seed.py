"""Explicit local-only synthetic facility provisioning; never run on production."""
import argparse
import getpass
import os
from sqlalchemy import select
from .config import Settings
from .db import make_engine, make_sessions
from .models import Facility, User, uid
from .security import hash_password
from .audit import append_audit


def provision_user(db, *, email, password, display_name, role="clinician", facility=None, facility_name="Synthetic demonstration facility"):
    if len(password) < 14:
        raise ValueError("Choose a password with at least 14 characters")
    if role not in {"clinician", "supervisor", "admin"}:
        raise ValueError("Unsupported role")
    if db.scalar(select(User).where(User.email == email.lower())):
        raise ValueError("User already exists; provisioning never overwrites accounts")
    facility = facility or Facility(id=uid(), name=facility_name)
    db.add(facility)
    db.flush()
    user = User(id=uid(), facility_id=facility.id, email=email.lower(), password_hash=hash_password(password), display_name=display_name, role=role)
    db.add(user)
    db.flush()
    append_audit(db, user, "user.provision", "user", user.id)
    db.commit()
    return user


def main():
    parser = argparse.ArgumentParser(description="Explicit local synthetic NCDAI account provisioning")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Synthetic clinician")
    parser.add_argument("--role", choices=["clinician", "supervisor", "admin"], default="clinician")
    parser.add_argument("--facility-name", default="Synthetic demonstration facility")
    args = parser.parse_args()
    settings = Settings()
    settings.validate()
    if settings.environment != "local" or not settings.allow_demo_seed:
        parser.error("Provisioning requires NCDAI_ENV=local and NCDAI_ALLOW_DEMO_SEED=true")
    password = os.getenv("NCDAI_SEED_PASSWORD") or getpass.getpass("New local password (minimum 14 characters): ")
    engine = make_engine(settings.database_url)
    with make_sessions(engine)() as db:
        facility = db.scalar(select(Facility).where(Facility.name == args.facility_name))
        user = provision_user(db, email=args.email, password=password, display_name=args.name, role=args.role, facility=facility, facility_name=args.facility_name)
    print(f"Created explicit {user.role} account {user.email} in synthetic facility. No patient data added. Sign in using the password you supplied.")
    print("Disable NCDAI_ALLOW_DEMO_SEED after provisioning. Never enter real patient information in this release.")


if __name__ == "__main__":
    main()
