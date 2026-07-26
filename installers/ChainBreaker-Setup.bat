@echo off
setlocal EnableDelayedExpansion

title Chain-Breaker Scripture Vault Installer
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║                                                                  ║
echo  ║              CHAIN-BREAKER SCRIPTURE VAULT                       ║
echo  ║                    Windows Installer                              ║
echo  ║                                                                  ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.
echo  Distributed Scripture Preservation System
echo  Version 1.0.0
echo.
echo  ════════════════════════════════════════════════════════════════════
echo.

REM Check Windows version
ver | findstr /i "10\." > nul
if errorlevel 1 (
    ver | findstr /i "11\." > nul
    if errorlevel 1 (
        echo  ⚠️  Warning: Windows 10 or 11 recommended
        echo.
        pause
    )
)

REM Set installation paths
set "INSTALL_DIR=%PROGRAMFILES%\Chain-Breaker"
set "DATA_DIR=%LOCALAPPDATA%\Chain-Breaker"
set "START_MENU=%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Chain-Breaker"
set "DESKTOP=%PUBLIC%\Desktop"

REM Check for admin rights
net session > nul 2>&1
if errorlevel 1 (
    echo  ❌ Administrator rights required!
    echo.
    echo  Please right-click this file and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo  ✅ Running as Administrator
echo.

REM ═══════════════════════════════════════════════════════════════════
echo  Step 1: Checking System Requirements
echo  ═══════════════════════════════════════════════════════════════════
echo.

REM Check Python
python --version > nul 2>&1
if errorlevel 1 (
    python3 --version > nul 2>&1
    if errorlevel 1 (
        echo  ❌ Python not found!
        echo.
        echo  Installing Python automatically...
        echo.
        
        REM Download Python installer
        set "PYTHON_URL=https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe"
        set "PYTHON_INSTALLER=%TEMP%\python_installer.exe"
        
        echo  Downloading Python... (this may take a few minutes)
        powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'" 2> nul
        
        if exist "%PYTHON_INSTALLER%" (
            echo  ✅ Python downloaded
echo  Installing Python... (click through the installer)
            "%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
            
            REM Wait for installation
            timeout /t 10 > nul
            
            REM Verify Python installation
            python --version > nul 2>&1
            if errorlevel 1 (
                echo  ❌ Python installation failed
                echo  Please install manually from https://python.org
                pause
                exit /b 1
            )
        ) else (
            echo  ❌ Failed to download Python
            echo  Please install manually from https://python.org
            pause
            exit /b 1
        )
    )
)

for /f "tokens=*" %%a in ('python --version 2>&1') do set "PYTHON_VERSION=%%a"
echo  ✅ Python found: %PYTHON_VERSION%

REM Check Python version (need 3.11+)
python -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2> nul
if errorlevel 1 (
    echo  ⚠️  Python 3.11+ recommended (current may work but not tested)
)

echo.

REM Check Git
where git > nul 2>&1
if errorlevel 1 (
    echo  ⚠️  Git not found (optional but recommended)
    echo  Download from: https://git-scm.com/download/win
    echo.
)

echo.

REM ═══════════════════════════════════════════════════════════════════
echo  Step 2: Creating Directories
echo  ═══════════════════════════════════════════════════════════════════
echo.

echo  Creating installation directory...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
echo  ✅ %INSTALL_DIR%

echo  Creating data directory...  
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\nodes" mkdir "%DATA_DIR%\nodes"
if not exist "%DATA_DIR%\downloads" mkdir "%DATA_DIR%\downloads"
echo  ✅ %DATA_DIR%

echo  Creating Start Menu folder...
if not exist "%START_MENU%" mkdir "%START_MENU%"
echo  ✅ Start Menu

echo.

REM ═══════════════════════════════════════════════════════════════════
echo  Step 3: Installing Chain-Breaker
echo  ═══════════════════════════════════════════════════════════════════
echo.

echo  Downloading Chain-Breaker from GitHub...
echo.

REM Try to clone from private repo first, fall back to public
cd /d "%TEMP%"
if exist "chain-breaker-temp" rmdir /s /q "chain-breaker-temp"

git clone https://github.com/kaibuzz0/chain-breaker.git chain-breaker-temp 2> nul

if errorlevel 1 (
    echo  ⚠️  Private repository access not available
    echo  Installing public version...
    git clone https://github.com/kaibuzz0/Chain-breaker-public-repo.git chain-breaker-temp 2> nul
    
    if errorlevel 1 (
        echo  ❌ Failed to download from GitHub
        echo  Please check your internet connection
        pause
        exit /b 1
    )
    
    set "INSTALL_TYPE=public"
) else (
    set "INSTALL_TYPE=private"
)

echo  ✅ Repository downloaded (%INSTALL_TYPE% version)
echo.

echo  Copying files to installation directory...
xcopy /e /i /y "chain-breaker-temp\*" "%INSTALL_DIR%\" > nul
echo  ✅ Files installed

echo.
echo  Installing Python dependencies...
cd /d "%INSTALL_DIR%"
if exist "requirements.txt" (
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo  ⚠️  Some dependencies may have failed (non-critical)
    ) else (
        echo  ✅ Dependencies installed
    )
) else (
    echo  ⚠️  requirements.txt not found
)

