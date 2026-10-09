"""Authentication routes: register, login, me."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.app.core.audit import extract_request_info, log_audit
from backend.app.core.exceptions import AuthError, ValidationError
from backend.app.core.logging import get_logger
from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    extract_token_from_header,
    hash_password,
    verify_password,
)
from backend.app.db.session import get_db

logger = get_logger("auth")
router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/register")
async def register(req: RegisterRequest, request: Request):
    """Register a new user account."""
    db = await get_db()

    # Check if username already exists
    cursor = await db.execute("SELECT id FROM users WHERE username=?", (req.username,))
    if await cursor.fetchone():
        raise ValidationError(f"用户名 {req.username} 已存在")

    # Hash password
    pw_hash, salt = hash_password(req.password)

    # Insert user
    await db.execute(
        """INSERT INTO users (username, password_hash, password_salt, display_name)
           VALUES (?,?,?,?)""",
        (req.username, pw_hash, salt, req.display_name or req.username),
    )
    await db.commit()

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="auth.register",
        target=req.username,
        detail={"display_name": req.display_name},
        **info,
    )

    logger.info("auth.register", username=req.username)
    return {"data": {"message": "注册成功，请登录"}}


@router.post("/auth/login")
async def login(req: LoginRequest, request: Request):
    """Login and return JWT access token."""
    db = await get_db()

    cursor = await db.execute(
        "SELECT id, username, password_hash, password_salt, display_name, role, is_active FROM users WHERE username=?",
        (req.username,),
    )
    row = await cursor.fetchone()

    if not row:
        raise AuthError("用户名或密码错误")

    if not row["is_active"]:
        raise AuthError("账号已被禁用")

    if not verify_password(req.password, row["password_hash"], row["password_salt"]):
        raise AuthError("用户名或密码错误")

    # Update last login time
    await db.execute(
        "UPDATE users SET last_login=datetime('now','localtime') WHERE id=?",
        (row["id"],),
    )
    await db.commit()

    # Generate JWT token
    token = create_access_token(row["id"], row["username"], row["role"])

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="auth.login",
        target=req.username,
        **info,
    )

    logger.info("auth.login", username=req.username)
    return {"data": {
        "token": token,
        "user": {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
        },
        "message": "登录成功",
    }}


@router.get("/auth/me")
async def me(request: Request):
    """Get current user info from JWT token."""
    from backend.app.core.config import get_settings
    settings = get_settings()

    # When auth is disabled, return anonymous admin user
    if not settings.security.auth_enabled:
        return {"data": {
            "user_id": 0,
            "username": "admin",
            "display_name": "Admin",
            "role": "admin",
        }}

    token = extract_token_from_header(request.headers.get("authorization"))
    if not token:
        raise AuthError("未提供认证令牌")

    payload = decode_access_token(token)
    if not payload:
        raise AuthError("认证令牌无效或已过期")

    return {"data": {
        "user_id": int(payload["sub"]),
        "username": payload["username"],
        "role": payload["role"],
    }}
