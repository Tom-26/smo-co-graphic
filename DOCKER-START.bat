@echo off
cd /d "%~dp0"
if errorlevel 1 goto folder_error
where docker >nul 2>&1
if errorlevel 1 goto docker_missing
docker compose version >nul 2>&1
if errorlevel 1 goto compose_missing
docker compose up -d --build
if errorlevel 1 goto failed
echo.
echo Control: http://127.0.0.1:18770/control.html
echo OBS:     http://127.0.0.1:18770/overlay.html
echo Keep Docker Desktop running during the broadcast.
start "" "http://127.0.0.1:18770/control.html"
pause
exit /b 0
:folder_error
echo ERROR: Cannot open the application folder.
pause
exit /b 1
:docker_missing
echo ERROR: Docker was not found. Install and start Docker Desktop.
pause
exit /b 1
:compose_missing
echo ERROR: Docker Compose is not available. Check Docker Desktop installation.
pause
exit /b 1
:failed
echo.
echo ERROR: Startup failed. Check Docker Desktop and the error messages above.
pause
exit /b 1
