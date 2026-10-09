"""AI Briefing & Monitor services for StockPilot Phase 2."""
from datetime import datetime

import httpx

from backend.app.core.config import get_settings

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"


async def _call_ai(prompt: str, system: str = "") -> str:
    """Call DeepSeek for text generation."""
    settings = get_settings()
    if not settings.ai.configured or not settings.ai.enabled:
        return "[AI未配置] 请在设置中填入 DeepSeek API Key"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(DEEPSEEK_URL, json={
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "max_tokens": 800,
            "temperature": 0.7,
        }, headers={"Authorization": f"Bearer {settings.ai.api_key}"})
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _fetch_indices() -> list[dict]:
    """Fetch major index quotes from Tencent."""
    codes = "sh000001,sz399001,sz399006"
    url = f"https://qt.gtimg.cn/q={codes}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        text = resp.text
    results = []
    for line in text.strip().split("\n"):
        if "~" not in line:
            continue
        parts = line.split("~")
        if len(parts) < 40:
            continue
        results.append({
            "name": parts[1],
            "price": float(parts[3]) if parts[3] else 0,
            "change_pct": float(parts[32]) if parts[32] else 0,
            "volume": parts[36] if len(parts) > 36 else "",
        })
    return results


async def generate_briefing(positions: list[dict], watchlist: list[dict]) -> dict:
    """Generate daily AI briefing."""
    indices = await _fetch_indices()

    # Build context
    idx_text = "\n".join(f"  {i['name']}: {i['price']} ({'+' if i['change_pct']>0 else ''}{i['change_pct']}%)" for i in indices)

    pos_text = "无持仓"
    if positions:
        pos_lines = []
        for p in positions[:10]:
            pnl = (p.get("price", 0) - p.get("cost", 0)) * p.get("qty", 0)
            pnl_pct = ((p.get("price", 0) / p.get("cost", 1)) - 1) * 100 if p.get("cost") else 0
            pos_lines.append(f"  {p.get('name','')}({p.get('code','')}): {p.get('qty',0)}股, 成本{p.get('cost',0):.2f}, 现价{p.get('price',0):.2f}, 盈亏{pnl:+.0f}元({pnl_pct:+.1f}%)")
        pos_text = "\n".join(pos_lines)

    watch_text = "无自选"
    if watchlist:
        watch_text = ", ".join(f"{w.get('name','')}({w.get('code','')})" for w in watchlist[:8])

    now = datetime.now()
    prompt = f"""今天是{now.year}年{now.month}月{now.day}日，请生成一份简洁的每日投资简报。

【大盘指数】
{idx_text}

【我的持仓】
{pos_text}

【自选股】
{watch_text}

要求：
1. 用3-5句话总结今日大盘走势
2. 对持仓给出简短操作建议（持有/减仓/加仓）
3. 提醒需要关注的风险或机会
4. 语气专业但易懂，不要太长"""

    system = "你是StockPilot的AI投资顾问，擅长A股市场分析。回复简洁有力，不超过200字。用纯文本，禁止使用*#等markdown符号。"

    summary = await _call_ai(prompt, system)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "indices": indices,
        "summary": summary,
        "position_count": len(positions),
        "watchlist_count": len(watchlist),
    }


async def check_alerts(positions: list[dict]) -> list[dict]:
    """Check positions for alert conditions."""
    alerts = []
    if not positions:
        return alerts

    # Fetch current prices for all positions
    codes = []
    for p in positions:
        code = p.get("code", "")
        if code.startswith("6"):
            codes.append(f"sh{code}")
        else:
            codes.append(f"sz{code}")

    if not codes:
        return alerts

    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        text = resp.text

    quotes = {}
    for line in text.strip().split("\n"):
        if "~" not in line:
            continue
        parts = line.split("~")
        if len(parts) < 40:
            continue
        code = parts[2]
        quotes[code] = {
            "name": parts[1],
            "price": float(parts[3]) if parts[3] else 0,
            "change_pct": float(parts[32]) if parts[32] else 0,
            "turnover": float(parts[38]) if len(parts) > 38 and parts[38] else 0,
        }

    for p in positions:
        code = p.get("code", "")
        q = quotes.get(code)
        if not q:
            continue
        cost = p.get("cost", 0)
        price = q["price"]
        if not cost or not price:
            continue

        pnl_pct = ((price / cost) - 1) * 100
        day_change = q["change_pct"]

        # Stop-loss: -8%
        if pnl_pct <= -8:
            alerts.append({
                "type": "stop_loss",
                "level": "danger",
                "code": code,
                "name": q["name"],
                "message": f"{q['name']} 亏损 {pnl_pct:.1f}%，已触发止损线(-8%)",
                "value": pnl_pct,
            })
        # Take-profit: +20%
        elif pnl_pct >= 20:
            alerts.append({
                "type": "take_profit",
                "level": "success",
                "code": code,
                "name": q["name"],
                "message": f"{q['name']} 盈利 {pnl_pct:.1f}%，可考虑止盈",
                "value": pnl_pct,
            })

        # Daily large move
        if abs(day_change) >= 5:
            direction = "大涨" if day_change > 0 else "大跌"
            alerts.append({
                "type": "large_move",
                "level": "warning",
                "code": code,
                "name": q["name"],
                "message": f"{q['name']} 今日{direction} {day_change:+.1f}%",
                "value": day_change,
            })

    return alerts


