@echo off
echo Chain-Breaker GitHub Push Script
echo ==================================
echo.

REM Check if git is installed
where git > nul 2>&1
if %errorlevel% neq 0 (
    echo Git not found. Installing...
    winget install Git.Git
    echo Please restart this script after Git is installed.
    pause
    exit /b
)

REM Check if in right directory
if not exist "demo.py" (
    echo Error: Run this script from the chain-breaker directory
    pause
    exit /b
)

REM Initialize if needed
if not exist ".git" (
    echo Initializing git repository...
    git init
)

echo Adding files...
git add .

echo Committing...
git commit -m "Initial commit: E8-Enhanced Blockchain for Scripture"

echo Setting branch to main...
git branch -M main

echo Adding remote...
git remote add origin https://github.com/kaibuzz0/chain-breaker.git 2>nul

echo Pushing to GitHub...
git push -u origin main

echo.
echo Done!
pause
