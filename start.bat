@echo off
echo Starting Portfyl...

if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
        set "%%a=%%b"
    )
)

cd /d "%~dp0backend"

REM First run: create an isolated Python environment with uv (https://docs.astral.sh/uv/).
if not exist ".venv\Scripts\python.exe" (
    echo Setting up backend Python environment with uv...
    uv venv .venv --python 3.12 || goto :no_uv
    uv pip install --python ".venv\Scripts\python.exe" -r requirements.txt || goto :no_uv
)

start "Portfyl Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"

cd /d "%~dp0frontend"
start "Portfyl Frontend" cmd /k "npm install --silent && npm run dev"

echo.
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo.
timeout /t 5 >nul
start http://localhost:5173
goto :eof

:no_uv
echo.
echo  ERROR: could not create the backend Python environment.
echo  Install uv from https://docs.astral.sh/uv/ then run start.bat again.
echo.
pause
