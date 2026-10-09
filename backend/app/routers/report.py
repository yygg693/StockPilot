"""Daily report routes: generate market summary report."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from backend.app.core.cache import TTLCache
from backend.app.core.config import get_settings
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.deps import get_cache
from backend.app.services.data_tencent import parse_index_overview

logger = get_logger("report")
router = APIRouter()

_INDEX_CODES = ["sh000001", "sz399001", "sz399006"]


@router.get("/report/daily")
async def daily_report(cache: TTLCache = Depends(get_cache)):
    """Generate a daily market summary report."""
    cache_key = "report_daily"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    settings = get_settings()

    # Fetch index data
    indices = await parse_index_overview(client, _INDEX_CODES)

    # Build report sections
    now = datetime.now()
    report = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "indices": indices,
        "summary": "",
        "sections": [],
    }

    # Generate summary from index data
    if indices:
        sh = next((i for i in indices if "000001" in i.get("code", "")), None)
        sz = next((i for i in indices if "399001" in i.get("code", "")), None)
        cy = next((i for i in indices if "399006" in i.get("code", "")), None)

        parts = []
        if sh:
            direction = "上涨" if sh.get("change_pct", 0) > 0 else "下跌"
            parts.append(f"上证指数{direction}{abs(sh.get('change_pct', 0)):.2f}%，报{sh.get('price', 0):.2f}点")
        if sz:
            direction = "上涨" if sz.get("change_pct", 0) > 0 else "下跌"
            parts.append(f"深证成指{direction}{abs(sz.get('change_pct', 0)):.2f}%")
        if cy:
            direction = "上涨" if cy.get("change_pct", 0) > 0 else "下跌"
            parts.append(f"创业板指{direction}{abs(cy.get('change_pct', 0)):.2f}%")

        report["summary"] = "，".join(parts) + "。"

    # Fetch top movers via Tencent API
    try:
        import re as _re
        pool = "sh600519,sh601318,sz000858,sh600036,sz300750,sh601012,sz002594,sh600900,sz000001,sh601899,sh600030,sz002475,sh600276,sz300059,sh601888,sz000333,sh600809,sz002304,sh601166,sh600887,sh601398,sh600000,sz000002,sh601668,sh600585,sz002415,sh601601,sh600104,sz000568,sh601088"
        r = await client.get(f"https://qt.gtimg.cn/q={pool}", headers={"Referer": "https://finance.qq.com"}, timeout=8.0)
        movers = []
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            m = _re.match(r'v_(\w+)="(.*)"', line)
            if not m:
                continue
            fields = m.group(2).split("~")
            if len(fields) < 35:
                continue
            try:
                movers.append({"code": m.group(1), "name": fields[1], "change_pct": float(fields[32]) if fields[32] else 0})
            except (ValueError, IndexError):
                continue
        movers.sort(key=lambda x: x["change_pct"], reverse=True)
        report["top_gainers"] = movers[:5]
        report["top_losers"] = movers[-5:][::-1]
    except Exception:
        report["top_gainers"] = []
        report["top_losers"] = []

    # Fetch financial news from Sina
    try:
        r = await client.get(
            "https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": "153", "lid": "2516", "k": "", "num": "15", "page": "1"},
            timeout=8.0,
        )
        news_data = r.json()
        items = news_data.get("result", {}).get("data", [])
        report["news"] = [
            {
                "title": item.get("title", ""),
                "time": item.get("ctime", ""),
                "url": item.get("url", ""),
                "source": item.get("media_name", "新浪财经"),
            }
            for item in items[:15]
            if item.get("title")
        ]
    except Exception:
        report["news"] = []

    # Try AI-enhanced report if configured (after news fetch so AI can reference headlines)
    if settings.ai.configured:
        try:
            ai_result = await _generate_ai_report(client, settings, report)
            report["ai_summary"] = ai_result["text"]
            report["key_news_indices"] = ai_result["key_indices"]
        except Exception as e:
            logger.warning("report.ai_failed", error=str(e))
            report["ai_summary"] = ""
            report["key_news_indices"] = []

    await cache.set(cache_key, report, ttl=300)
    return {"data": report}


async def _generate_ai_report(client, settings, report: dict) -> dict:
    """Use AI to generate market commentary and identify key news."""
    import json as _json

    import httpx

    news_list = report.get("news", [])[:15]
    news_titles = "\n".join(
        f"[{i}] {n['title']}" for i, n in enumerate(news_list)
    ) or "暂无新闻数据"

    prompt = f"""你是一位资深A股分析师。根据以下今日市场数据和新闻，完成两件事。

今日行情：{report.get("summary", "")}

今日要闻（编号对应索引）：
{news_titles}

请严格按以下JSON格式返回（不要加任何其他内容）：
{{"key_indices": [最重要的2-3条新闻的编号], "commentary": "200字以内市场点评"}}

要求：
1. key_indices: 从上方新闻中选出对A股影响最大的2-3条，填其编号（如[0,3,7]中的0,3,7）
2. commentary: 先一句话概括今日核心特征，再点评key_indices对应新闻的后市影响，最后指出最值得关注方向
3. 禁止使用*#等markdown符号，纯文本
4. 语言犀利专业，不要废话"""

    async with httpx.AsyncClient(timeout=30.0) as ai_client:
        r = await ai_client.post(
            f"{settings.ai.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai.api_key}"},
            json={
                "model": settings.ai.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
            },
        )
        r.raise_for_status()
        data = r.json()
        raw = data["choices"][0]["message"]["content"].strip()

    # Parse AI JSON response
    import re as _re
    try:
        # Handle possible markdown code fence wrapping
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = _json.loads(raw)
        return {
            "text": parsed.get("commentary", raw),
            "key_indices": parsed.get("key_indices", []),
        }
    except (_json.JSONDecodeError, KeyError):
        # Fallback: extract fields via regex from possibly truncated JSON
        indices = []
        m = _re.search(r'"key_indices"\s*:\s*\[([\d,\s]*)\]', raw)
        if m:
            indices = [int(x) for x in m.group(1).split(",") if x.strip()]
        m2 = _re.search(r'"commentary"\s*:\s*"(.+)', raw, _re.DOTALL)
        text = m2.group(1).rstrip('"}') if m2 else raw
        return {"text": text, "key_indices": indices}
