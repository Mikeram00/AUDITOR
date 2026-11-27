@echo off
chcp 65001 >nul
title AUDITOR - Control Interno
cd /d "%~dp0"
python "AUDITOR.py"
if errorlevel 1 (
  echo.
  echo Algo fallo. Lee el mensaje de arriba.
  pause
)
