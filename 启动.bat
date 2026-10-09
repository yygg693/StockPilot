@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   StockPilot 个人 AI 投资助手 启动中...
echo ============================================
echo.

REM 1. 确保虚拟环境（项目内 .venv，自动创建，可移植）
set "VENV=.venv"
if not exist "%VENV%\Scripts\python.exe" (
    echo [1/4] 未检测到虚拟环境，正在创建 %VENV% ...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo 创建虚拟环境失败：请先安装 Python 3.11+ 并加入 PATH 后重试。
        pause
        exit /b 1
    )
)

REM 2. 安装依赖（幂等：已安装则快速跳过）
echo [2/4] 安装/校验依赖 (requirements.txt) ...
call "%VENV%\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败，请检查网络与 requirements.txt。
    pause
    exit /b 1
)

REM 3. 启动后端（端口与 config.yaml 一致，默认 8000）
echo [3/4] 启动后端服务 http://127.0.0.1:8000 ...
start "StockPilot-Backend" cmd /k "%VENV%\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"

REM 4. 等待后端就绪（轮询 /api/health，最多 30 秒）
echo [4/4] 等待后端就绪并做健康检查...
set "PY=%VENV%\Scripts\python.exe"
set tries=0
:waitloop
"%PY%" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3); sys.exit(0)" >nul 2>&1
if %errorlevel%==0 goto healthy
set /a tries+=1
if %tries% geq 30 (
    echo 后端 30 秒内未就绪，请查看 "StockPilot-Backend" 窗口日志。
    goto end
)
timeout /t 1 >nul
goto waitloop

:healthy
echo.
echo ============================================
echo   启动完成！
echo   后端 API : http://127.0.0.1:8000
echo   Swagger  : http://127.0.0.1:8000/docs
echo   健康检查 : http://127.0.0.1:8000/api/health
echo ============================================
echo.
echo   关闭后端：结束 "StockPilot-Backend" 窗口，或在其内按 Ctrl+C。
echo.

:end
pause
