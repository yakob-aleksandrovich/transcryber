"""Password hashing and session-based authentication helpers."""

import logging

import bcrypt
from fastapi import HTTPException, Request

from .db import SessionLocal, User

logger = logging.getLogger("transcryber.auth")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def authenticate(username: str, password: str) -> dict | None:
    """Return a plain dict for the user on success, else None."""
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        if user and verify_password(password, user.password_hash):
            return {"id": user.id, "username": user.username}
    return None


def seed_users(users: list[dict]) -> None:
    """Preseed users from config: create if missing, update password if changed.

    Never deletes users. `users` is a list of {username, password_hash} where the
    hash is a bcrypt string generated with `python -m app.cli hash-password`.
    """
    created = updated = skipped = 0
    with SessionLocal() as session:
        for entry in users:
            username = (entry or {}).get("username")
            password_hash = (entry or {}).get("password_hash")
            if not username or not password_hash:
                logger.warning("Skipping invalid user entry in config: %r", entry)
                skipped += 1
                continue
            if not str(password_hash).startswith("$2"):
                logger.warning(
                    "User '%s': password_hash does not look like a bcrypt hash "
                    "($2...). Did you paste a plaintext password? Skipping.",
                    username,
                )
                skipped += 1
                continue

            existing = session.query(User).filter(User.username == username).first()
            if existing is None:
                session.add(User(username=username, password_hash=password_hash))
                created += 1
            elif existing.password_hash != password_hash:
                existing.password_hash = password_hash
                updated += 1
        session.commit()
    logger.info(
        "User seeding from config: %d created, %d updated, %d skipped "
        "(existing users not listed are left untouched).",
        created,
        updated,
        skipped,
    )


def current_user(request: Request) -> dict:
    """FastAPI dependency: require a logged-in user or raise 401."""
    uid = request.session.get("user_id")
    if uid:
        with SessionLocal() as session:
            user = session.get(User, uid)
            if user:
                return {"id": user.id, "username": user.username}
    raise HTTPException(status_code=401, detail="Not authenticated")
