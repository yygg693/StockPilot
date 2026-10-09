"""
腾讯行情数据源（qt.gtimg.cn / web.ifzq.gtimg.cn / smartbox.gtimg.cn）。
本环境下东财/新浪接口的 TLS 指纹被 WAF 拦截，腾讯接口稳定可用，故作为主力源。
纯 requests 实现，字段索引已实测确认。
"""
import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_TIMEOUT = 10


def to_tx_code(code: str, asset_type: str = "stock") -> str:
    """代码 -> 腾讯代码前缀。
    A股: sh/sz + 6位；港股: hk + 5位；美股: us + 字母代码。
    """
    raw = (code or "").strip()
    low = raw.lower()
    # 已带前缀直接返回
    if low.startswith(("sh", "sz", "hk", "us")):
        return low if low.startswith(("sh", "sz", "hk")) else "us" + raw[2:].upper()
    # 港股：5位数字 或 asset_type=hk
    if asset_type in ("hk", "hkstock"):
        return "hk" + raw.zfill(5)
    # 美股：含字母（非纯数字）
    if asset_type in ("us", "usstock") or (not raw.isdigit()):
        return "us" + raw.upper()
    # A股 6位
    if raw.startswith(("6", "5", "9", "11", "7")):
        return "sh" + raw
    if raw.startswith(("0", "3", "2", "15", "16", "12", "1")):
        return "sz" + raw
    return "sh" + raw


def _kline_endpoint(tx_code: str) -> str:
    """按市场返回对应的 K线端点前缀。"""
    if tx_code.startswith("hk"):
        return "hkfqkline"
    if tx_code.startswith("us"):
        return "usfqkline"
    return "fqkline"


def normalize_type(asset_type: str) -> str:
    """把 hk/us 归一到 stock 家族用于指标计算等（保留原值给前端展示）。"""
    return asset_type


def get_quote(code: str, asset_type: str = "stock"):
    """实时行情。返回统一结构。"""
    tx = to_tx_code(code, asset_type)
    url = f"https://qt.gtimg.cn/q={tx}"
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    # 美股返回体是 GBK 编码但含拉丁字符，统一用 gbk 容错解码
    try:
        text = r.content.decode("gbk", errors="replace")
    except Exception:  # noqa
        r.encoding = "gbk"
        text = r.text
    if "=" not in text or '""' in text:
        raise RuntimeError("腾讯行情返回空")
    payload = text.split('="', 1)[1].rstrip('";\n')
    p = payload.split("~")
    if len(p) < 35:
        raise RuntimeError("腾讯行情字段不足")

    def _lvl(i_price, i_vol):
        return {"price": _f(p[i_price]), "volume": _f(p[i_vol])}

    # 五档盘口（买一~买五 / 卖一~卖五），volume 单位：手
    bids = [_lvl(9, 10), _lvl(11, 12), _lvl(13, 14), _lvl(15, 16), _lvl(17, 18)]
    asks = [_lvl(19, 20), _lvl(21, 22), _lvl(23, 24), _lvl(25, 26), _lvl(27, 28)]
    amt_wan = _f(p[37]) if len(p) > 37 else None
    amount_yuan = round(amt_wan * 10000, 2) if amt_wan is not None else None
    return {
        "code": code,
        "name": p[1],
        "type": asset_type,
        "price": _f(p[3]),
        "prev_close": _f(p[4]),
        "open": _f(p[5]),
        "volume": _f(p[6]),          # 成交量(手)
        "outer": _f(p[7]),           # 外盘(主动性买盘, 手)
        "inner": _f(p[8]),           # 内盘(主动性卖盘, 手)
        "change": _f(p[31]),
        "change_pct": _f(p[32]),
        "high": _f(p[33]),
        "low": _f(p[34]),
        "amount": amount_yuan,       # 成交额(元)
        "turnover": _f(p[38]) if len(p) > 38 else None,      # 换手率%
        "volume_ratio": _f(p[56]) if len(p) > 56 else None,  # 量比
        "pe": _f(p[39]) if len(p) > 39 else None,
        "pb": _f(p[46]) if len(p) > 46 else None,
        "amplitude": _f(p[49]) if len(p) > 49 else None,    # 振幅%
        "limit_up": _f(p[47]) if len(p) > 47 else None,     # 涨停价
        "limit_down": _f(p[48]) if len(p) > 48 else None,   # 跌停价
        "bids": bids,
        "asks": asks,
        "source": "tencent",
    }


def get_kline(code: str, asset_type: str = "stock", period: str = "day", limit: int = 120):
    """K线。period: day/week/month。返回 {kind:'kline', rows:[...]}。支持 A股/港股/美股。"""
    tx = to_tx_code(code, asset_type)
    pmap = {"daily": "day", "day": "day", "week": "week", "month": "month"}
    per = pmap.get(period, "day")
    endpoint = _kline_endpoint(tx)
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/{endpoint}/get"
           f"?param={tx},{per},,,{limit},qfq")
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    j = r.json()
    node = (j.get("data") or {}).get(tx) or {}
    arr = node.get("qfq" + per) or node.get(per) or []
    rows = []
    for it in arr:
        # [date, open, close, high, low, volume]
        try:
            rows.append({
                "date": it[0], "open": _f(it[1]), "close": _f(it[2]),
                "high": _f(it[3]), "low": _f(it[4]), "volume": _f(it[5]),
            })
        except Exception:  # noqa
            continue
    return {"code": code, "type": asset_type, "kind": "kline", "rows": rows,
            "source": "tencent"}


