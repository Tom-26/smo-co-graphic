@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (py -3 scripts\start_all.py) else (python scripts\start_all.py)
if errorlevel 1 pause
