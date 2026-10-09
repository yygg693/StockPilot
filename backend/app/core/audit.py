"""Audit logging service - records all sensitive operations to the audit_log table.

Audit entries are append-only (no update/delete API exposed).
Every trade, AI auto-execute, config change, and watchlist modification
should be logged via log_audit().
"""
from __future__ import annotations

import contextlib
import json
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.db.session import get_db

logger = get_logger("audit")


async def log_audit(
    action: str,
    target: str = "",
    detail: dict[str, Any] | None = None,
    user_id: str = "anonymous",
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    """Write an audit log entry. Fire-and-forget: errors are logged but never raised.

    Args:
        action: What happened, e.g. "trade.buy", "ai.auto_execute", "config.save"
        target: The affected entity, e.g. stock code "600519"
        detail: Additional context as a dict (stored as JSON)
        user_id: Who did it (placeholder until auth system is built)
        ip_address: Request source IP
        user_agent: Request User-Agent string
    """
    try:
        db = await get_db()
        await db.execute(
            """INSERT INTO audit_log (user_id, action, target, detail, ip_address, user_agent)
               VALUES (?,?,?,?,?,?)""",
            (
                user_id,
                action,
                target,
                json.dumps(detail or {}, ensure_ascii=False, default=str),
                ip_address,
                user_agent,
            ),
        )
        await db.commit()
        logger.info("audit.logged", action=action, target=target)
    except Exception as e:
        # Audit logging must never break the business operation
        logger.error("audit.log_failed", action=action, error=str(e))


async def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    action_filter: str = "",
) -> list[dict]:
    """Read audit logs (newest first). Optional action prefix filter."""
    db = await get_db()
    if action_filter:
        cursor = await db.execute(
            """SELECT * FROM audit_log WHERE action LIKE ?
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (f"{action_filter}%", limit, offset),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        item = dict(r)
        # Parse detail JSON for convenience
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            item["detail"] = json.loads(item.get("detail", "{}"))
        result.append(item)
    return result


def extract_request_info(request) -> dict[str, str]:
    """Extract IP and User-Agent from a FastAPI Request for audit logging."""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    return {"ip_address": ip, "user_agent": ua}
