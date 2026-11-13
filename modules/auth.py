"""Username/password auth backed by Neon `app_users` table."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from modules.db import connection, db_configured, ensure_schema

# Demo accounts seeded into Neon (passwords hashed at rest).
DEFAULT_USERS = [
    {"username": "admin", "password": "Admin@123", "display_name": "Admin"},
    {"username": "sagar", "password": "Sagar@123", "display_name": "Sagar"},
    {"username": "demo", "password": "Demo@123", "display_name": "Demo User"},
]


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return salt, digest


def _verify(password: str, salt: str, password_hash: str) -> bool:
    _, digest = _hash_password(password, salt)
    return hmac.compare_digest(digest, password_hash)


def ensure_users_table() -> bool:
    if not db_configured():
        return False
    ensure_schema()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
    return True


def seed_default_users() -> int:
    """Insert the 3 demo users if missing. Returns how many were inserted."""
    if not ensure_users_table():
        return 0
    inserted = 0
    with connection() as conn:
        with conn.cursor() as cur:
            for u in DEFAULT_USERS:
                cur.execute("SELECT 1 FROM app_users WHERE username = %s", (u["username"],))
                if cur.fetchone():
                    continue
                salt, digest = _hash_password(u["password"])
                cur.execute(
                    """
                    INSERT INTO app_users (username, display_name, salt, password_hash)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (u["username"], u["display_name"], salt, digest),
                )
                inserted += 1
    return inserted


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    username = (username or "").strip().lower()
    password = password or ""
    if not username or not password:
        return None
    if not ensure_users_table():
        return None
    seed_default_users()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT username, display_name, salt, password_hash
                FROM app_users
                WHERE lower(username) = %s
                """,
                (username,),
            )
            row = cur.fetchone()
    if not row:
        return None
    uname, display_name, salt, password_hash = row
    if not _verify(password, salt, password_hash):
        return None
    return {"username": uname, "display_name": display_name}
