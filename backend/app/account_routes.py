"""Audited account lifecycle without weakening clinical or facility boundaries.

Install alongside the application's existing authentication dependencies. Login
must lock its user row before checking a password and issuing a new session; this
serializes credential issuance with password change and account deactivation.
"""
from datetime import timedelta
import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .account_schemas import PasswordChange, AccountStatusChange
from .models import AuthSession, LoginAttempt, User, utcnow
from .security import hash_password, token_hash, verify_password


def install_account_routes(api, *, get_db, authenticated, commit_change, user_json, settings):
    DB = Annotated[Session, Depends(get_db)]
    AUTH = Annotated[User, Depends(authenticated)]

    def lock_accounts(db, facility_id):
        # Serialize simultaneous administrator decisions and password changes.
        # SQLite mutations already use the application's process-wide write lock.
        if db.bind.dialect.name == "postgresql":
            key = int.from_bytes(hashlib.sha256(("account-lifecycle:" + facility_id).encode()).digest()[:8],
                                 "big", signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    def fresh_actor(request, db, previous):
        lock_accounts(db, previous.facility_id)
        db.expire_all()
        # Session revocation/role changes while waiting must take effect here.
        return authenticated(request, db)

    def locked_user(db, user_id, facility_id):
        user = db.scalar(select(User).where(User.id == user_id, User.facility_id == facility_id)
                         .with_for_update().execution_options(populate_existing=True))
        if user is None:
            raise HTTPException(404, "Account not found")
        return user

    @api.post("/api/auth/change-password")
    def change_password(payload: PasswordChange, request: Request, db: DB, user: AUTH):
        user = fresh_actor(request, db, user)
        user = locked_user(db, user.id, user.facility_id)
        key = hmac.new(settings.secret_key.encode(), ("password-change:" + user.id).encode(), hashlib.sha256).hexdigest()
        cutoff = utcnow() - timedelta(minutes=10)
        attempts = db.scalar(select(func.count()).select_from(LoginAttempt)
                             .where(LoginAttempt.key == key, LoginAttempt.created_at >= cutoff))
        if attempts >= 5:
            raise HTTPException(429, "Too many password-change attempts; wait ten minutes", headers={"Retry-After": "600"})
        db.add(LoginAttempt(key=key))
        if not verify_password(payload.current_password, user.password_hash):
            commit_change(db, user, "user.password_change_failed", "user", user.id)
            raise HTTPException(400, "Current password is incorrect")
        user.password_hash = hash_password(payload.new_password)
        user.password_change_required = False
        current_session = token_hash(request.cookies[settings.cookie_name])
        revoked = db.execute(delete(AuthSession).where(AuthSession.user_id == user.id,
                                                      AuthSession.id != current_session)).rowcount
        commit_change(db, user, "user.password_change", "user", user.id)
        return {"status": "password_changed", "other_sessions_revoked": revoked}

    @api.patch("/api/users/{user_id}/status")
    def change_status(user_id: str, payload: AccountStatusChange, request: Request, db: DB, user: AUTH):
        if user.role != "admin":
            raise HTTPException(403, "Administrator role required")
        user = fresh_actor(request, db, user)
        if user.role != "admin":
            raise HTTPException(403, "Administrator role required")
        target = locked_user(db, user_id, user.facility_id)
        if not payload.active:
            if target.active and target.role == "admin":
                administrators = db.scalar(select(func.count()).select_from(User).where(
                    User.facility_id == user.facility_id, User.role == "admin", User.active.is_(True)))
                if administrators <= 1:
                    raise HTTPException(409, "The last active administrator cannot be deactivated")
            if target.id == user.id:
                raise HTTPException(409, "You cannot deactivate your own account")
        if target.active == payload.active:
            return {**user_json(db, target), "active": target.active}
        target.active = payload.active
        # Reactivation never restores an old authenticated session. This also
        # clears residual sessions from previously manual account administration.
        db.execute(delete(AuthSession).where(AuthSession.user_id == target.id))
        commit_change(db, user, "user.reactivate" if payload.active else "user.deactivate", "user", target.id)
        return {**user_json(db, target), "active": target.active}
