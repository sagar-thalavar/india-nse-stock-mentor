"""Username/password auth backed by Neon `app_users` table."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Any

from modules.db import connection, db_configured, ensure_schema


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


def create_user(username: str, password: str, display_name: str | None = None) -> tuple[bool, str]:
    """Create a user in Neon. Returns (ok, message)."""
    username = (username or "").strip().lower()
    password = password or ""
    display_name = (display_name or username).strip() or username

    if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
        return False, "Username must be 3–32 characters (letters, numbers, underscore)."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if not ensure_users_table():
        return False, "Database is not configured."

    salt, digest = _hash_password(password)
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM app_users WHERE lower(username) = %s", (username,))
                if cur.fetchone():
                    return False, "That username is already taken."
                cur.execute(
                    """
                    INSERT INTO app_users (username, display_name, salt, password_hash)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (username, display_name, salt, digest),
                )
        return True, "Account created. You can sign in now."
    except Exception as exc:
        return False, f"Could not create user: {type(exc).__name__}"


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    username = (username or "").strip().lower()
    password = password or ""
    if not username or not password:
        return None
    if not ensure_users_table():
        return None
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
