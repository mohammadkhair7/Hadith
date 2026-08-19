"""JWT auth helpers (HS256 access + refresh tokens, bcrypt password hashing)."""
import datetime as dt
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from ..config import settings


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), pw_hash.encode())
    except ValueError:
        return False


def _token(payload: dict[str, Any], minutes: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {**payload, "iat": now, "exp": now + dt.timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def make_tokens(user_id: int, email: str, is_admin: bool) -> dict[str, str]:
    base = {"sub": str(user_id), "email": email, "admin": is_admin}
    return {
        "access_token": _token({**base, "type": "access"}, settings.access_token_minutes),
        "refresh_token": _token({**base, "type": "refresh"}, settings.refresh_token_days * 24 * 60),
        "token_type": "bearer",
    }


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")
    if payload.get("type") != expected_type:
        raise HTTPException(401, "wrong token type")
    return payload


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    return auth[7:] if auth.startswith("Bearer ") else None


def current_user(request: Request) -> dict[str, Any]:
    token = _bearer(request)
    if not token:
        raise HTTPException(401, "authentication required")
    p = decode_token(token)
    return {"user_id": int(p["sub"]), "email": p["email"], "is_admin": bool(p.get("admin"))}


def optional_user(request: Request) -> dict[str, Any] | None:
    token = _bearer(request)
    if not token:
        return None
    try:
        p = decode_token(token)
    except HTTPException:
        return None
    return {"user_id": int(p["sub"]), "email": p["email"], "is_admin": bool(p.get("admin"))}


def admin_user(user: dict = Depends(current_user)) -> dict[str, Any]:
    if not user["is_admin"]:
        raise HTTPException(403, "admin access required")
    return user
