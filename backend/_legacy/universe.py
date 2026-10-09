"""
股票池（选股 universe）获取，带磁盘缓存，保证「全A」能稳定扫描全市场。
数据来源（按稳定性分层）：
  - 代码清单：AKShare stock_info_a_code_name()（全市场 ~5500 只，本环境可用），落盘缓存 24h
  - 行情/估值快照（PE/PB/涨跌幅/成交额）：腾讯 qt.gtimg.cn 批量接口（稳定），落盘缓存 6h
  两者结合生成全市场快照 data/universe_snapshot.json，选股直接扫快照，不再依赖东财 spot 列表。
优雅降级：快照构建失败 → 用磁盘旧快照；都没有 → 内置白马清单（兜底，不空转）。
"""
import os
import re
import json
import time
import threading

import requests

from backend.config import DATA_DIR
from backend.db import store

try:
    import akshare as ak
except Exception:  # noqa
    ak = None

_LOCK = threading.Lock()
_CODES_PATH = os.path.join(DATA_DIR, "universe_codes.json")
_SNAP_PATH = os.path.join(DATA_DIR, "universe_snapshot.json")

_CODES_TTL = 86400    # 代码清单缓存 24h
_SNAP_TTL = 21600     # 行情快照缓存 6h
_CHUNK = 120          # 腾讯批量每次 120 只
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://stockapp.finance.qq.com/",
}

# 后台构建状态
_BUILD = {"running": False, "total": 0, "done": 0, "started_at": None}

# 兜底清单（仅在所有数据源都失败时使用）
_FALLBACK_CODES = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("601318", "中国平安"),
    ("600036", "招商银行"), ("000333", "美的集团"), ("000651", "格力电器"),
    ("601012", "隆基绿能"), ("600276", "恒瑞医药"), ("300750", "宁德时代"),
    ("002594", "比亚迪"), ("600900", "长江电力"), ("601899", "紫金矿业"),
    ("600030", "中信证券"), ("000001", "平安银行"), ("600887", "伊利股份"),
]


def _safe_f(v):
    try:
        if v is None or v == "" or v == "-":
            return None
        return float(v)
    except Exception:  # noqa
        return None


def _load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa
            return None
    return None


def _save_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    except Exception as e:  # noqa
        print(f"[universe] 缓存写入失败 {path}: {e}")


def _to_tx(code):
    code = (code or "").strip()
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("0", "3")):
        return "sz" + code
    if code.startswith(("8", "4")):
        return "bj" + code
    return "sh" + code


# --------------------------------------------------------------- 代码清单
def get_all_codes(force=False):
    """全市场股票代码+名称清单（带磁盘缓存）。"""
    now = time.time()
    if not force:
        cached = _load_json(_CODES_PATH)
        if cached and (now - cached.get("_ts", 0)) < _CODES_TTL:
            return cached["data"]
    if ak is None:
        cached = _load_json(_CODES_PATH)
        return cached["data"] if cached else None
    try:
        df = ak.stock_info_a_code_name()
        data = [{"code": str(r.get("code")), "name": str(r.get("name"))}
                for _, r in df.iterrows()]
        _save_json(_CODES_PATH, {"_ts": now, "data": data})
        return data
    except Exception as e:  # noqa
        print(f"[universe] 代码清单获取失败: {e}")
        cached = _load_json(_CODES_PATH)
        return cached["data"] if cached else None


# --------------------------------------------------------------- 行情快照
def _batch_quotes(codes):
    """腾讯批量行情：输入 [{code,name}]，返回 {code: {price,change_pct,pe,pb,...}}。
    单批失败（超时/空响应）返回 {}，由调用方决定是否跳过该批。
    腾讯返回格式：每行 `v_sz000001="51~平安银行~000001~..."`，末尾无 pv_none_count 字段。
    有效判定：响应中包含 `v_` 数据行即可。"""
    tx_map = {_to_tx(c["code"]): c for c in codes}
    url = "https://qt.gtimg.cn/q=" + ",".join(tx_map.keys())
    last_err = ""
    for attempt in range(2):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10)
            text = r.content.decode("gbk", "replace")
            if "v_" not in text:
                last_err = "空响应"
                continue
            res = {}
            for line in text.split(";"):
                line = line.strip()
                if not line.startswith("v_"):
                    continue
                # 形如 v_sz000001="51~平安银行~000001~..."
                m = re.match(r'^v_(\w+)="(.*)"\s*$', line)
                if not m:
                    continue
                tx = m.group(1)
                orig = tx_map.get(tx)
                if not orig:
                    continue
                p = m.group(2).split("~")
                if len(p) < 47:
                    continue
                # 成交额：腾讯 p[37] 单位为「万元」，易错；改为用 现价×成交量(手)×100 计算（单位：元），更可靠
                price = _safe_f(p[3])
                vol = _safe_f(p[6])          # 成交量，单位「手」
                amount = (price * vol * 100) if (price and vol) else None
                res[orig["code"]] = {
                    "code": orig["code"], "name": p[1] or orig["name"],
                    "price": price, "change_pct": _safe_f(p[32]),
                    "pe": _safe_f(p[39]), "pb": _safe_f(p[46]),
                    "turnover": _safe_f(p[38]), "amount": amount,
                }
            return res
        except Exception as e:  # noqa
            last_err = str(e)
            time.sleep(0.3)
    print(f"[universe] 批量行情失败({len(codes)}只): {last_err}")
    return {}


