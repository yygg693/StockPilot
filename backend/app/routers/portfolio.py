"""Portfolio import routes: import real holdings from external apps (Ant Fortune etc)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.db.session import get_db
from backend.app.deps import get_current_user

logger = get_logger("portfolio")
router = APIRouter(dependencies=[Depends(get_current_user)])


class PositionItem(BaseModel):
    code: str
    name: str = ""
    qty: float = Field(gt=0)
    cost: float = Field(gt=0)
    asset_type: str = "stock"  # stock / fund


class ManualImportRequest(BaseModel):
    positions: list[PositionItem]
    cash: float | None = None


class TextImportRequest(BaseModel):
    text: str
    cash: float | None = None


class ImageImportRequest(BaseModel):
    image_base64: str
    cash: float | None = None


@router.post("/portfolio/import-manual")
async def import_manual(req: ManualImportRequest):
    """Import positions manually entered by user."""
    db = await get_db()
    imported = 0
    for p in req.positions:
        code = _normalize_code(p.code)
        cursor = await db.execute(
            "SELECT id FROM positions WHERE code=? AND type=?", (code, p.asset_type)
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE positions SET qty=?, cost=?, name=? WHERE id=?",
                (p.qty, p.cost, p.name or "", row["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO positions (code, name, type, qty, cost) VALUES (?,?,?,?,?)",
                (code, p.name, p.asset_type, p.qty, p.cost),
            )
        imported += 1

    if req.cash is not None:
        await db.execute(
            "INSERT OR IGNORE INTO account (id, cash, initial_cash) VALUES (1, ?, ?)",
            (req.cash, req.cash),
        )
        await db.execute(
            "UPDATE account SET cash=?, initial_cash=? WHERE id=1", (req.cash, req.cash)
        )

    await db.commit()
    logger.info("portfolio.import_manual", count=imported)

    # Auto-add to watchlist
    for p in req.positions:
        code = _normalize_code(p.code)
        await db.execute(
            "INSERT OR IGNORE INTO watchlist (code, name, type) VALUES (?,?,?)",
            (code, p.name or "", p.asset_type),
        )
    await db.commit()

    return {"ok": True, "imported": imported, "message": f"成功导入 {imported} 条持仓"}


@router.post("/portfolio/import-text")
async def import_text(req: TextImportRequest):
    """Parse pasted text from Ant Fortune / broker apps and import positions."""
    positions = _parse_positions_text(req.text)
    if not positions:
        return {
            "ok": False,
            "imported": 0,
            "message": "未能从文本中识别出持仓信息，请检查格式",
        }

    db = await get_db()
    imported = 0
    for p in positions:
        code = _normalize_code(p["code"])
        cursor = await db.execute(
            "SELECT id FROM positions WHERE code=? AND type=?", (code, p["type"])
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE positions SET qty=?, cost=?, name=? WHERE id=?",
                (p["qty"], p["cost"], p["name"], row["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO positions (code, name, type, qty, cost) VALUES (?,?,?,?,?)",
                (code, p["name"], p["type"], p["qty"], p["cost"]),
            )
        imported += 1

    if req.cash is not None:
        await db.execute(
            "INSERT OR IGNORE INTO account (id, cash, initial_cash) VALUES (1, ?, ?)",
            (req.cash, req.cash),
        )
        await db.execute(
            "UPDATE account SET cash=?, initial_cash=? WHERE id=1", (req.cash, req.cash)
        )

    await db.commit()
    logger.info("portfolio.import_text", count=imported)

    # Auto-add to watchlist
    for p in positions:
        code = _normalize_code(p["code"])
        await db.execute(
            "INSERT OR IGNORE INTO watchlist (code, name, type) VALUES (?,?,?)",
            (code, p.get("name", ""), p.get("type", "stock")),
        )
    await db.commit()

    return {
        "ok": True,
        "imported": imported,
        "positions": positions,
        "message": f"从文本识别并导入 {imported} 条持仓",
    }


@router.post("/portfolio/import-image")
async def import_image(req: ImageImportRequest):
    """Use AI vision to parse a screenshot of holdings from Ant Fortune etc."""
    settings = get_settings()
    if not settings.ai.configured:
        return {
            "ok": False,
            "message": "AI未配置，无法进行截图识别，请使用文本粘贴或手动录入",
        }

    import httpx

    prompt = (
        "你是一个金融数据提取助手。请从这张持仓截图中提取所有持仓信息。\n\n"
        "严格按以下JSON数组格式返回（不要加任何其他内容）：\n"
        '[{"code": "代码", "name": "名称", "qty": 数量, "cost": 成本价, "type": "stock或fund"}]\n\n'
        "规则：\n"
        "1. code: 6位数字代码（如600519、161725）\n"
        "2. name: 股票/基金名称\n"
        "3. qty: 持有数量/份额（数字）\n"
        "4. cost: 成本价/成本净值（数字）\n"
        "5. type: 如果是基金写fund，股票写stock\n"
        '6. 如果截图中有可用余额/现金，额外加一个对象：{"cash": 数字}\n'
        "7. 只返回JSON，不要解释"
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as ai_client:
            r = await ai_client.post(
                f"{settings.ai.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai.api_key}"},
                json={
                    "model": settings.ai.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{req.image_base64}"
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": 1000,
                },
            )
            r.raise_for_status()
            data = r.json()
            raw = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("portfolio.image_ai_failed", error=str(e))
        return {
            "ok": False,
            "message": f"截图识别失败: {str(e)[:100]}，请改用文本粘贴",
        }

    # Parse AI response
    import json as _json

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        items = _json.loads(raw)
    except _json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                items = _json.loads(m.group())
            except _json.JSONDecodeError:
                return {"ok": False, "message": "AI识别结果解析失败，请改用文本粘贴"}
        else:
            return {"ok": False, "message": "AI未能识别出持仓信息，请改用文本粘贴"}

    # Separate cash from positions
    cash_val = None
    positions = []
    for item in items:
        if "cash" in item and "code" not in item:
            cash_val = float(item["cash"])
        elif "code" in item:
            positions.append(item)

    if not positions:
        return {"ok": False, "message": "截图中未识别到持仓数据"}

    # Save to DB
    db = await get_db()
    imported = 0
    for p in positions:
        code = _normalize_code(str(p.get("code", "")))
        ptype = p.get("type", "stock")
        qty = float(p.get("qty", 0))
        cost = float(p.get("cost", 0))
        name = p.get("name", "")
        if qty <= 0 or cost <= 0:
            continue
        cursor = await db.execute(
            "SELECT id FROM positions WHERE code=? AND type=?", (code, ptype)
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE positions SET qty=?, cost=?, name=? WHERE id=?",
                (qty, cost, name, row["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO positions (code, name, type, qty, cost) VALUES (?,?,?,?,?)",
                (code, name, ptype, qty, cost),
            )
        imported += 1

    final_cash = req.cash if req.cash is not None else cash_val
    if final_cash is not None:
        await db.execute(
            "INSERT OR IGNORE INTO account (id, cash, initial_cash) VALUES (1, ?, ?)",
            (final_cash, final_cash),
        )
        await db.execute(
            "UPDATE account SET cash=?, initial_cash=? WHERE id=1",
            (final_cash, final_cash),
        )

    await db.commit()
    logger.info("portfolio.import_image", count=imported)

    # Auto-add to watchlist
    for p in positions:
        code = _normalize_code(str(p.get("code", "")))
        await db.execute(
            "INSERT OR IGNORE INTO watchlist (code, name, type) VALUES (?,?,?)",
            (code, p.get("name", ""), p.get("type", "stock")),
        )
    await db.commit()

    return {
        "ok": True,
        "imported": imported,
        "positions": positions,
        "message": f"截图识别成功，导入 {imported} 条持仓",
    }


@router.get("/portfolio/status")
async def portfolio_status():
    """Check if user has imported real portfolio data."""
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM positions")
    row = await cursor.fetchone()
    count = row["cnt"] if row else 0
    cursor2 = await db.execute("SELECT cash, initial_cash FROM account WHERE id=1")
    acc = await cursor2.fetchone()
    return {
        "data": {
            "has_portfolio": count > 0,
            "position_count": count,
            "cash": float(acc["cash"]) if acc else 0,
        }
    }


@router.post("/portfolio/clear")
async def clear_portfolio():
    """Clear all positions (for re-import)."""
    db = await get_db()
    await db.execute("DELETE FROM positions")
    await db.commit()
    return {"ok": True, "message": "已清空持仓，可重新导入"}


# --- Helpers ---


def _normalize_code(code: str) -> str:
    """Add market prefix if missing (6->sh, else->sz)."""
    code = code.strip()
    if code.startswith(("sh", "sz")):
        return code
    if code.startswith("6"):
        return "sh" + code
    return "sz" + code


def _parse_positions_text(text: str) -> list[dict]:
    """Parse positions from pasted text (Ant Fortune / broker app format)."""
    positions = []
    lines = text.strip().split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Try to find a code (6 digits) in this line
        code_match = re.search(r"\b(\d{6})\b", line)
        if code_match:
            code = code_match.group(1)
            # Extract name: text before or after the code
            name = line[: code_match.start()].strip() or line[code_match.end() :].strip()
            name = re.sub(r"[()（）\[\]]", " ", name).strip()

            # Determine asset type
            asset_type = "fund" if any(
                k in line for k in ["基金", "指数", "LOF", "ETF", "混合", "债券"]
            ) or code.startswith(("1", "5")) else "stock"

            # Look for qty and cost in this line or next few lines
            qty = 0.0
            cost = 0.0

            # Search current + next 4 lines for qty/cost
            block = "\n".join(lines[i : i + 5])

            # qty patterns
            qty_m = re.search(r"(?:份额|持有|数量|股)[：:\s]*([\d,.]+)", block)
            if qty_m:
                qty = float(qty_m.group(1).replace(",", ""))
            else:
                # Try plain number after code
                nums = re.findall(r"[\d,.]+", line[code_match.end() :])
                if nums:
                    qty = float(nums[0].replace(",", ""))

            # cost patterns (longer terms first to avoid partial match)
            cost_m = re.search(
                r"(?:成本净值|成本价|买入价|成本|净值)[：:\s]*([\d,.]+)", block
            )
            if cost_m:
                cost = float(cost_m.group(1).replace(",", ""))
            else:
                nums = re.findall(r"[\d,.]+", line[code_match.end() :])
                if len(nums) > 1:
                    cost = float(nums[1].replace(",", ""))

            if qty > 0 and cost > 0:
                positions.append(
                    {
                        "code": code,
                        "name": name,
                        "qty": qty,
                        "cost": cost,
                        "type": asset_type,
                    }
                )

        i += 1

    return positions
