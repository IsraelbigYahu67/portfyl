@echo off
echo Starting Portfyl...

if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
        set "%%a=%%b"
    )
)

if not defined PORTFYL_EDITION set "PORTFYL_EDITION=local"

REM Local PostgreSQL runs in Docker (deploy\docker-compose.postgres-dev.yml, port 55432).
REM Start Docker Desktop if the daemon is not up yet, then bring the DB container up.
docker info >nul 2>&1 && goto :docker_ready
echo Docker is not running - starting Docker Desktop...
if not exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" goto :no_docker
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a DOCKER_WAIT=0
:wait_docker
timeout /t 3 >nul
docker info >nul 2>&1 && goto :docker_ready
set /a DOCKER_WAIT+=1
if %DOCKER_WAIT% lss 40 goto :wait_docker
goto :no_docker

:docker_ready
echo Starting local database container...
docker compose -f "%~dp0deploy\docker-compose.postgres-dev.yml" up -d --wait || goto :no_docker

cd /d "%~dp0backend"

REM First run: create an isolated Python environment with uv (https://docs.astral.sh/uv/).
if not exist ".venv\Scripts\python.exe" (
    echo Setting up backend Python environment with uv...
    uv venv .venv --python 3.12 || goto :no_uv
    uv pip install --python ".venv\Scripts\python.exe" --require-hashes -r requirements.lock || goto :no_uv
)

start "Portfyl Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"

cd /d "%~dp0frontend"
start "Portfyl Frontend" cmd /k "npm install --silent && npm run dev"

echo.
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo.
REM Open Chrome as soon as the frontend answers, so the tab never lands on a connection error.
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

set /a FRONTEND_WAIT=0
:wait_frontend
curl -s -o nul http://localhost:5173 && goto :open_browser
set /a FRONTEND_WAIT+=1
if %FRONTEND_WAIT% geq 120 goto :open_browser
timeout /t 1 >nul
goto :wait_frontend

:open_browser
if defined CHROME (
    start "" "%CHROME%" http://localhost:5173
) else (
    start http://localhost:5173
)
goto :eof

:no_docker
echo.
echo  ERROR: could not start the local database in Docker.
echo  Start Docker Desktop, wait until it is running, then run start.bat again.
echo.
pause
goto :eof

:no_uv
echo.
echo  ERROR: could not create the backend Python environment.
echo  Install uv from https://docs.astral.sh/uv/ then run start.bat again.
echo.
pause
