@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "iniciar_demo.py" --manual %*
) else (
    python "iniciar_demo.py" --manual %*
)
if errorlevel 1 (
    echo.
    echo Confirme Python 3.11 ou superior e siga a instalacao no README.
)
pause
endlocal
