@echo off
echo ============================================
echo   Chain-Breaker Quick Installer
echo ============================================
echo.

REM Check Python
python --version > nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found!
    echo Please install Python from https://python.org
    echo Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

echo ✅ Python found

REM Create directory
set "INSTALL_DIR=%USERPROFILE%\Chain-Breaker"
mkdir "%INSTALL_DIR%" 2> nul

echo.
echo Downloading Chain-Breaker...
cd /d "%TEMP%"

git clone https://github.com/kaibuzz0/chain-breaker.git temp_cb 2> nul
if errorlevel 1 (
    echo Trying public repository...
    git clone https://github.com/kaibuzz0/Chain-breaker-public-repo.git temp_cb
)

xcopy /e /i /y "temp_cb\*" "%INSTALL_DIR%\" > nul
rmdir /s /q "temp_cb"

cd /d "%INSTALL_DIR%"
pip install -r requirements.txt --quiet

echo.
echo ✅ Installation complete!
echo Location: %INSTALL_DIR%
echo.
pause
