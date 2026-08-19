from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from ..db import db, q1
from ..services.auth import (current_user, decode_token, hash_password,
                             make_tokens, verify_password)

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


@router.post("/register")
def register(body: Credentials):
    if len(body.password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    with db() as conn:
        exists = q1(conn, "SELECT 1 FROM users WHERE email=%s", (body.email,))
        if exists:
            raise HTTPException(409, "email already registered")
        # first registered user becomes admin (bootstrap)
        first = q1(conn, "SELECT count(*) AS n FROM users")["n"] == 0
        row = conn.execute(
            "INSERT INTO users (email, pw_hash, is_admin) VALUES (%s,%s,%s) "
            "RETURNING user_id, email, is_admin",
            (body.email, hash_password(body.password), first),
        ).fetchone()
        conn.commit()
    return make_tokens(row["user_id"], row["email"], row["is_admin"])


@router.post("/login")
def login(body: Credentials):
    with db() as conn:
        row = q1(conn, "SELECT user_id, email, pw_hash, is_admin FROM users WHERE email=%s",
                 (body.email,))
    if not row or not verify_password(body.password, row["pw_hash"]):
        raise HTTPException(401, "invalid credentials")
    return make_tokens(row["user_id"], row["email"], row["is_admin"])


@router.post("/refresh")
def refresh(body: RefreshBody):
    p = decode_token(body.refresh_token, expected_type="refresh")
    return make_tokens(int(p["sub"]), p["email"], bool(p.get("admin")))


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