async def diagnose_portfolio(positions: list[dict]) -> dict:
    """AI-powered portfolio diagnosis."""
    if not positions:
        # Still provide market-level advice
        indices = await _fetch_indices()
        idx_text = ", ".join(f"{i['name']} {i['price']}({i['change_pct']:+.1f}%)" for i in indices)
        prompt = f"当前无持仓。今日大盘: {idx_text}。请给出建仓建议：现在适合入场吗？推荐关注哪些方向？不超过150字。"
        advice = await _call_ai(prompt, "你是A股投资顾问，给出实用建仓建议。")
        return {"diagnosis": advice or "当前无持仓，建议关注大盘企稳后再择机建仓。", "scores": {"concentration": 100, "diversification": 0, "profitability": 50}}

    # Fetch current prices
    codes = []
    for p in positions:
        code = p.get("code", "")
        if code.startswith("6"):
            codes.append(f"sh{code}")
        else:
            codes.append(f"sz{code}")

    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        text = resp.text

    quotes = {}
    for line in text.strip().split("\n"):
        if "~" not in line:
            continue
        parts = line.split("~")
        if len(parts) < 40:
            continue
        quotes[parts[2]] = {
            "name": parts[1],
            "price": float(parts[3]) if parts[3] else 0,
            "pe": float(parts[39]) if len(parts) > 39 and parts[39] else 0,
            "industry": parts[19] if len(parts) > 19 else "",
        }

    # Calculate metrics
    total_value = 0
    pos_details = []
    for p in positions:
        code = p.get("code", "")
        q = quotes.get(code, {})
        price = q.get("price", p.get("price", 0))
        qty = p.get("qty", 0)
        value = price * qty
        total_value += value
        pos_details.append({
            "code": code,
            "name": q.get("name", p.get("name", "")),
            "value": value,
            "weight": 0,
            "industry": q.get("industry", "未知"),
            "pnl_pct": ((price / p.get("cost", 1)) - 1) * 100 if p.get("cost") else 0,
        })

    if total_value > 0:
        for pd in pos_details:
            pd["weight"] = round(pd["value"] / total_value * 100, 1)

    # Concentration: top1 weight
    top1_weight = max((pd["weight"] for pd in pos_details), default=0)
    # Industry distribution
    industries = {}
    for pd in pos_details:
        ind = pd["industry"] or "未知"
        industries[ind] = industries.get(ind, 0) + pd["weight"]

    # Build prompt
    pos_text = "\n".join(f"  {pd['name']}({pd['code']}): 权重{pd['weight']}%, 行业{pd['industry']}, 盈亏{pd['pnl_pct']:+.1f}%" for pd in pos_details)
    ind_text = ", ".join(f"{k}:{v:.0f}%" for k, v in sorted(industries.items(), key=lambda x: -x[1]))

    prompt = f"""请诊断以下投资组合，给出专业建议：

【持仓明细】(总市值约{total_value:.0f}元)
{pos_text}

【行业分布】
{ind_text}

【集中度】最大单只占比: {top1_weight}%

请从以下维度诊断：
1. 集中度风险（单只/行业是否过度集中）
2. 盈亏状况（是否需要调仓）
3. 配置建议（缺少什么类型的标的）
4. 给出1-2条具体操作建议

简洁回复，不超过250字。不要用markdown格式，不要用*#-等符号，直接用纯文本和数字编号。"""

    system = "你是专业的投资组合顾问，擅长A股资产配置分析。回复用纯文本，禁止使用markdown格式符号。"
    diagnosis = await _call_ai(prompt, system)

    # Scores
    scores = {
        "concentration": max(0, 100 - top1_weight * 1.5),  # Lower concentration = higher score
        "diversification": min(100, len(industries) * 25),
        "profitability": 50 + sum(pd["pnl_pct"] for pd in pos_details) / max(len(pos_details), 1),
    }
    scores = {k: round(max(0, min(100, v))) for k, v in scores.items()}

    return {
        "diagnosis": diagnosis,
        "total_value": round(total_value, 2),
        "position_count": len(pos_details),
        "top1_weight": top1_weight,
        "industries": industries,
        "scores": scores,
        "details": pos_details,
    }
