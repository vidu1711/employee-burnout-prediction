"""
security.py -- password hashing, sessions and role checks.

Passwords use PBKDF2-HMAC-SHA256 with a per-user random salt. A login creates
a random session token stored server-side and sent as an HttpOnly cookie.
Every protected route re-reads the user's role from the database, so the
browser can never "claim" a role.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request

from . import db

ITERATIONS = 120_000
COOKIE = "pc_session"
SESSION_DAYS = 7


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations).hex()
    return f"pbkdf2${iterations}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(test, digest)
    except Exception:
        return False


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    exp = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    db.run("INSERT INTO sessions(token, user_id, expires_at) VALUES (?,?,?)", (token, user_id, exp))
    return token


def end_session(token: str):
    db.run("DELETE FROM sessions WHERE token=?", (token,))


def user_for_token(token: str):
    if not token:
        return None
    row = db.one(
        "SELECT u.*, t.name AS team_name FROM sessions s JOIN users u ON u.id=s.user_id "
        "LEFT JOIN teams t ON t.id=u.team_id WHERE s.token=? AND s.expires_at>?",
        (token, datetime.now().isoformat(timespec="seconds")),
    )
    return row


def current_user(request: Request) -> dict:
    user = user_for_token(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return user


def require_roles(*roles):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Your role doesn't have access to this.")
        return user
    return dep


# --- very small login throttle (per username, in memory) -------------------
_FAILS: dict = {}
MAX_FAILS, WINDOW = 6, 300


def throttle_check(username: str):
    now = time.time()
    hits = [t for t in _FAILS.get(username, []) if now - t < WINDOW]
    _FAILS[username] = hits
    if len(hits) >= MAX_FAILS:
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a few minutes and try again.")


def throttle_fail(username: str):
    _FAILS.setdefault(username, []).append(time.time())


def throttle_clear(username: str):
    _FAILS.pop(username, None)
