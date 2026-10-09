"""AI analysis routes: single-call comprehensive analysis."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.exceptions import AIServiceError
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.core.risk import get_risk_manager
from backend.app.deps import get_current_user
from backend.app.services.ai_briefing import check_alerts, diagnose_portfolio, generate_briefing
from backend.app.services.ai_context import build_ai_context
from backend.app.services.ai_persistence import get_analysis_history, get_latest_analysis, save_analysis
from backend.app.services.ai_signals import ai_filter_signals, generate_signals
from backend.app.services.ai_tools import TOOL_DEFINITIONS, execute_tool
from backend.app.services.data_tencent import fetch_quote_batch

logger = get_logger("ai")

# Default stock universe (popular A-shares) when watchlist is empty
_DEFAULT_UNIVERSE = [
    "600519", "000858", "601318", "600036", "000333",
    "002594", "600900", "601899", "300750", "000001",
    "600276", "601012", "002475", "600809", "000568",
    "601888", "300059", "002415", "600585", "601668",
]


router = APIRouter(dependencies=[Depends(get_current_user)])

_SYSTEM_PROMPT = """你是一位资深投资顾问，请对用户提供的股票进行综合分析。
要求：
1. 用简洁的中文回答，不要使用markdown格式（不要用*、#、-等符号）
2. 分三段：基本面分析、技术面分析、操作建议
3. 每段2-3句话，总计不超过300字
4. 给出明确的方向判断（看多/看空/震荡）和信心等级（高/中/低）
5. 直接输出文字，不要任何格式标记"""


class AnalyzeRequest(BaseModel):
    code: str
    name: str = ""
    context: str = ""


@router.post("/ai/analyze")
async def analyze(req: AnalyzeRequest):
    settings = get_settings()
    if not settings.ai.configured or not settings.ai.enabled:
        raise AIServiceError("AI service not configured or disabled")

    client = get_http_client()
    context = req.context or f"Stock: {req.name} ({req.code})"

    user_msg = f"请分析以下股票：{req.name}（{req.code}）。{context}"

    try:
        r = await client.post(
            f"{settings.ai.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.ai.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.7,
                "max_tokens": 800,
            },
            timeout=90.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        # Clean any residual markdown
        text = text.replace("**", "").replace("###", "").replace("##", "").replace("#", "").replace("*", "")
        text = text.replace("`", "")
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                line = line[2:]
            if line.startswith("* "):
                line = line[2:]
            lines.append(line)
        text = "\n".join(lines).strip()

        return {"data": {
            "code": req.code,
            "name": req.name,
            "summary": text,
            "analyses": None,
        }}
    except Exception as e:
        logger.error("ai.call_failed", error=str(e))
        raise AIServiceError("AI analysis failed", detail=str(e)) from e


# ---------- Market Summary ----------

_MARKET_PROMPT = """你是一位市场分析师。根据提供的今日A股市场数据（指数、涨跌家数、涨跌幅榜），用150字以内给出一段市场速览。
要求：纯文字，不用markdown，不用列表，语气专业简洁，包含大盘方向、市场情绪、板块亮点或风险提示。"""

_INDEX_CODES = ['sh000001', 'sz399001', 'sz399006']
_BREADTH_POOL = ','.join([
    'sh600519','sh601318','sh600036','sh600276','sh601166','sh600030','sh601888','sh600809',
    'sh601012','sh600900','sh601899','sh600585','sh600031','sh601668','sh600048','sh601398',
    'sh600887','sh600309','sh601601','sh600050','sz000858','sz000333','sz002714','sz000651',
    'sz002415','sz300750','sz002594','sz000568','sz002304','sz300059','sz002475','sz000725',
    'sz002027','sz300124','sz000063','sz002230','sz300015','sz002352','sz300760','sz000002',
    'sh688981','sh688012','sh688036','sh688111','sh688008','sh688009','sh688169','sh688396',
    'sh603259','sh603501','sh603986','sh600745','sh601728','sh600150','sh601985','sh600028',
    'sh601857','sh600029','sh601688','sh600000','sh601211','sh600016','sh601328','sh600015',
])


@router.get('/ai/market-summary')
async def market_summary():
    settings = get_settings()
    if not settings.ai.configured or not settings.ai.enabled:
        return {'data': {'summary': None, 'error': 'AI service not configured'}}

    client = get_http_client()

    # Gather market data
    try:
        quotes = await fetch_quote_batch(client, _INDEX_CODES + _BREADTH_POOL.split(','))
    except Exception as e:
        logger.error('market_summary.fetch_failed', error=str(e))
        return {'data': {'summary': None, 'error': 'Failed to fetch market data'}}

    # Build index summary
    idx_lines = []
    for code in _INDEX_CODES:
        q = quotes.get(code)
        if q:
            idx_lines.append(f"{q.get('name', code)}: {q.get('price', '--')} ({'+' if (q.get('change_pct') or 0) >= 0 else ''}{q.get('change_pct', 0):.2f}%)")

    # Breadth from pool
    up = down = flat = 0
    movers = []
    for code in _BREADTH_POOL.split(','):
        q = quotes.get(code)
        if not q:
            continue
        pct = q.get('change_pct') or 0
        if pct > 0.5:
            up += 1
        elif pct < -0.5:
            down += 1
        else:
            flat += 1
        movers.append((q.get('name', code), pct))

    movers.sort(key=lambda x: x[1], reverse=True)
    top3 = ', '.join([f"{n}(+{p:.1f}%)" if p > 0 else f"{n}({p:.1f}%)" for n, p in movers[:3]])
    bot3 = ', '.join([f"{n}({p:.1f}%)" for n, p in movers[-3:]])

    context = f"""今日指数: {'; '.join(idx_lines)}
