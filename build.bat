@echo off
REM StockPilot Build Script - package into standalone desktop exe
REM Usage: build.bat
REM
REM Produces: dist\StockPilot\StockPilot.exe  (onedir, double-click to run)
REM The bundled app serves the built frontend + API on 127.0.0.1:8000 and
REM opens it in a native pywebview window. User data lives in
REM %APPDATA%\StockPilot\data (never inside the install dir).

echo ============================================================
echo   StockPilot Desktop Build
echo ============================================================
echo.

REM --- Pick a Python that has pyinstaller + pywebview installed ---
set "PY_EXE=.venv\Scripts\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"
echo Using Python: %PY_EXE%

REM Ensure a config.yaml exists for packaging.
REM config.yaml is gitignored (holds local secrets); config.example.yaml is
REM committed, so a fresh clone can build without leaking anything.
if not exist "%~dp0config.yaml" (
    if exist "%~dp0config.example.yaml" (
        copy "%~dp0config.example.yaml" "%~dp0config.yaml" >nul
        echo   Generated config.yaml from config.example.yaml
    )
)

REM Ensure build tooling is present
"%PY_EXE%" -m pip install --quiet --upgrade pyinstaller 2>nul
"%PY_EXE%" -m pip install --quiet pywebview 2>nul

REM Step 1: Build frontend
echo [1/3] Building frontend...
cd /d "%~dp0frontend-v2"
call node_modules\.bin\vite.cmd build
if %errorlevel% neq 0 (
    echo BUILD FAILED: frontend build error
    pause
    exit /b 1
)
echo       Frontend built OK
echo.

REM Step 2: Package with PyInstaller
REM All bundling options (incl. privacy-safe exclusion of logs/db/ai_config)
REM live in StockPilot.spec so the published build never leaks local data.
echo [2/3] Packaging with PyInstaller...
cd /d "%~dp0"
"%PY_EXE%" -m PyInstaller --noconfirm StockPilot.spec

if %errorlevel% neq 0 (
    echo BUILD FAILED: PyInstaller error
    pause
    exit /b 1
)
echo       Package OK
echo.

REM Step 3: Done
echo [3/3] Done!
echo.
echo   Output: %~dp0dist\StockPilot\StockPilot.exe
echo   Double-click to run. User data is stored under %%APPDATA%%\StockPilot
echo.
pause
