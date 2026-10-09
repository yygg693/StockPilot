"""AI analysis result persistence — save and retrieve analysis history."""
from __future__ import annotations

import json

from backend.app.core.logging import get_logger
from backend.app.db.session import get_db

logger = get_logger("ai_persistence")


async def save_analysis(
    code: str,
    signal: str,
    score: int = 0,
    confidence: int = 0,
    indicators: dict | None = None,
    ai_commentary: str = "",
    model: str = "",
) -> int | None:
    """Save an AI analysis result to the database.

    Returns the inserted row ID, or None on failure.
    """
    try:
        db = await get_db()
        cursor = await db.execute(
            """INSERT INTO ai_analysis_log
               (code, signal, score, confidence, indicators_json, ai_commentary, model)
               VALUES (?,?,?,?,?,?,?)""",
            (
                code,
                signal,
                score,
                confidence,
                json.dumps(indicators or {}, ensure_ascii=False, default=str),
                ai_commentary,
                model,
            ),
        )
        await db.commit()
        logger.info("ai.analysis_saved", code=code, signal=signal, confidence=confidence)
        return cursor.lastrowid
    except Exception as e:
        logger.error("ai.save_failed", code=code, error=str(e))
        return None


async def get_analysis_history(
    code: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Retrieve AI analysis history, optionally filtered by stock code."""
    db = await get_db()
    if code:
        cursor = await db.execute(
            """SELECT * FROM ai_analysis_log WHERE code = ?
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (code, limit, offset),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM ai_analysis_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["indicators"] = json.loads(item.get("indicators_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            item["indicators"] = {}
        del item["indicators_json"]
        result.append(item)
    return result


async def get_latest_analysis(code: str) -> dict | None:
    """Get the most recent analysis for a given stock code."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM ai_analysis_log WHERE code = ? ORDER BY id DESC LIMIT 1",
        (code,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["indicators"] = json.loads(item.get("indicators_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        item["indicators"] = {}
    del item["indicators_json"]
    return item
