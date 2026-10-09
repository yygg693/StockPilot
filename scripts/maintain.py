"""StockPilot One-Click Maintenance - runs all checks and outputs a unified report.

Usage:
    python scripts/maintain.py          # Full check (backend + frontend + processes)
    python scripts/maintain.py --quick  # Quick check (backend health only)
    python scripts/maintain.py --fix    # Auto-fix common issues + restart services
"""
import subprocess
import sys
import os
import time
import socket
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)
VENV_PY = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
PYTHON = VENV_PY if os.path.exists(VENV_PY) else "python"


def check_port(port):
    for host in ["127.0.0.1", "::1", "localhost"]:
        try:
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                if s.connect_ex((host, port)) == 0:
                    return True
        except Exception:
            continue
    return False


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def run_script(name, path, timeout=120):
    """Run a check script and return success/failure."""
    print(f"\n  Running {name}...")
    try:
        result = subprocess.run(
            [PYTHON, path],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        print(result.stdout)
        if result.stderr:
            # Only print relevant stderr
            for line in result.stderr.split("\n"):
                if "error" in line.lower() or "warning" in line.lower():
                    print(f"  {line}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  [!] TIMEOUT after {timeout}s")
        return False
    except Exception as e:
        print(f"  [!] ERROR: {e}")
        return False


def ensure_services():
    """Make sure backend and frontend are running."""
    section("Service Status")
    backend_ok = check_port(8000)
    frontend_ok = check_port(5173)

    print(f"  Backend  (:8000): {'RUNNING' if backend_ok else 'DOWN'}")
    print(f"  Frontend (:5173): {'RUNNING' if frontend_ok else 'DOWN'}")

    if not backend_ok:
        print("  -> Starting backend...")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=PROJECT_DIR,
            env=env,
            creationflags=0x00000008 | 0x00000200,
            stdout=open(os.path.join(PROJECT_DIR, "backend.log"), "a"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(4)
        backend_ok = check_port(8000)
        print(f"  -> Backend {'started' if backend_ok else 'FAILED to start'}")

    if not frontend_ok:
        print("  -> Starting frontend...")
        vite = os.path.join(PROJECT_DIR, "frontend-v2", "node_modules", ".bin", "vite.cmd")
        subprocess.Popen(
            [vite, "--port", "5173", "--strictPort"],
            cwd=os.path.join(PROJECT_DIR, "frontend-v2"),
            creationflags=0x00000008 | 0x00000200,
            stdout=open(os.path.join(PROJECT_DIR, "frontend.log"), "a"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(4)
        frontend_ok = check_port(5173)
        print(f"  -> Frontend {'started' if frontend_ok else 'FAILED to start'}")

    return backend_ok, frontend_ok


def auto_fix():
    """Attempt to fix common known issues."""
    section("Auto-Fix")

    fixes_applied = 0

    # Fix 1: Check for 'request(' in api/index.ts
    api_file = os.path.join(PROJECT_DIR, "frontend-v2", "src", "api", "index.ts")
    if os.path.exists(api_file):
        with open(api_file, "r", encoding="utf-8") as f:
            content = f.read()
        if "request(" in content and "function request" not in content:
            print("  [FIX] api/index.ts: replacing undefined request() with api calls")
            content = content.replace("return request(", "return api.get(")
            with open(api_file, "w", encoding="utf-8") as f:
                f.write(content)
            fixes_applied += 1

    # Fix 2: Check for resp.text without GBK decode in ai_briefing.py
    briefing_file = os.path.join(PROJECT_DIR, "backend", "app", "services", "ai_briefing.py")
    if os.path.exists(briefing_file):
        with open(briefing_file, "r", encoding="utf-8") as f:
            content = f.read()
        if "resp.text" in content and "decode('gbk'" not in content:
            print("  [FIX] ai_briefing.py: adding GBK decode for Tencent API responses")
            content = content.replace("text = resp.text", "text = resp.content.decode('gbk', errors='replace')")
            with open(briefing_file, "w", encoding="utf-8") as f:
                f.write(content)
            fixes_applied += 1

    # Fix 3: Check for initOrb/orbAnim stale references
    detail_file = os.path.join(PROJECT_DIR, "frontend-v2", "src", "views", "StockDetailView.vue")
    if os.path.exists(detail_file):
        with open(detail_file, "r", encoding="utf-8") as f:
            content = f.read()
        if "initOrb()" in content or "orbAnim" in content:
            print("  [FIX] StockDetailView.vue: removing stale initOrb/orbAnim references")
            content = content.replace(" initOrb();", "")
            content = content.replace("; cancelAnimationFrame(orbAnim)", "")
            with open(detail_file, "w", encoding="utf-8") as f:
                f.write(content)
            fixes_applied += 1

    if fixes_applied == 0:
        print("  No auto-fixable issues found")
    else:
        print(f"\n  Applied {fixes_applied} fix(es)")

    return fixes_applied


def main():
    quick = "--quick" in sys.argv
    fix = "--fix" in sys.argv

    print(f"\n{'#'*60}")
    print(f"  StockPilot Maintenance System")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'quick' if quick else 'full'}{' + auto-fix' if fix else ''}")
    print(f"{'#'*60}")

    # Step 1: Ensure services are running
    backend_ok, frontend_ok = ensure_services()

    if fix:
        auto_fix()
        # Restart backend after fixes
        if backend_ok:
            print("\n  Restarting backend to apply fixes...")
            subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq uvicorn*"],
                         capture_output=True, timeout=5)
            time.sleep(2)
            ensure_services()

    # Step 2: Backend health check
    if backend_ok:
        section("Backend Health Check")
        hc_path = os.path.join(SCRIPTS_DIR, "healthcheck.py")
        backend_pass = run_script("healthcheck.py", hc_path, timeout=180)
    else:
        print("\n  [!] Skipping backend checks (service down)")
        backend_pass = False

    # Step 3: Frontend pre-check (skip in quick mode)
    if not quick and frontend_ok:
        section("Frontend Pre-check")
        pc_path = os.path.join(SCRIPTS_DIR, "precheck.py")
        frontend_pass = run_script("precheck.py", pc_path, timeout=90)
    else:
        frontend_pass = frontend_ok

    # Final summary
    section("SUMMARY")
    checks = [
        ("Backend service", backend_ok),
        ("Frontend service", frontend_ok),
        ("API health", backend_pass),
        ("Frontend build", frontend_pass),
    ]
    all_ok = True
    for name, ok in checks:
        icon = "+" if ok else "!"
        print(f"  [{icon}] {name}: {'OK' if ok else 'FAILED'}")
        if not ok:
            all_ok = False

    print(f"\n{'='*60}")
    if all_ok:
        print("  SYSTEM HEALTHY - all checks passed")
    else:
        print("  ISSUES DETECTED - see details above")
        if not fix:
            print("  Tip: run with --fix to attempt auto-repair")
    print(f"{'='*60}\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
