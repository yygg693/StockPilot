"""StockPilot Watchdog - process monitor with auto-restart + log error detection."""
import subprocess
import time
import os
import sys
import signal
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_CMD = ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"]
BACKEND_CWD = PROJECT_ROOT
FRONTEND_CMD = [str(PROJECT_ROOT / "frontend-v2" / "node_modules" / ".bin" / "vite.cmd"), "--port", "5173", "--strictPort"]
FRONTEND_CWD = PROJECT_ROOT / "frontend-v2"

CHECK_INTERVAL = 10  # seconds between health checks
MAX_RESTARTS = 5     # max restarts before giving up
RESTART_COOLDOWN = 5  # seconds to wait after restart


class ProcessGuard:
    def __init__(self, name, cmd, cwd, port):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.port = port
        self.process = None
        self.restart_count = 0
        self.last_restart = 0

    def is_alive(self):
        if self.process is None:
            return False
        return self.process.poll() is None

    def start(self):
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        log_file = open(os.path.join(BACKEND_CWD, f"{self.name}.log"), "a", encoding="utf-8")
        self.process = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=0x00000008 | 0x00000200,  # DETACHED + CREATE_NEW_PROCESS_GROUP
        )
        print(f"  [{self.name}] Started (PID {self.process.pid})")
        return self.process.pid

    def stop(self):
        if self.process and self.is_alive():
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print(f"  [{self.name}] Stopped")

    def maybe_restart(self):
        if self.restart_count >= MAX_RESTARTS:
            print(f"  [{self.name}] Max restarts ({MAX_RESTARTS}) reached, giving up")
            return False
        now = time.time()
        if now - self.last_restart < RESTART_COOLDOWN:
            time.sleep(RESTART_COOLDOWN)
        self.restart_count += 1
        self.last_restart = now
        print(f"  [{self.name}] Restarting (attempt {self.restart_count}/{MAX_RESTARTS})...")
        self.start()
        time.sleep(3)  # wait for startup
        return True


def check_port(port):
    """Check if a port is listening (IPv4 + IPv6)."""
    import socket
    for host in ["127.0.0.1", "::1"]:
        try:
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                if s.connect_ex((host, port)) == 0:
                    return True
        except Exception:
            continue
    return False


def scan_log_errors(log_path, since_line=0):
    """Scan log file for new ERROR/CRITICAL/Traceback lines."""
    errors = []
    if not os.path.exists(log_path):
        return errors, since_line
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for i in range(since_line, len(lines)):
            line = lines[i]
            if any(kw in line for kw in ["ERROR", "CRITICAL", "Traceback", "Exception"]):
                errors.append(f"L{i+1}: {line.strip()[:100]}")
        return errors, len(lines)
    except Exception:
        return errors, since_line


def main():
    print(f"\n{'='*60}")
    print(f"  StockPilot Watchdog")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Monitoring: backend(:8000) + frontend(:5173)")
    print(f"  Check interval: {CHECK_INTERVAL}s")
    print(f"{'='*60}\n")

    backend = ProcessGuard("backend", BACKEND_CMD, BACKEND_CWD, 8000)
    frontend = ProcessGuard("frontend", FRONTEND_CMD, FRONTEND_CWD, 5173)

    # Check if already running
    if check_port(8000):
        print("  [backend] Already running on :8000")
    else:
        backend.start()
        time.sleep(3)

    if check_port(5173):
        print("  [frontend] Already running on :5173")
    else:
        frontend.start()
        time.sleep(3)

    backend_log_line = 0
    frontend_log_line = 0
    cycle = 0

    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            cycle += 1

            # Port checks
            backend_ok = check_port(8000)
            frontend_ok = check_port(5173)

            status = f"[{datetime.now().strftime('%H:%M:%S')}] backend:{'OK' if backend_ok else 'DOWN'} frontend:{'OK' if frontend_ok else 'DOWN'}"

            if not backend_ok:
                print(f"  {status} -> restarting backend")
                backend.maybe_restart()
            elif not frontend_ok:
                print(f"  {status} -> restarting frontend")
                frontend.maybe_restart()
            elif cycle % 6 == 0:  # Print status every ~60s
                print(f"  {status}")

            # Log error scanning (every 3 cycles)
            if cycle % 3 == 0:
                errors, backend_log_line = scan_log_errors(
                    os.path.join(BACKEND_CWD, "backend.log"), backend_log_line
                )
                if errors:
                    print(f"  [backend] {len(errors)} new error(s) in log:")
                    for e in errors[-3:]:
                        print(f"    {e}")

    except KeyboardInterrupt:
        print("\n  Watchdog stopped by user")
    finally:
        # Don't kill child processes - they should keep running
        print("  Watchdog exiting (services continue running)")


if __name__ == "__main__":
    main()
