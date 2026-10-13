@echo off
setlocal
if exist "%~dp0..\..\.venv\Scripts\python.exe" (
    "%~dp0..\..\.venv\Scripts\python.exe" "%~dp0code_stats.py" %*
    goto result
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0code_stats.py" %*
    goto result
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0code_stats.py" %*
    goto result
)
echo Python nebyl nalezen. Nainstalujte Python 3.10 nebo novejsi.
pause
exit /b 1
:result
if errorlevel 1 (
    echo Prehled se nepodarilo aktualizovat.
    pause
    exit /b 1
)
endlocal
