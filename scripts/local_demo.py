"""Prepare or serve an isolated synthetic demo. Never intended for deployment."""
from pathlib import Path
import json
import os
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
CONFIG = RUNTIME / "demo-access.json"
sys.path.insert(0, str(ROOT / "backend"))


def environment():
    RUNTIME.mkdir(exist_ok=True)
    if CONFIG.exists():
        config = json.loads(CONFIG.read_text())
    else:
        config = {"email": "demo@ncdai.example", "password": secrets.token_urlsafe(24),
                  "secret": secrets.token_urlsafe(48), "url": "http://127.0.0.1:5173",
                  "database_url": f"sqlite:///{(RUNTIME / 'demo.db').as_posix()}"}
        CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.environ.update(NCDAI_ENV="local", DATABASE_URL=config["database_url"],
                      NCDAI_SECRET_KEY=config["secret"], NCDAI_SECURE_COOKIES="false",
                      NCDAI_ALLOW_DEMO_SEED="false")
    # External AI remains an explicit configuration. A key alone never enables it.
    return config


if __name__ == "__main__":
    config = environment()
    if "--prepare" in sys.argv:
        from alembic.config import Config
        from alembic import command
        os.chdir(ROOT / "backend")
        command.upgrade(Config("alembic.ini"), "head")
        from app.main import create_app
        from app.seed import provision_user
        from app.models import User
        from app.models import AuthSession
        from app.security import hash_password
        from app.audit import append_audit
        from sqlalchemy import select, delete
        app = create_app()
        with app.state.session_factory() as db:
            user = db.scalar(select(User).where(User.email == config["email"]))
            if user and "--rotate-access" in sys.argv:
                config["password"] = secrets.token_urlsafe(24)
                config["secret"] = secrets.token_urlsafe(48)
                user.password_hash = hash_password(config["password"])
                db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
                append_audit(db, user, "demo.credentials_rotate", "user", user.id)
                db.commit()
                CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
            if not user:
                provision_user(db, email=config["email"], password=config["password"],
                               display_name="Demo clinician", role="supervisor",
                               facility_name="NCDAI demonstration clinic")
        app.state.engine.dispose()
        print("Synthetic demo prepared. Credentials are in ignored .runtime/demo-access.json.")
    else:
        import uvicorn
        uvicorn.run("app.main:app", host="127.0.0.1", port=8010, access_log=False)
