"""AI Trading Signals + Risk Control for StockPilot Phase 3."""

import httpx

from backend.app.core.config import get_settings

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"  # Default fallback; actual model from settings


# ============ Technical Indicators (Expanded Library) ============

def calc_ma(closes: list[float], n: int) -> list[float | None]:
    result = []
    for i in range(len(closes)):
        if i < n - 1:
            result.append(None)
        else:
            result.append(sum(closes[i-n+1:i+1]) / n)
    return result


def calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_macd(closes: list[float]) -> dict:
    """Returns latest DIF, DEA, histogram."""
    if len(closes) < 26:
        return {"dif": 0, "dea": 0, "hist": 0}
    def ema(data, n):
        result = [data[0]]
        k = 2 / (n + 1)
        for i in range(1, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = [ema12[i] - ema26[i] for i in range(len(closes))]
    dea = ema(dif, 9)
    hist = [(dif[i] - dea[i]) * 2 for i in range(len(dif))]
    return {"dif": round(dif[-1], 4), "dea": round(dea[-1], 4), "hist": round(hist[-1], 4)}


def calc_boll(closes: list[float], n: int = 20, k: float = 2.0) -> dict:
    """Bollinger Bands. Returns upper, middle, lower."""
    if len(closes) < n:
        return {"upper": 0, "mid": 0, "lower": 0}
    window = closes[-n:]
    mid = sum(window) / n
    std = (sum((x - mid) ** 2 for x in window) / n) ** 0.5
    return {"upper": round(mid + k * std, 2), "mid": round(mid, 2), "lower": round(mid - k * std, 2)}


def calc_kdj(klines: list[dict], n: int = 9) -> dict:
    """KDJ stochastic oscillator. Requires kline data with high/low/close."""
    if len(klines) < n:
        return {"k": 0, "d": 0, "j": 0}
    k, d = 50.0, 50.0
    for i in range(max(0, len(klines) - n * 3), len(klines)):
        start = max(0, i - n + 1)
        window = klines[start:i+1]
        hn = max(w["high"] for w in window)
        ln = min(w["low"] for w in window)
        close = klines[i]["close"]
        rsv = (close - ln) / (hn - ln) * 100 if hn != ln else 50
        k = 2 / 3 * k + 1 / 3 * rsv
        d = 2 / 3 * d + 1 / 3 * k
    j = 3 * k - 2 * d
    return {"k": round(k, 2), "d": round(d, 2), "j": round(j, 2)}


def calc_obv(closes: list[float], volumes: list[float]) -> float:
    """On Balance Volume — returns latest cumulative OBV."""
    if len(closes) < 2 or len(volumes) < len(closes):
        return 0.0
    obv = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv += volumes[i]
        elif closes[i] < closes[i-1]:
            obv -= volumes[i]
    return round(obv, 0)


def calc_wr(closes: list[float], highs: list[float], lows: list[float], n: int = 14) -> float | None:
    """Williams %R. Range: -100 to 0."""
    if len(closes) < n:
        return None
    hn = max(highs[-n:])
    ln = min(lows[-n:])
    if hn == ln:
        return -50.0
    return round((hn - closes[-1]) / (hn - ln) * -100, 2)


def calc_cci(closes: list[float], highs: list[float], lows: list[float], n: int = 14) -> float | None:
    """Commodity Channel Index."""
    if len(closes) < n:
        return None
    tps = [(h + lo + c) / 3 for h, lo, c in zip(highs[-n:], lows[-n:], closes[-n:], strict=True)]
    ma_tp = sum(tps) / n
    md = sum(abs(tp - ma_tp) for tp in tps) / n
    if md == 0:
        return 0.0
    tp = tps[-1]
    return round((tp - ma_tp) / (0.015 * md), 2)


# ============ Signal Generation ============

async def fetch_kline(code: str, days: int = 60) -> list[dict]:
    """Fetch daily K-line from Tencent."""
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        data = resp.json()
    try:
        kdata = data.get("data", {}).get(f"{prefix}{code}", {})
        day_data = kdata.get("qfqday") or kdata.get("day") or []
        return [{"date": d[0], "open": float(d[1]), "close": float(d[2]), "high": float(d[3]), "low": float(d[4]), "volume": float(d[5]) if len(d) > 5 else 0} for d in day_data]
    except Exception:
        return []


def analyze_technicals(closes: list[float], klines: list[dict] | None = None) -> dict:
    """Generate technical analysis with expanded indicators and confidence scoring."""
    if len(closes) < 20:
        return {"signal": "neutral", "reason": "数据不足", "score": 0, "confidence": 0}

    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    boll = calc_boll(closes)

    # New indicators (require kline data)
    kdj = calc_kdj(klines) if klines else {"k": 0, "d": 0, "j": 0}
    wr = None
    cci = None
    obv = 0
    if klines and len(klines) >= 14:
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        vols = [k.get("volume", 0) for k in klines]
        wr = calc_wr(closes, highs, lows)
        cci = calc_cci(closes, highs, lows)
        obv = calc_obv(closes, vols)

    score = 0
    reasons = []
    indicators_used = 0
    indicators_agree = 0  # Count how many agree with final direction

    # MA crossover
    indicators_used += 1
    if ma5[-1] and ma10[-1] and ma5[-2] and ma10[-2]:
        if ma5[-1] > ma10[-1] and ma5[-2] <= ma10[-2]:
            score += 2
            reasons.append("MA5上穿MA10(金叉)")
            indicators_agree += 1
        elif ma5[-1] < ma10[-1] and ma5[-2] >= ma10[-2]:
            score -= 2
            reasons.append("MA5下穿MA10(死叉)")
            indicators_agree += 1
        elif ma5[-1] > ma10[-1] > (ma20[-1] or 0):
            score += 1
            reasons.append("多头排列")
            indicators_agree += 1

    # RSI
    indicators_used += 1
    if rsi is not None:
        if rsi < 30:
            score += 2
            reasons.append(f"RSI超卖({rsi:.0f})")
            indicators_agree += 1
        elif rsi > 70:
            score -= 2
            reasons.append(f"RSI超买({rsi:.0f})")
            indicators_agree += 1
        elif rsi < 40:
            score += 1
            reasons.append(f"RSI偏低({rsi:.0f})")

    # MACD
    indicators_used += 1
    if macd["hist"] > 0 and macd["dif"] > macd["dea"]:
        score += 1
        reasons.append("MACD红柱")
        indicators_agree += 1
    elif macd["hist"] < 0 and macd["dif"] < macd["dea"]:
        score -= 1
        reasons.append("MACD绿柱")
        indicators_agree += 1

    # Price vs MA20
    indicators_used += 1
    if ma20[-1]:
        if closes[-1] > ma20[-1] * 1.02:
            score += 1
            reasons.append("站上20日线")
            indicators_agree += 1
        elif closes[-1] < ma20[-1] * 0.98:
            score -= 1
            reasons.append("跌破20日线")
            indicators_agree += 1

    # Bollinger Bands
    indicators_used += 1
    if boll["lower"] > 0:
        if closes[-1] <= boll["lower"]:
            score += 1
            reasons.append("触及布林下轨")
            indicators_agree += 1
        elif closes[-1] >= boll["upper"]:
            score -= 1
            reasons.append("触及布林上轨")
            indicators_agree += 1

    # KDJ
    if klines:
        indicators_used += 1
        if kdj["j"] < 0:
            score += 1
            reasons.append(f"KDJ超卖(J={kdj['j']:.0f})")
            indicators_agree += 1
        elif kdj["j"] > 100:
            score -= 1
            reasons.append(f"KDJ超买(J={kdj['j']:.0f})")
            indicators_agree += 1
        elif kdj["k"] > kdj["d"] and kdj["j"] > kdj["k"]:
            score += 1
            reasons.append("KDJ金叉向上")
            indicators_agree += 1

    # Williams %R
    if wr is not None:
        indicators_used += 1
        if wr < -80:
            score += 1
            reasons.append(f"WR超卖({wr:.0f})")
            indicators_agree += 1
        elif wr > -20:
            score -= 1
            reasons.append(f"WR超买({wr:.0f})")
            indicators_agree += 1

    # CCI
    if cci is not None:
        indicators_used += 1
        if cci < -100:
            score += 1
            reasons.append(f"CCI超卖({cci:.0f})")
            indicators_agree += 1
        elif cci > 100:
            score -= 1
            reasons.append(f"CCI超买({cci:.0f})")
            indicators_agree += 1

    if score >= 3:
        signal = "strong_buy"
    elif score >= 1:
        signal = "buy"
    elif score <= -3:
        signal = "strong_sell"
    elif score <= -1:
        signal = "sell"
    else:
        signal = "neutral"

    # Confidence score (0-100): based on signal strength and indicator agreement
    abs_score = abs(score)
    agreement_ratio = indicators_agree / indicators_used if indicators_used > 0 else 0
    confidence = min(100, int(abs_score * 15 + agreement_ratio * 40))

    result = {
        "signal": signal,
        "score": score,
        "confidence": confidence,
        "reasons": reasons,
        "rsi": round(rsi, 1) if rsi else None,
        "macd": macd,
        "ma5": round(ma5[-1], 2) if ma5[-1] else None,
        "ma20": round(ma20[-1], 2) if ma20[-1] else None,
        "boll": boll,
        "kdj": kdj,
    }
    if wr is not None:
        result["wr"] = wr
    if cci is not None:
        result["cci"] = cci
    if obv:
        result["obv"] = obv
    return result


async def generate_signals(codes: list[str]) -> list[dict]:
    """Generate trading signals for a list of stock codes (parallel fetch)."""
    import asyncio

    async def _analyze_one(code: str) -> dict | None:
        klines = await fetch_kline(code, 60)
        if not klines or len(klines) < 20:
            return None
        closes = [k["close"] for k in klines]
        tech = analyze_technicals(closes, klines)
        if tech["signal"] == "neutral":
            return None
        return {
            "code": code,
            "price": closes[-1],
            "change_pct": round((closes[-1] / closes[-2] - 1) * 100, 2) if len(closes) > 1 else 0,
            **tech,
        }

    tasks = [_analyze_one(code) for code in codes[:20]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    signals = [r for r in results if isinstance(r, dict)]

    # Sort by absolute score
    signals.sort(key=lambda x: abs(x["score"]), reverse=True)

    # Attach stock names via quote fetch
    if signals:
        try:
            from backend.app.core.http_client import get_http_client
            from backend.app.services.data_tencent import fetch_quote_batch
            client = get_http_client()
            # Add exchange prefix for quote API
            def _pfx(code: str) -> str:
                if code.startswith(("sh", "sz")):
                    return code
                return ("sh" if code.startswith("6") else "sz") + code
            prefixed = [_pfx(s["code"]) for s in signals]
            quotes = await fetch_quote_batch(client, prefixed)
            for s in signals:
                full_code = _pfx(s["code"])
                q = quotes.get(full_code, {})
                s["name"] = q.get("name", s["code"])
        except Exception:
            for s in signals:
                s.setdefault("name", s["code"])

    return signals


async def ai_filter_signals(signals: list[dict], market_context: str = "") -> str:
    """Use AI to provide commentary on generated signals. Uses configured model."""
    if not signals:
        return "当前无明显交易信号。"
    settings = get_settings()
    if not settings.ai.configured or not settings.ai.enabled:
        return ""

    sig_text = "\n".join(
        f"  {s['code']}: {s['signal']}(评分{s['score']},置信度{s.get('confidence', 0)}%), 原因: {', '.join(s['reasons'])}"
        for s in signals[:8]
    )
    prompt = f"""以下是技术面生成的量化信号，请仅做客观解读与信息整理（不超过150字）：

{sig_text}

{market_context}

请说明这些信号分别基于哪些技术维度、有何局限性，并提示信号可能存在假信号风险。所有内容仅供学习参考，不构成交易指令。"""

    # Multi-model switching: use configured base_url and model
    api_url = f"{settings.ai.base_url}/chat/completions"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(api_url, json={
            "model": settings.ai.model,
            "messages": [
                {"role": "system", "content": "你是量化数据分析助手，擅长A股技术面数据的客观解读。回复简洁，用纯文本，禁止使用*#等markdown符号；仅呈现数据维度与风险提示，不给出确定性买卖指令。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.5,
        }, headers={"Authorization": f"Bearer {settings.ai.api_key}"})
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


# ============ Risk Control Engine (delegated to core/risk.py) ============
# Re-export unified risk manager for backward compatibility
