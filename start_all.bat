@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 定位项目根目录
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo ===================================================
echo [初始化] 配置多模态 RAG 平台启动变量
set "DEEPSEEK_KEY=sk-96ae8a9a321e4340948676718ff8ec0b"
set /p USER_INPUT="请输入 DeepSeek API Key (如需使用默认值请直接回车): "
if not "!USER_INPUT!"=="" set "DEEPSEEK_KEY=!USER_INPUT!"
echo [生效参数] 当前挂载的 API Key 为: !DEEPSEEK_KEY!
echo ===================================================

echo [1/3] 正在挂载 AI Engine 进程 (端口 8000) ...
start "ai-engine" cmd /k cd /d "%ROOT%\ai-engine" ^&^& set DATA_DIR=%ROOT%\data ^&^& set OPENAI_API_KEY=!DEEPSEEK_KEY! ^&^& set OPENAI_BASE_URL=https://api.deepseek.com ^&^& set OPENAI_MODEL=deepseek-chat ^&^& python -m uvicorn core.main:app --host 127.0.0.1 --port 8000

echo [2/3] 正在挂载 Backend 进程 (端口 8080) ...
start "backend" cmd /k cd /d "%ROOT%\backend-server" ^&^& call mvnw.cmd spring-boot:run

echo [3/3] 正在挂载 Frontend 进程 (端口 5173) ...
start "frontend" cmd /k cd /d "%ROOT%\frontend-web" ^&^& npm install ^&^& npm run dev

echo ===================================================
echo 服务派发指令已全量投递。
echo ===================================================
pause
endlocal