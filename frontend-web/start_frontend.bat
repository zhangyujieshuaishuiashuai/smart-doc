@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Frontend Starter

echo ========================================
echo Frontend Auto Start Script
echo ========================================
echo.

if not exist package.json (
    echo [ERROR] package.json not found
    echo Please put this bat file in the frontend project root
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found
    pause
    exit /b 1
)

if not exist node_modules (
    echo [INFO] node_modules not found, running npm install...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed
        pause
        exit /b 1
    )
)

echo.
echo [INFO] starting vite dev server...
call npm run dev

echo.
echo [INFO] process ended
pause
