@echo off
setlocal
cd /d "%~dp0"

title Chess AI V2 - Starter

echo ========================================
echo          CHESS AI V2
echo ========================================
echo.

REM Find a Python installation.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo FEHLER: Python wurde nicht gefunden.
        echo Bitte Python 3.11 oder neuer installieren und PATH aktivieren.
        echo https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

REM Create the virtual environment on first launch.
if not exist ".venv\Scripts\python.exe" (
    echo Erstelle virtuelle Python-Umgebung ...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

echo Pruefe und installiere Abhaengigkeiten ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto :error

echo.
echo Starte Chess AI V2 ...
".venv\Scripts\python.exe" -m chess_ai_v2.app
if errorlevel 1 goto :error

exit /b 0

:error
echo.
echo Beim Einrichten oder Starten ist ein Fehler aufgetreten.
echo Pruefe, ob Python 3.11 oder neuer installiert ist.
pause
exit /b 1
