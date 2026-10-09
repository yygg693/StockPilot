"""StockPilot Desktop - native window wrapper.

Usage:
    python desktop.py              # Dev mode (connects to Vite dev server)
    python desktop.py --prod       # Prod mode (serves built static files)
    python desktop.py --build      # Build frontend then launch prod mode
"""
import sys
import os
import time
import threading
import socket

# Project paths
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend-v2")
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")
PYTHON = sys.executable

BACKEND_PORT = 8000
FRONTEND_PORT = 5173


def check_port(port):
    for host in ["127.0.0.1", "::1"]:
        try:
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex((host, port)) == 0:
                    return True
        except Exception:
            continue
    return False


def start_backend():
    """Start uvicorn backend in a thread."""
    import subprocess
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    log = open(os.path.join(PROJECT_DIR, "backend.log"), "a", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=PROJECT_DIR,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return proc


def start_frontend_dev():
    """Start Vite dev server."""
    import subprocess
    vite = os.path.join(FRONTEND_DIR, "node_modules", ".bin", "vite.cmd")
    log = open(os.path.join(PROJECT_DIR, "frontend.log"), "a", encoding="utf-8")
    proc = subprocess.Popen(
        [vite, "--port", str(FRONTEND_PORT), "--strictPort"],
        cwd=FRONTEND_DIR,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return proc


def build_frontend():
    """Run vite build to produce static files."""
    import subprocess
    print("[StockPilot] Building frontend...")
    vite = os.path.join(FRONTEND_DIR, "node_modules", ".bin", "vite.cmd")
    result = subprocess.run(
        [vite, "build"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode == 0:
        print("[StockPilot] Build successful -> frontend-v2/dist/")
        return True
    else:
        print("[StockPilot] Build FAILED:")
        print(result.stderr[-500:] if result.stderr else result.stdout[-500:])
        return False


def wait_for_port(port, timeout=15):
    """Wait until a port is listening."""
    start = time.time()
    while time.time() - start < timeout:
        if check_port(port):
            return True
        time.sleep(0.5)
    return False


def main():
    import webview

    prod_mode = "--prod" in sys.argv
    do_build = "--build" in sys.argv

    print(f"\n{'='*50}")
    print(f"  StockPilot Desktop")
    print(f"  Mode: {'production' if prod_mode else 'development'}")
    print(f"{'='*50}\n")

    # Build if requested
    if do_build:
        if not build_frontend():
            sys.exit(1)
        prod_mode = True

    # Start backend
    backend_proc = None
    if not check_port(BACKEND_PORT):
        print("[StockPilot] Starting backend...")
        backend_proc = start_backend()
        if wait_for_port(BACKEND_PORT):
            print(f"[StockPilot] Backend ready on :{BACKEND_PORT}")
        else:
            print("[StockPilot] WARNING: Backend may not have started")
    else:
        print(f"[StockPilot] Backend already running on :{BACKEND_PORT}")

    # Determine URL
    if prod_mode:
        # In prod mode, backend serves static files from dist/
        # We need to configure FastAPI to serve static files
        url = f"http://localhost:{BACKEND_PORT}"
        print(f"[StockPilot] Prod mode: serving from {DIST_DIR}")
    else:
        # Dev mode: start Vite dev server
        frontend_proc = None
        if not check_port(FRONTEND_PORT):
            print("[StockPilot] Starting frontend dev server...")
            frontend_proc = start_frontend_dev()
            if wait_for_port(FRONTEND_PORT):
                print(f"[StockPilot] Frontend ready on :{FRONTEND_PORT}")
            else:
                print("[StockPilot] WARNING: Frontend may not have started")
        else:
            print(f"[StockPilot] Frontend already running on :{FRONTEND_PORT}")
        url = f"http://localhost:{FRONTEND_PORT}"

    # Open native window
    print(f"[StockPilot] Opening window -> {url}")
    window = webview.create_window(
        "StockPilot",
        url,
        width=1440,
        height=900,
        min_size=(1024, 680),
        background_color="#0a0a0f",
        text_select=True,
    )
    webview.start(debug=not prod_mode)

    # Cleanup on window close
    print("[StockPilot] Window closed, shutting down...")
    if backend_proc:
        backend_proc.terminate()


if __name__ == "__main__":
    main()
