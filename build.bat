@echo off
REM StockPilot Build Script - package into standalone exe
REM Usage: build.bat

echo ============================================================
echo   StockPilot Build
echo ============================================================
echo.

REM Step 1: Build frontend
echo [1/3] Building frontend...
cd /d D:\StockPilot\frontend-v2
call node_modules\.bin\vite.cmd build
if %errorlevel% neq 0 (
    echo BUILD FAILED: frontend build error
    pause
    exit /b 1
)
echo       Frontend built OK
echo.

REM Step 2: Package with PyInstaller
echo [2/3] Packaging with PyInstaller...
cd /d D:\StockPilot
D:\Python313\python.exe -m PyInstaller --noconfirm --onedir --windowed ^
    --name "StockPilot" ^
    --add-data "backend;backend" ^
    --add-data "frontend-v2/dist;frontend-v2/dist" ^
    --add-data "data;data" ^
    --hidden-import uvicorn ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import webview ^
    desktop.py

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
echo   Output: D:\StockPilot\dist\StockPilot\StockPilot.exe
echo   Double-click to run.
echo.
pause
