@echo off
chcp 65001 >nul
cd /d "%~dp0"
docker compose up -d --build
if errorlevel 1 (
  echo Не удалось запустить приложение. Проверьте, что Docker Desktop запущен.
  pause
  exit /b 1
)
echo Пульт: http://127.0.0.1:18770/control.html
echo Графика OBS: http://127.0.0.1:18770/overlay.html
start http://127.0.0.1:18770/control.html
pause
