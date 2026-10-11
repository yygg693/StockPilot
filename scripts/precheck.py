"""StockPilot Frontend Pre-check - catches syntax errors before they hit the browser."""
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend-v2"
VITE_CMD = os.path.join(str(FRONTEND_DIR), "node_modules", ".bin", "vite.cmd")


def run_build_check():
    """Run vite build in dry mode to catch compilation errors."""
    print("\n[Frontend Pre-check] Running vite build (syntax validation)...")
    print("-" * 60)

    result = subprocess.run(
        [VITE_CMD, "build", "--mode", "development"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode == 0:
        print("  [+] PASS  Frontend builds successfully")
        return True
    else:
        print("  [!] FAIL  Frontend build failed:")
        # Extract the useful error lines
        stderr = result.stderr or ""
        stdout = result.stdout or ""
        output = stderr + stdout
        lines = output.split("\n")
        error_lines = []
        for i, line in enumerate(lines):
            if "error" in line.lower() or "Error" in line:
                # Print context around error
                start = max(0, i - 1)
                end = min(len(lines), i + 4)
                error_lines.extend(lines[start:end])
                error_lines.append("")

        if error_lines:
            for line in error_lines[:30]:
                print(f"        {line}")
        else:
            # Just print last 20 lines
            for line in lines[-20:]:
                print(f"        {line}")
        return False


def check_undefined_imports():
    """Quick scan for common issues in api/index.ts."""
    print("\n[Frontend Pre-check] Scanning for undefined references...")
    print("-" * 60)

    api_file = os.path.join(FRONTEND_DIR, "src", "api", "index.ts")
    if not os.path.exists(api_file):
        print("  [!] FAIL  api/index.ts not found")
        return False

    with open(api_file, "r", encoding="utf-8") as f:
        content = f.read()

    issues = []

    # Check for undefined 'request' usage
    if "request(" in content and "function request" not in content and "const request" not in content:
        issues.append("api/index.ts uses 'request()' but it's not defined (should use 'api')")

    # Check for unbalanced quotes in string literals
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        # Simple check: odd number of unescaped single quotes
        stripped = line.split("//")[0]  # remove comments
        sq = stripped.count("'") - stripped.count("\\'")
        if sq % 2 != 0 and "import" not in stripped:
            issues.append(f"Line {i}: possibly unbalanced quotes: {stripped.strip()[:60]}")

    if issues:
        for issue in issues:
            print(f"  [!] WARN  {issue}")
        return len(issues) == 0
    else:
        print("  [+] PASS  No undefined references found")
        return True


def check_vue_components():
    """Check that all imported components exist."""
    print("\n[Frontend Pre-check] Verifying component imports...")
    print("-" * 60)

    src_dir = os.path.join(FRONTEND_DIR, "src")
    issues = []

    for root, dirs, files in os.walk(src_dir):
        for fname in files:
            if not fname.endswith(".vue"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()

            # Find component imports
            import re
            imports = re.findall(r'import\s+\w+\s+from\s+["\'](@/[^"\']+)["\']', content)
            for imp in imports:
                # Resolve @/ to src/
                rel = imp.replace("@/", "").replace(".vue", "")
                candidates = [
                    os.path.join(src_dir, rel + ".vue"),
                    os.path.join(src_dir, rel + ".ts"),
                    os.path.join(src_dir, rel, "index.ts"),
                ]
                if not any(os.path.exists(c) for c in candidates):
                    issues.append(f"{fname}: import '{imp}' -> file not found")

    if issues:
        for issue in issues:
            print(f"  [!] FAIL  {issue}")
        return False
    else:
        print("  [+] PASS  All component imports resolve")
        return True


if __name__ == "__main__":
    results = []
    results.append(("Build check", run_build_check()))
    results.append(("Undefined refs", check_undefined_imports()))
    results.append(("Component imports", check_vue_components()))

    print(f"\n{'='*60}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"  Frontend Pre-check: {passed}/{total} passed")
    print(f"{'='*60}\n")
    sys.exit(0 if passed == total else 1)