REM Cleanup
cd /d "%TEMP%"
rmdir /s /q "chain-breaker-temp" 2> nul

echo.

REM ═══════════════════════════════════════════════════════════════════
echo  Step 4: Creating Shortcuts and Configuration
echo  ═══════════════════════════════════════════════════════════════════
echo.

echo  Creating configuration file...
(
echo {    
echo   "version": "1.0.0",
echo   "install_type": "%INSTALL_TYPE%",
echo   "install_date": "%DATE%",
echo   "install_path": "%INSTALL_DIR:=\%",
echo   "data_path": "%DATA_DIR:=\%",
echo   "first_run": true
echo }
) > "%INSTALL_DIR%\install_config.json"

echo  ✅ Configuration saved

echo.
echo  Creating shortcuts...

REM Create Start Menu shortcuts
echo Creating Start Menu shortcuts...

(
echo @echo off
echo cd /d "%INSTALL_DIR%"
echo python vault_cli.py --list
echo pause
) > "%START_MENU%\View Vault.bat"

echo Set oWS = WScript.CreateObject^("WScript.Shell"^) > "%TEMP%\CreateShortcut.vbs"
echo sLinkFile = "%START_MENU%\View Vault.lnk" >> "%TEMP%\CreateShortcut.vbs"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^) >> "%TEMP%\CreateShortcut.vbs"
echo oLink.TargetPath = "%INSTALL_DIR%\vault_cli.py" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.Arguments = "--list" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.IconLocation = "%SYSTEMROOT%\System32\SHELL32.dll,14" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.Save >> "%TEMP%\CreateShortcut.vbs"
cscript //nologo "%TEMP%\CreateShortcut.vbs"
del "%TEMP%\CreateShortcut.vbs"

REM Create Desktop shortcut
echo Creating Desktop shortcut...
copy "%START_MENU%\View Vault.lnk" "%DESKTOP%\Chain-Breaker Vault.lnk" > nul
echo  ✅ Desktop shortcut created

REM Create Uninstaller
echo.
echo  Creating uninstaller...
(
echo @echo off
echo title Chain-Breaker Uninstaller
echo echo Uninstalling Chain-Breaker...
echo echo.
echo choice /C YN /M "Are you sure you want to uninstall?"
echo if errorlevel 2 exit
echo.
echo echo Removing files...
echo rmdir /s /q "%INSTALL_DIR%"
echo rmdir /s /q "%DATA_DIR%"
echo del "%DESKTOP%\Chain-Breaker Vault.lnk"
echo rmdir /s /q "%START_MENU%"
echo.
echo echo ✅ Chain-Breaker has been uninstalled
echo pause
) > "%INSTALL_DIR%\uninstall.bat"

echo  ✅ Uninstaller created

REM Add to PATH (optional)
echo.
echo  Adding to system PATH...
setx /M PATH "%PATH%;%INSTALL_DIR%" > nul 2>&1
echo  ✅ Added to PATH

echo.

REM ═══════════════════════════════════════════════════════════════════
echo  Installation Complete!
echo  ═══════════════════════════════════════════════════════════════════
echo.

echo  ✅ Chain-Breaker Scripture Vault has been installed!
echo.
echo  Installation Type: %INSTALL_TYPE%
echo  Location: %INSTALL_DIR%
echo  Data: %DATA_DIR%
echo.
echo  Quick Start:
echo    • View Vault: Click "Chain-Breaker Vault" on your desktop
echo    • Start Menu: All Programs ^> Chain-Breaker
echo    • Command Line: Run "python -m chainbreaker"
echo.
echo  Documentation:
echo    https://github.com/kaibuzz0/chain-breaker

echo.
echo  ════════════════════════════════════════════════════════════════════
echo.

REM Launch the vault
choice /C YN /M "Would you like to view your vault now?"
if errorlevel 2 goto end
cd /d "%INSTALL_DIR%"
python vault_cli.py --list
pause

:end
echo.
echo  Thank you for installing Chain-Breaker!
echo.
echo  ⚡ Preserving Scripture for Eternity ⚡
echo.
pause
