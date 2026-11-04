"""User repository written with secure defaults."""
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import closing


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt, digest


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def find_user(db_path: str, username: str) -> dict | None:
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id, email FROM users WHERE username = ?", (username,)
        ).fetchone()
    return {"id": row[0], "email": row[1]} if row else None
