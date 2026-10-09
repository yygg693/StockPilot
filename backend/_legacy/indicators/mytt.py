"""
精简版技术指标库（借鉴 MyTT 思路，纯 pandas/numpy 实现，不依赖 talib）。
输入统一为收盘价等 pandas Series。
"""
import numpy as np
import pandas as pd


def EMA(S, N):
    return pd.Series(S).ewm(span=N, adjust=False).mean()


def MA(S, N):
    return pd.Series(S).rolling(N).mean()


def SMA(S, N, M=1):
    """中国式 SMA（通达信）。"""
    S = pd.Series(S)
    return S.ewm(alpha=M / N, adjust=False).mean()


def MACD(close, short=12, long=26, mid=9):
    close = pd.Series(close)
    dif = EMA(close, short) - EMA(close, long)
    dea = EMA(dif, mid)
    macd = (dif - dea) * 2
    return dif, dea, macd


def RSI(close, N=14):
    close = pd.Series(close)
    diff = close.diff()
    up = diff.clip(lower=0)
    down = -diff.clip(upper=0)
    rs = SMA(up, N) / (SMA(down, N) + 1e-12)
    return 100 - 100 / (1 + rs)


def KDJ(close, high, low, N=9, M1=3, M2=3):
    close, high, low = pd.Series(close), pd.Series(high), pd.Series(low)
    low_n = low.rolling(N).min()
    high_n = high.rolling(N).max()
    rsv = (close - low_n) / (high_n - low_n + 1e-12) * 100
    k = SMA(rsv, M1)
    d = SMA(k, M2)
    j = 3 * k - 2 * d
    return k, d, j


def BOLL(close, N=20, P=2):
    close = pd.Series(close)
    mid = MA(close, N)
    std = close.rolling(N).std()
    return mid + P * std, mid, mid - P * std


def _last(series):
    try:
        v = series.iloc[-1]
        if pd.isna(v):
            return None
        return round(float(v), 3)
    except Exception:  # noqa
        return None


def compute_all(kline_rows):
    """输入 K线 rows（含 close/high/low），返回指标最新值 + 简要信号解读。"""
    if not kline_rows or len(kline_rows) < 20:
        return {"error": "数据不足，无法计算指标", "signals": []}
    df = pd.DataFrame(kline_rows)
    close = df["close"].astype(float)
    high = df.get("high", close).astype(float)
    low = df.get("low", close).astype(float)

    dif, dea, macd = MACD(close)
    rsi6 = RSI(close, 6)
    rsi14 = RSI(close, 14)
    k, d, j = KDJ(close, high, low)
    up, mid, low_b = BOLL(close)
    ma5, ma10, ma20 = MA(close, 5), MA(close, 10), MA(close, 20)

    latest = {
        "MA5": _last(ma5), "MA10": _last(ma10), "MA20": _last(ma20),
        "MACD_DIF": _last(dif), "MACD_DEA": _last(dea), "MACD": _last(macd),
        "RSI6": _last(rsi6), "RSI14": _last(rsi14),
        "KDJ_K": _last(k), "KDJ_D": _last(d), "KDJ_J": _last(j),
        "BOLL_UP": _last(up), "BOLL_MID": _last(mid), "BOLL_LOW": _last(low_b),
        "price": _last(close),
    }

    # 简要信号解读（供 AI 与前端使用）
    signals = []
    if latest["MA5"] and latest["MA10"] and latest["MA20"]:
        if latest["MA5"] > latest["MA10"] > latest["MA20"]:
            signals.append(("均线", "多头排列（MA5>MA10>MA20）", "偏多"))
        elif latest["MA5"] < latest["MA10"] < latest["MA20"]:
            signals.append(("均线", "空头排列（MA5<MA10<MA20）", "偏空"))
        else:
            signals.append(("均线", "均线缠绕，方向不明", "中性"))
    if latest["MACD_DIF"] is not None and latest["MACD_DEA"] is not None:
        if latest["MACD_DIF"] > latest["MACD_DEA"]:
            signals.append(("MACD", "DIF 在 DEA 上方（金叉区）", "偏多"))
        else:
            signals.append(("MACD", "DIF 在 DEA 下方（死叉区）", "偏空"))
    if latest["RSI14"] is not None:
        if latest["RSI14"] > 70:
            signals.append(("RSI", f"RSI14={latest['RSI14']} 超买", "偏空"))
        elif latest["RSI14"] < 30:
            signals.append(("RSI", f"RSI14={latest['RSI14']} 超卖", "偏多"))
        else:
            signals.append(("RSI", f"RSI14={latest['RSI14']} 中性区", "中性"))
    if latest["KDJ_J"] is not None:
        if latest["KDJ_J"] > 100:
            signals.append(("KDJ", f"J={latest['KDJ_J']} 高位钝化", "偏空"))
        elif latest["KDJ_J"] < 0:
            signals.append(("KDJ", f"J={latest['KDJ_J']} 低位钝化", "偏多"))

    # 近 N 日涨幅（用于追高判断）
    try:
        recent = close.tail(6)
        chase = round((recent.iloc[-1] / recent.iloc[0] - 1) * 100, 2)
    except Exception:  # noqa
        chase = None
    latest["recent5_pct"] = chase

    return {"latest": latest, "signals": signals}
