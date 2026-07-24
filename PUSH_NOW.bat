@echo off
echo Chain-Breaker Git Setup
echo ========================
echo.
echo This will configure Git and push to GitHub.
echo.
pause

cd /d "D:\Hermes-USB-Portable-main\src\chain-breaker"

echo.
echo [1/6] Initializing Git...
git init

echo.
echo [2/6] Configuring user...
git config user.email "chain-breaker@example.com"
git config user.name "Chain-Breaker Developer"

echo.
echo [3/6] Adding files...
git add .

echo.
echo [4/6] Committing...
git commit -m "Initial commit: E8-Enhanced Blockchain"

echo.
echo [5/6] Setting up remote...
git branch -M main
git remote remove origin 2>nul
git remote add origin https://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@github.com/kaibuzz0/chain-breaker.git

echo.
echo [6/6] Pushing to GitHub...
git push -u origin main --force

echo.
echo Done! Check https://github.com/kaibuzz0/chain-breaker
echo.
pause
