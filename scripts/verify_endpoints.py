"""Runtime endpoint verification script."""
import asyncio, sys, json
sys.path.insert(0, r"D:\StockPilot")

from backend.app.main import create_app
from backend.app.db.session import init_db, close_db

async def test_endpoints():
    await init_db()
    app = create_app()
    
    import httpx
    transport = httpx.ASGITransport(app=app)
    
    results = []
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        tests = [
            ("GET", "/api/health", None),
            ("POST", "/api/auth/register", {"username": "testuser", "password": "Test123456"}),
            ("POST", "/api/auth/login", {"username": "testuser", "password": "Test123456"}),
            ("GET", "/api/account", None),
            ("GET", "/api/positions", None),
            ("GET", "/api/watchlist", None),
            ("GET", "/api/suitability/questionnaire", None),
            ("GET", "/api/audit/logs", None),
            ("GET", "/api/risk-warnings", None),
            ("POST", "/api/trade/buy", {"code": "sh600519", "name": "贵州茅台", "qty": 100, "price": 1500.0}),
            ("GET", "/api/trade/history", None),
            ("GET", "/api/config/ai", None),
            ("GET", "/api/suitability/product-grades", None),
            ("POST", "/api/suitability/assess", {"answers": [3, 3, 3, 3, 3, 3, 3, 3]}),
            ("GET", "/api/suitability/profile", None),
        ]
        
        for method, path, body in tests:
            try:
                if method == "GET":
                    r = await client.get(path)
                else:
                    r = await client.post(path, json=body)
                ok = r.status_code in (200, 201)
                detail = "OK" if ok else r.text[:120]
                results.append((ok, method, path, r.status_code, detail))
            except Exception as e:
                results.append((False, method, path, 0, str(e)[:120]))
    
    await close_db()
    
    print("=" * 70)
    print("RUNTIME ENDPOINT TEST RESULTS")
    print("=" * 70)
    all_ok = True
    for ok, method, path, status, detail in results:
        icon = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{icon}] {status} {method} {path} - {detail}")
    
    passed = sum(1 for r in results if r[0])
    print(f"\n{passed}/{len(results)} endpoints passed")
    return all_ok

ok = asyncio.run(test_endpoints())
sys.exit(0 if ok else 1)