样本涨跌: 上涨{up}家, 下跌{down}家, 平盘{flat}家
领涨: {top3}
领跌: {bot3}"""

    try:
        r = await client.post(
            f'{settings.ai.base_url}/chat/completions',
            headers={
                'Authorization': f'Bearer {settings.ai.api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': settings.ai.model,
                'messages': [
                    {'role': 'system', 'content': _MARKET_PROMPT},
                    {'role': 'user', 'content': context},
                ],
                'temperature': 0.7,
                'max_tokens': 300,
            },
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data['choices'][0]['message']['content'].strip()
        return {'data': {'summary': text, 'error': None}}
    except Exception as e:
        logger.error('market_summary.ai_failed', error=str(e))
        return {'data': {'summary': None, 'error': str(e)}}


# ---------- Multi-turn AI Chat ----------

_CHAT_SYSTEM_PROMPT = """你是StockPilot的智能投资顾问AI。你精通A股、基金、ETF投资，能分析个股基本面、技术面，也能分析基金的持仓、经理风格、业绩归因。

你的能力：
1. 分析股票和基金的投资价值
2. 给出买入/卖出/持有建议（附理由和风险提示）
3. 解读市场走势和板块轮动
4. 评估投资组合风险
5. 回答任何投资相关问题

规则：
- 用简洁中文回答，不用markdown格式
- 每次回答控制在200字以内
- 给出明确方向判断，不要模棱两可
- 必须提示投资风险
- 如果用户问的是具体基金/股票，结合提供的数据回答"""


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = []
    context: str = ""


@router.post("/ai/chat")
async def ai_chat(req: ChatRequest):
    settings = get_settings()
    if not settings.ai.configured or not settings.ai.enabled:
        raise AIServiceError("AI service not configured or disabled")

    client = get_http_client()

    # Build rich context automatically
    auto_context = await build_ai_context(
        page=req.context.split("|")[0] if "|" in req.context else "",
        asset_code=req.context.split("|")[1] if "|" in req.context and len(req.context.split("|")) > 1 else "",
        asset_name=req.context.split("|")[2] if "|" in req.context and len(req.context.split("|")) > 2 else "",
    )
    # Merge with any manual context passed from frontend
    full_context = auto_context
    if req.context and "|" not in req.context:
        full_context = req.context + "\n" + auto_context

    messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": f"以下是用户当前的实时投资数据：\n{full_context}"})

    history = req.messages[-12:] if len(req.messages) > 12 else req.messages
    for msg in history:
        role = "assistant" if msg.role == "assistant" else "user"
        messages.append({"role": role, "content": msg.content})

    try:
        # Function calling loop (max 3 rounds)
        for _round in range(3):
            r = await client.post(
                f"{settings.ai.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai.model,
                    "messages": messages,
                    "tools": TOOL_DEFINITIONS,
                    "temperature": 0.7,
                    "max_tokens": 600,
                },
                timeout=60.0,
            )
            r.raise_for_status()
            data = r.json()
            choice = data["choices"][0]
            msg = choice["message"]

            # If AI wants to call tools
            if msg.get("tool_calls"):
                # Add assistant message with tool_calls
                messages.append(msg)
                # Execute each tool call
                import json as _json
                for tc in msg["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    fn_args = _json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                    logger.info("ai.tool_call", tool=fn_name, args=str(fn_args))
                    result = await execute_tool(fn_name, fn_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
                continue  # Loop again with tool results

            # Final text response
            text = msg.get("content", "").strip()
            text = text.replace("**", "").replace("###", "").replace("##", "").replace("#", "").replace("`", "").replace("*", "")
            lines = []
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    line = line[2:]
                if line.startswith("* "):
                    line = line[2:]
                lines.append(line)
            text = "\n".join(lines).strip()
            return {"data": {"reply": text}}

        # Fallback if loop exhausted
        return {"data": {"reply": "抱歉，处理超时，请重试。"}}
    except Exception as e:
        logger.error("ai.chat_failed", error=str(e))
        raise AIServiceError("AI chat failed", detail=str(e)) from e


class StreamRequest(BaseModel):
    messages: list[ChatMessage] = []
    context: str = ""


@router.post("/ai/stream")
async def ai_stream(req: StreamRequest):
    """SSE streaming AI chat - returns text/event-stream."""
    settings = get_settings()
    if not settings.ai.configured or not settings.ai.enabled:
        raise AIServiceError("AI service not configured or disabled")

    auto_context = await build_ai_context(
        page=req.context.split("|")[0] if "|" in req.context else "",
        asset_code=req.context.split("|")[1] if "|" in req.context and len(req.context.split("|")) > 1 else "",
        asset_name=req.context.split("|")[2] if "|" in req.context and len(req.context.split("|")) > 2 else "",
    )
    full_context = auto_context
    if req.context and "|" not in req.context:
        full_context = req.context + "\n" + auto_context

    messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": f"以下是用户当前的实时投资数据：\n{full_context}"})

    history = req.messages[-12:] if len(req.messages) > 12 else req.messages
    for msg in history:
        role = "assistant" if msg.role == "assistant" else "user"
        messages.append({"role": role, "content": msg.content})

    import json as _json

    import httpx

    async def event_generator():
        try:
            async with httpx.AsyncClient() as stream_client, stream_client.stream(
                "POST",
                f"{settings.ai.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 600,
                    "stream": True,
                },
                timeout=90.0,
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(payload)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            # Clean markdown on the fly
                            content = content.replace("**", "").replace("`", "").replace("*", "")
                            yield f"data: {_json.dumps({'text': content}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        logger.warning("ai.stream.chunk_parse_failed", error=str(e))
                        continue
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# === Phase 2: Proactive Management ===

@router.get("/ai/briefing")
async def get_briefing():
    """Generate daily AI briefing with market + portfolio summary."""
    from backend.app.services.ai_context import get_trade_db, get_watchlist_store
    db = await get_trade_db()
    positions = db.get("positions", [])
    watchlist = list(await get_watchlist_store())
    result = await generate_briefing(positions, watchlist)
    return {"data": result}


@router.get("/ai/alerts")
async def get_alerts():
    """Check positions for alert conditions (stop-loss, take-profit, large moves)."""
    from backend.app.services.ai_context import get_trade_db
    db = await get_trade_db()
    positions = db.get("positions", [])
    alerts = await check_alerts(positions)
    return {"data": alerts}


# Diagnosis cache (memory + disk, survives restart)
_diag_cache: dict = {"data": None, "ts": 0}
_DIAG_TTL = 300  # 5 minutes


@router.post("/ai/diagnose")
async def post_diagnose(refresh: bool = False):
    """AI-powered portfolio diagnosis. Cached 5min, persisted to disk."""
    import time as _time

    from backend.app.core.disk_cache import disk_get, disk_set
    now = _time.time()

    # 1) Memory cache
    if not refresh and _diag_cache["data"] and now - _diag_cache["ts"] < _DIAG_TTL:
        return {"data": _diag_cache["data"], "cached": True}

    # 2) Disk cache (survives restart)
    if not refresh:
        disked = disk_get("diagnose", _DIAG_TTL)
        if disked is not None:
            _diag_cache["data"] = disked
            _diag_cache["ts"] = now
            return {"data": disked, "cached": True}

    from backend.app.services.ai_context import get_trade_db
    db = await get_trade_db()
    positions = db.get("positions", [])
    result = await diagnose_portfolio(positions)

    _diag_cache["data"] = result
    _diag_cache["ts"] = now
    disk_set("diagnose", result)

    return {"data": result}


# === Phase 3: Auto Trading ===

# Signal cache: avoid regenerating AI signals on every page load (memory + disk)
_signal_cache: dict = {"data": None, "ts": 0}
_SIGNAL_TTL = 300  # 5 minutes


@router.get("/ai/signals")
async def get_signals(codes: str = "", refresh: bool = False):
    """Generate trading signals. Pass comma-separated codes, or empty for watchlist. Cached 5min, persisted to disk."""
    import time as _time

    from backend.app.core.disk_cache import disk_get, disk_set

    cache_key = codes or "__watchlist__"
    now = _time.time()

    # 1) Memory cache
    if (not refresh and _signal_cache.get("key") == cache_key
            and _signal_cache["data"] and now - _signal_cache["ts"] < _SIGNAL_TTL):
        return {"data": _signal_cache["data"], "cached": True}

    # 2) Disk cache (survives restart)
    if not refresh:
        disked = disk_get(f"signals_{cache_key}", _SIGNAL_TTL)
        if disked is not None:
            _signal_cache["data"] = disked
            _signal_cache["ts"] = now
            _signal_cache["key"] = cache_key
            return {"data": disked, "cached": True}

    from backend.app.services.ai_context import get_watchlist_store
    if codes:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        wl = await get_watchlist_store()
        code_list = [w.get("code", "") for w in wl if w.get("code")]
    if not code_list:
        code_list = _DEFAULT_UNIVERSE
    signals = await generate_signals(code_list)
    commentary = await ai_filter_signals(signals)
    result = {"signals": signals, "commentary": commentary}

    # P2-5: Persist analysis results to database (fire-and-forget)
    settings = get_settings()
    for s in signals[:10]:
        try:
            await save_analysis(
                code=s["code"],
                signal=s["signal"],
                score=s.get("score", 0),
                confidence=s.get("confidence", 0),
                indicators={
                    "reasons": s.get("reasons", []),
                    "rsi": s.get("rsi"),
                    "macd": s.get("macd"),
                    "boll": s.get("boll"),
                    "kdj": s.get("kdj"),
                },
                ai_commentary=commentary[:200] if commentary else "",
                model=settings.ai.model,
            )
        except Exception as e:
            logger.warning("ai.signal_persist_failed", error=str(e))
            # Persistence is best-effort, never block signal delivery

    # Store in cache (memory + disk)
    _signal_cache["data"] = result
    _signal_cache["ts"] = now
    _signal_cache["key"] = cache_key
    disk_set(f"signals_{cache_key}", result)

    return {"data": result}


@router.get("/ai/risk-status")
async def get_risk_status():
    """Get current risk management status."""
    rm = get_risk_manager()
    return {"data": rm.get_status()}


@router.post("/ai/auto-execute")
async def post_auto_execute(request: Request):
    """Auto-execute: generate signals -> risk check -> create trade PROPOSAL (not executed).

    P0-2 fix: Trades are NOT executed directly. Returns a proposal that requires
    user confirmation via /ai/confirm-execute.
    """
    from backend.app.core.audit import extract_request_info, log_audit
    from backend.app.core.trade_proposal import create_proposal, format_proposal_response
    from backend.app.services.ai_context import get_trade_db, get_watchlist_store

    db = await get_trade_db()
    rm = get_risk_manager()
    wl = await get_watchlist_store()
    code_list = [w.get("code", "") for w in wl if w.get("code")]
    if not code_list:
        code_list = _DEFAULT_UNIVERSE

    # Step 1: Generate signals
    signals = await generate_signals(code_list)

    # Step 2: Build proposed sells (stop-loss/take-profit) - NOT executed
    proposed_sells = []
    skipped = []
    positions = db.get("positions", [])

    for p in positions:
        code = p.get("code", "")
        sell_check = rm.check_sell(code, db)
        if sell_check["should_sell"]:
            proposed_sells.append({
                "action": "sell",
                "code": code,
                "name": p.get("name", ""),
                "qty": p.get("qty", 0),
                "price": p.get("price", 0),
                "reason": sell_check["reason"],
            })

    # Step 3: Build proposed buys (strong_buy only, with risk check) - NOT executed
    proposed_buys = []
    buy_signals = [s for s in signals if s["signal"] in ("strong_buy", "buy") and s["score"] >= 2]
    for sig in buy_signals[:3]:  # Max 3 buys per run
        code = sig["code"]
        price = sig["price"]
        # Calculate position size: 15% of total assets
        total = db.get("cash", 0) + sum(p.get("qty", 0) * p.get("price", 0) for p in db.get("positions", []))
        amount = total * 0.15
        qty = int(amount / price / 100) * 100
        if qty < 100:
            skipped.append({"code": code, "reason": "资金不足一手"})
            continue

        risk_check = rm.check_buy(code, qty * price, db)
        if not risk_check.allowed:
            skipped.append({"code": code, "reason": risk_check.reason})
            continue

        # Use adjusted amount if risk manager adjusted it
        actual_amount = risk_check.adjusted_amount or (qty * price)
        actual_qty = int(actual_amount / price / 100) * 100
        if actual_qty < 100:
            skipped.append({"code": code, "reason": "调整后不足一手"})
            continue

        proposed_buys.append({
            "action": "buy",
            "code": code,
            "name": code,
            "qty": actual_qty,
            "price": price,
            "amount": round(actual_qty * price, 2),
            "reason": ", ".join(sig["reasons"]),
        })

    # Get AI commentary on signals
    commentary = ""
    if signals:
        commentary = await ai_filter_signals(signals)

    # Audit log - proposal creation
    info = extract_request_info(request)
    await log_audit(
        action="ai.auto_execute.proposal",
        target="signals",
        detail={
            "proposed_sells": len(proposed_sells),
            "proposed_buys": len(proposed_buys),
            "skipped": skipped,
            "signals_count": len(signals),
        },
        **info,
    )

    # Create proposal (NOT executing trades)
    signals_summary = [
        {"code": s["code"], "signal": s["signal"], "score": s["score"], "reasons": s["reasons"], "price": s["price"]}
        for s in signals[:8]
    ]
    proposal = create_proposal(
        sells=proposed_sells,
        buys=proposed_buys,
        signals_summary=signals_summary,
        commentary=commentary,
    )
    return format_proposal_response(proposal)


@router.post("/ai/confirm-execute")
async def confirm_execute(body: dict, request: Request):
    """Confirm and execute a previously generated trade proposal.

    Required: {"proposal_id": "xxx", "confirmed": true}
    Optional: {"selected_codes": ["600519", ...]} to execute only a subset.
    """
    from backend.app.core.audit import extract_request_info, log_audit
    from backend.app.core.trade_proposal import consume_proposal
    from backend.app.services.ai_tools import execute_tool

    proposal_id = body.get("proposal_id", "")
    confirmed = body.get("confirmed", False)
    selected_codes = body.get("selected_codes", [])  # empty = execute all

    if not confirmed:
        return {"data": {"executed": [], "message": "用户未确认，取消执行"}}

    proposal = consume_proposal(proposal_id)
    if not proposal:
        return {"data": {"executed": [], "message": "提案不存在或已过期，请重新生成"}}

    executed = []
    failed = []

    # Execute sells
    for s in proposal["sells"]:
        if selected_codes and s["code"] not in selected_codes:
            continue
        result = await execute_tool("execute_trade", {
            "action": "sell", "code": s["code"],
            "name": s.get("name", ""), "amount": s.get("qty", 0) * s.get("price", 0),
        })
        import json as _json
        res = _json.loads(result)
        if res.get("success"):
            executed.append({"action": "sell", "code": s["code"], "result": res["message"]})
        else:
            failed.append({"action": "sell", "code": s["code"], "error": res.get("error", "unknown")})

    # Execute buys
    for b in proposal["buys"]:
        if selected_codes and b["code"] not in selected_codes:
            continue
        result = await execute_tool("execute_trade", {
            "action": "buy", "code": b["code"],
            "name": b.get("name", ""), "amount": b.get("amount", b.get("qty", 0) * b.get("price", 0)),
        })
        import json as _json
        res = _json.loads(result)
        if res.get("success"):
            executed.append({"action": "buy", "code": b["code"], "result": res["message"]})
        else:
            failed.append({"action": "buy", "code": b["code"], "error": res.get("error", "unknown")})

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="ai.auto_execute.confirmed",
        target=proposal_id,
        detail={"executed": executed, "failed": failed},
        **info,
    )

    return {"data": {
        "executed": executed,
        "failed": failed,
        "message": f"确认执行完成: {len(executed)}笔成功, {len(failed)}笔失败",
    }}


# === P2-5: AI Analysis History ===

@router.get("/ai/analysis-history")
async def analysis_history(code: str = "", limit: int = 50, offset: int = 0):
    """Retrieve AI analysis history, optionally filtered by stock code."""
    history = await get_analysis_history(code=code, limit=limit, offset=offset)
    return {"data": history}


@router.get("/ai/latest-analysis")
async def latest_analysis(code: str):
    """Get the most recent AI analysis for a given stock code."""
    result = await get_latest_analysis(code)
    return {"data": result}
