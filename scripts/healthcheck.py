"""StockPilot Backend Health Check - API smoke tests + response validation."""
import asyncio
import httpx
import sys
import time
from datetime import datetime

BASE = "http://localhost:8000/api"
TIMEOUT = 35


class CheckResult:
    def __init__(self, name, passed, detail="", duration=0):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.duration = duration


results: list = []


async def check(client, name, method, path, validate=None, body=None, timeout=TIMEOUT):
    start = time.time()
    try:
        if method == "GET":
            r = await client.get(BASE + path, timeout=timeout)
        else:
            r = await client.post(BASE + path, json=body or {}, timeout=timeout)
        dur = round((time.time() - start) * 1000)
        if r.status_code != 200:
            results.append(CheckResult(name, False, f"HTTP {r.status_code}: {r.text[:100]}", dur))
            return
        data = r.json()
        if validate:
            err = validate(data)
            if err:
                results.append(CheckResult(name, False, f"Validation: {err}", dur))
                return
        results.append(CheckResult(name, True, "", dur))
    except Exception as e:
        dur = round((time.time() - start) * 1000)
        results.append(CheckResult(name, False, str(e)[:120], dur))


def has_data(d):
    if "data" not in d:
        return "missing data field"
    return None


def index_valid(d):
    if "data" not in d or not isinstance(d["data"], list):
        return "missing data list"
    if len(d["data"]) < 3:
        return f"expected 3+ indices, got {len(d['data'])}"
    for idx in d["data"]:
        if not idx.get("name"):
            return f"index missing name: {idx.get('code')}"
        if not idx.get("price"):
            return f"index missing price: {idx.get('name')}"
    return None


def quote_valid(d):
    if "data" not in d or not isinstance(d["data"], dict):
        return "missing data dict"
    q = d["data"]
    for field in ["name", "price", "open", "high", "low", "volume"]:
        if field not in q:
            return f"missing field: {field}"
    if not q.get("name"):
        return "name is empty"
    return None


def kline_valid(d):
    if "data" not in d or not isinstance(d["data"], list):
        return "missing data list"
    if len(d["data"]) < 10:
        return f"too few bars: {len(d['data'])}"
    bar = d["data"][0]
    for f in ["date", "open", "close", "high", "low"]:
        if f not in bar:
            return f"bar missing field: {f}"
    return None


def search_valid(d):
    if "data" not in d or not isinstance(d["data"], list):
        return "missing data list"
    if len(d["data"]) == 0:
        return "no results for keyword"
    item = d["data"][0]
    if not item.get("name"):
        return "result missing name"
    if not item.get("code"):
        return "result missing code"
    return None


def briefing_valid(d):
    if "data" not in d or not isinstance(d["data"], dict):
        return "missing data dict"
    bd = d["data"]
    if not bd.get("summary"):
        return "missing summary"
    if not bd.get("indices"):
        return "missing indices"
    for idx in bd["indices"]:
        if not idx.get("name"):
            return "index name empty (GBK decode issue?)"
    return None


def signals_valid(d):
    if "data" not in d or not isinstance(d["data"], dict):
        return "missing data dict"
    sd = d["data"]
    if "signals" not in sd:
        return "missing signals field"
    if len(sd["signals"]) == 0:
        return "no signals generated (stock universe empty?)"
    sig = sd["signals"][0]
    for f in ["code", "signal", "score", "reasons"]:
        if f not in sig:
            return f"signal missing field: {f}"
    return None


async def run_all():
    async with httpx.AsyncClient() as c:
        # Core Data
        await check(c, "GET /health", "GET", "/health")
        await check(c, "GET /index (indices)", "GET", "/index", index_valid)
        await check(c, "GET /quote (stock)", "GET", "/quote?code=sh600519", quote_valid)
        await check(c, "GET /kline day", "GET", "/kline?code=sh600519&period=day&count=60", kline_valid)
        await check(c, "GET /kline week", "GET", "/kline?code=sh600519&period=week&count=60", kline_valid)
        await check(c, "GET /kline month", "GET", "/kline?code=sh600519&period=month&count=60", kline_valid)
        await check(c, "GET /search (Chinese)", "GET", "/search?q=%E8%8C%85%E5%8F%B0", search_valid)
        await check(c, "GET /search (code)", "GET", "/search?q=600519", search_valid)
        await check(c, "GET /breadth", "GET", "/breadth", has_data)

        # Trade
        await check(c, "GET /account", "GET", "/account", has_data)
        await check(c, "GET /trade/history", "GET", "/trade/history?limit=5", has_data)
        await check(c, "GET /watchlist", "GET", "/watchlist", has_data)

        # AI Phase 1
        await check(c, "GET /ai/market-summary", "GET", "/ai/market-summary", has_data)

        # AI Phase 2
        await check(c, "GET /ai/briefing", "GET", "/ai/briefing", briefing_valid)
        await check(c, "GET /ai/alerts", "GET", "/ai/alerts", has_data)
        await check(c, "POST /ai/diagnose", "POST", "/ai/diagnose", has_data)

        # AI Phase 3
        await check(c, "GET /ai/signals", "GET", "/ai/signals", signals_valid, timeout=90)
        await check(c, "GET /ai/risk-status", "GET", "/ai/risk-status", has_data)

        # Fund
        await check(c, "GET /fund/screen", "GET", "/fund/screen?limit=5", has_data)

        # Screener
        await check(c, "GET /screener/strategies", "GET", "/screener/strategies", has_data)


def print_report():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"  StockPilot Health Check Report")
    print(f"  {now}")
    print(f"{'='*60}")
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"{'='*60}\n")

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        icon = "+" if r.passed else "!"
        line = f"  [{icon}] {status}  {r.name}  ({r.duration}ms)"
        if r.detail:
            line += f"\n         -> {r.detail}"
        print(line)

    print(f"\n{'='*60}")
    if failed == 0:
        print("  ALL CHECKS PASSED")
    else:
        print(f"  {failed} CHECK(S) FAILED - needs attention")
    print(f"{'='*60}\n")
    return failed == 0


if __name__ == "__main__":
    asyncio.run(run_all())
    ok = print_report()
    sys.exit(0 if ok else 1)
