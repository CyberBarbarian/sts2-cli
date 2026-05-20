@echo off
setlocal
chcp 65001 >nul
title sts2-cli
cd /d "%~dp0"

where py >nul 2>nul
if "%ERRORLEVEL%"=="0" (
    set "PYTHON_CMD=py -3"
) else (
    set "PYTHON_CMD=python"
)

%PYTHON_CMD% launch.py --lang en
set "STS2_EXIT=%ERRORLEVEL%"

if not "%STS2_EXIT%"=="0" (
    echo.
    echo sts2-cli exited with code %STS2_EXIT%.
    pause
)

exit /b %STS2_EXIT%