def _build_snapshot():
    """构建全市场行情/估值快照（基于代码清单 + 腾讯批量）。
    后台线程运行；单批失败跳过，不中断整体。逐步更新 _BUILD 进度。"""
    codes = get_all_codes()
    if not codes:
        return None
    out = []
    total = max(1, (len(codes) + _CHUNK - 1) // _CHUNK)
    _BUILD["running"] = True
    _BUILD["total"] = total
    _BUILD["done"] = 0
    _BUILD["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        for i in range(0, len(codes), _CHUNK):
            batch = codes[i:i + _CHUNK]
            q = _batch_quotes(batch)
            for c in batch:
                if c["code"] in q:
                    out.append(q[c["code"]])
            _BUILD["done"] += 1
            time.sleep(0.05)
    finally:
        _BUILD["running"] = False
    return out


_BUILD_LOCK = threading.Lock()


def build_snapshot_async():
    """后台线程构建快照，写入磁盘缓存，不阻塞请求。
    防重入：若已有构建在进行中，直接返回 False。"""
    if not _BUILD_LOCK.acquire(blocking=False):
        return False  # 已有构建在进行

    def _run():
        try:
            snap = _build_snapshot()
            if snap:
                _save_json(_SNAP_PATH, {"_ts": time.time(), "data": snap})
        finally:
            _BUILD_LOCK.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True


def get_build_status():
    return dict(_BUILD)


def get_breadth():
    """市场宽度统计（基于全A快照）：上涨/下跌/平盘家数、涨停/跌停家数、平均涨跌幅。
    涨停/跌停用涨跌幅阈值近似（~±9.8%，兼容四舍五入）。无快照时返回 available=False。"""
    snap = get_spot_snapshot()
    if not snap:
        return {"available": False}
    up = down = flat = limit_up = limit_down = 0
    s = 0.0
    n = 0
    for r in snap:
        cp = r.get("change_pct")
        if cp is None:
            continue
        n += 1
        s += cp
        if cp > 0:
            up += 1
        elif cp < 0:
            down += 1
        else:
            flat += 1
        if cp >= 9.8:
            limit_up += 1
        elif cp <= -9.8:
            limit_down += 1
    return {
        "available": True,
        "total": n,
        "up": up, "down": down, "flat": flat,
        "limit_up": limit_up, "limit_down": limit_down,
        "avg_change_pct": round(s / n, 2) if n else None,
    }


def get_spot_snapshot(force=False):
    """全市场行情/估值快照（带磁盘缓存）。优先缓存，否则构建并落盘。
    安全约束：若已有后台构建在进行中，绝不在此同步构建（避免阻塞请求），
    直接返回磁盘上已有的旧快照（可能为 None）。"""
    now = time.time()
    if not force:
        cached = _load_json(_SNAP_PATH)
        if cached and (now - cached.get("_ts", 0)) < _SNAP_TTL:
            return cached["data"]
    if _BUILD["running"]:
        # 后台正在构建，不阻塞；返回旧缓存（可能为空）
        cached = _load_json(_SNAP_PATH)
        return cached["data"] if cached else None
    snap = _build_snapshot()
    if snap:
        _save_json(_SNAP_PATH, {"_ts": now, "data": snap})
        return snap
    cached = _load_json(_SNAP_PATH)
    return cached["data"] if cached else None


# --------------------------------------------------------------- 沪深300
_HS300_CACHE = {"ts": 0, "data": None}
_HS300_TTL = 3600


def get_hs300(force=False):
    now = time.time()
    with _LOCK:
        if not force and _HS300_CACHE["data"] and (now - _HS300_CACHE["ts"]) < _HS300_TTL:
            return _HS300_CACHE["data"]
    codes = []
    if ak is not None:
        try:
            df = ak.index_stock_cons(symbol="000300")
            for _, r in df.iterrows():
                codes.append({"code": str(r.get("成分券代码") or r.get("股票代码")),
                              "name": str(r.get("成分券名称") or r.get("股票名称"))})
        except Exception as e:  # noqa
            print(f"[universe] 沪深300成分获取失败: {e}")
    if not codes:
        codes = [{"code": c, "name": n} for c, n in _FALLBACK_CODES]
    with _LOCK:
        _HS300_CACHE["data"] = codes
        _HS300_CACHE["ts"] = now
    return codes


# --------------------------------------------------------------- 统一入口
def get_universe(universe: str):
    """返回股票池列表（含 code/name）。"""
    universe = (universe or "watch").lower()
    if universe == "watch":
        items = [w for w in store.list_watch() if w.get("type") in ("stock", "etf")]
        return [{"code": w["code"], "name": w.get("name") or w["code"]} for w in items]
    if universe == "hs300":
        return get_hs300()
    # all
    snap = get_spot_snapshot()
    if snap:
        return [{"code": s["code"], "name": s["name"]} for s in snap]
    codes = get_all_codes()
    if codes:
        return codes
    return [{"code": c, "name": n} for c, n in _FALLBACK_CODES]