# 分时（日内实时）数据缓存：避免轮询打爆外部源
_MINUTE_CACHE = {}
_MINUTE_TTL = 4  # 秒


def get_minute(code: str, asset_type: str = "stock"):
    """分时/日内实时走势（腾讯）。
    返回 {kind:'minute', prev_close, points:[{t,price,avg,volume}], ...}。
    字段：data.node['data']['data'] 每行 'HHMM 现价 累计成交量(手) 累计成交额(元)'，
    分时均价 = 累计成交额 / (累计成交量*100)。
    """
    tx = to_tx_code(code, asset_type)
    import time
    now = time.time()
    c = _MINUTE_CACHE.get(tx)
    if c and now - c[0] < _MINUTE_TTL:
        return c[1]
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={tx}"
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    j = r.json()
    node = (j.get("data") or {}).get(tx) or {}
    inner = node.get("data") or {}
    arr = inner.get("data") if isinstance(inner, dict) else inner
    if not isinstance(arr, list):
        return {"code": code, "type": asset_type, "kind": "minute",
                "available": False, "reason": "no_data"}
    points = []
    prev_cumvol = 0
    for it in arr:
        parts = str(it).split(" ")
        if len(parts) < 4:
            continue
        t = parts[0]
        price = _f(parts[1])
        cumvol = _f(parts[2])   # 累计成交量(手)
        cumamt = _f(parts[3])   # 累计成交额(元)
        if price is None or cumvol is None or cumamt is None:
            continue
        hh, mm = t[:2], t[2:4]
        avg = round(cumamt / (cumvol * 100), 3) if cumvol else price
        inc = max(0, int(round(cumvol - prev_cumvol))) if prev_cumvol is not None else 0
        prev_cumvol = cumvol
        points.append({"t": f"{hh}:{mm}", "price": price, "avg": avg, "volume": inc})
    # 昨收：minute 接口的 qt 节点通常为空，回退到实时行情接口取 prev_close
    prev_close = None
    qt = node.get("qt") or {}
    for qk, qv in qt.items():
        if isinstance(qv, str) and qk.startswith("v_ff_") and "~" in qv:
            pp = qv.split("~")
            prev_close = _f(pp[4]) if len(pp) > 4 else None
            break
    if prev_close is None:
        try:
            prev_close = get_quote(code, asset_type).get("prev_close")
        except Exception:  # noqa
            prev_close = None
    result = {"code": code, "type": asset_type, "kind": "minute",
              "available": bool(points), "date": node.get("date"),
              "prev_close": prev_close, "points": points, "source": "tencent"}
    _MINUTE_CACHE[tx] = (now, result)
    return result


def get_index_overview():
    """主要指数：上证/深证/创业板。"""
    targets = [("sh000001", "上证指数", "000001"),
               ("sz399001", "深证成指", "399001"),
               ("sz399006", "创业板指", "399006")]
    q = ",".join(t[0] for t in targets)
    url = f"https://qt.gtimg.cn/q={q}"
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    r.encoding = "gbk"
    out = []
    for line in r.text.strip().split(";"):
        if '="' not in line:
            continue
        payload = line.split('="', 1)[1].rstrip('"\n ')
        p = payload.split("~")
        if len(p) < 33:
            continue
        name = next((t[1] for t in targets if p[2] == t[2]), p[1])
        out.append({"code": p[2], "name": name,
                    "price": _f(p[3]), "change_pct": _f(p[32])})
    return out


def search(keyword: str):
    """腾讯智能盒子搜索股票/基金/指数。"""
    url = f"https://smartbox.gtimg.cn/s3/?v=2&q={keyword}&t=all"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.encoding = "gbk"
        text = r.text
    except Exception:  # noqa
        return []
    # 格式: v_hint="sh~600519~\u8d35\u5dde\u8305\u53f0~gzmt~GP-A^sz~000858~..."
    if '="' not in text:
        return []
    body = text.split('="', 1)[1].rstrip('";\n')
    results = []
    for item in body.split("^"):
        f = item.split("~")
        if len(f) < 5:
            continue
        mkt, code6, name_raw, _py, kind = f[0], f[1], f[2], f[3], f[4]
        # 名称 unicode 转义还原
        try:
            name = name_raw.encode("latin1", "ignore").decode("unicode_escape")
        except Exception:  # noqa
            name = name_raw
        # 类型判定
        k = (kind or "").upper()
        if "ZS" in k:            # 指数，跳过（不作为自选标的）
            continue
        elif "ETF" in k:
            atype = "etf"
        elif k.startswith("JJ") or "LOF" in k:
            atype = "fund"
        else:                    # GP-A / GP-B / GP-KCB / GP-CYB 等
            atype = "stock"
        results.append({"code": code6, "name": name, "type": atype,
                        "tx_code": f"{mkt}{code6}"})
    return results[:20]


def _f(v):
    try:
        if v is None or v == "" or v == "-":
            return None
        return float(v)
    except Exception:  # noqa
        return None
