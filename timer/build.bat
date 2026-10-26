@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "BUILD_PY=%~dp0venv\Scripts\python.exe"

if not exist "%BUILD_PY%" (
    echo Creating build environment for the first time...
    python -m venv "%~dp0venv" --system-site-packages
    if errorlevel 1 goto :error
)

"%BUILD_PY%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    "%BUILD_PY%" -m pip install pyinstaller
    if errorlevel 1 goto :error
)

"%BUILD_PY%" build.py
if errorlevel 1 goto :error

echo.
echo Build finished. See the dist folder.
pause
exit /b 0

:error
echo.
echo Build failed. Please check that Python and PyInstaller are installed.
pause
exit /b 1
