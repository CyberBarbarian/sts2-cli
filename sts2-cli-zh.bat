@echo off
setlocal
chcp 65001 >nul
title sts2-cli zh
cd /d "%~dp0"

python --version >nul 2>nul
if "%ERRORLEVEL%"=="0" (
    set "PYTHON_CMD=python"
) else (
    py -3 --version >nul 2>nul
    if "%ERRORLEVEL%"=="0" (
        set "PYTHON_CMD=py -3"
    ) else (
        echo Python 3.9 or newer is required.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% launch.py --lang zh
set "STS2_EXIT=%ERRORLEVEL%"

if not "%STS2_EXIT%"=="0" (
    echo.
    echo sts2-cli exited with code %STS2_EXIT%.
    pause
)

exit /b %STS2_EXIT%
