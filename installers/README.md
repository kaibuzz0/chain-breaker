# Windows Installers for Chain-Breaker

Easy Windows installation options for Chain-Breaker Scripture Vault.

---

## 🚀 Quick Install Options

### Option 1: One-Click Installer (Recommended)

**File:** `ChainBreaker-Setup.bat`

**What it does:**
- ✅ Checks for Python (auto-downloads if missing)
- ✅ Downloads Chain-Breaker from GitHub
- ✅ Installs dependencies
- ✅ Creates Start Menu and Desktop shortcuts
- ✅ Adds to PATH
- ✅ Creates uninstaller

**Requirements:**
- Windows 10 or 11
- Internet connection
- Administrator rights

**How to use:**
1. Download `ChainBreaker-Setup.bat`
2. Right-click → "Run as Administrator"
3. Follow prompts
4. Done! 🎉

---

### Option 2: Quick Install (If you have Python)

**File:** `quick-install.bat`

**Requirements:**
- Python 3.11+ already installed
- Git installed
- Internet connection

**How to use:**
1. Download `quick-install.bat`
2. Double-click to run
3. Done!

---

### Option 3: Professional Installer (.exe)

**Build from:** `installer.nsi`

**Requirements:**
- NSIS (Nullsoft Scriptable Install System)
- Download: https://nsis.sourceforge.io/

**How to build:**
1. Install NSIS
2. Right-click `installer.nsi` → "Compile NSIS Script"
3. Get `ChainBreaker-Setup.exe`

**Features:**
- Professional wizard interface
- Install/uninstall support
- Registry integration
- Desktop and Start Menu shortcuts

---

### Option 4: Standalone Executable

**Build from:** `ChainBreaker.spec`

**Requirements:**
- PyInstaller
- All Python dependencies

**How to build:**
```bash
pip install pyinstaller
pyinstaller ChainBreaker.spec
```

**Result:** Single `.exe` file that runs without Python installed

---

## 📥 Download

All installers are available at:
https://github.com/kaibuzz0/chain-breaker/tree/main/installers

---

## 🔧 System Requirements

**Minimum:**
- Windows 10 (64-bit)
- 4 GB RAM
- 1 GB free disk space
- Internet connection

**Recommended:**
- Windows 11 (64-bit)
- 8 GB RAM
- 5 GB free disk space
- Broadband internet

---

## 📂 What Gets Installed

```
C:\Program Files\Chain-Breaker\
├── scripture_vault/        ← Main application
├── vault_cli.py           ← Command-line tool
├── requirements.txt       ← Dependencies
└── install_config.json   ← Installation settings

C:\Users\[You]\AppData\Local\Chain-Breaker\
├── data/                  ← Your data
├── downloads/            ← Downloaded texts
└── nodes/               ← Node configuration

Start Menu:
└── Chain-Breaker
    ├── View Vault       ← Launch shortcut
    └── Uninstall        ← Remove program

Desktop:
└── Chain-Breaker Vault.lnk
```

---

## 🎮 Using Chain-Breaker

### After Installation:

**Option A: Desktop Shortcut**
- Double-click "Chain-Breaker Vault" on your desktop

**Option B: Start Menu**
- Start Menu → All Programs → Chain-Breaker → View Vault

**Option C: Command Line**
```cmd
chainbreaker --list
chainbreaker --find "josephus"
chainbreaker --verify
```

---

## 🗑️ Uninstallation

**Method 1: Start Menu**
- Start Menu → Chain-Breaker → Uninstall

**Method 2: Settings**
- Settings → Apps → Chain-Breaker Scripture Vault → Uninstall

**Method 3: Manually**
- Delete `C:\Program Files\Chain-Breaker\`
- Delete `C:\Users\[You]\AppData\Local\Chain-Breaker\`
- Remove Start Menu and Desktop shortcuts

---

## 🐛 Troubleshooting

### "Python not found"
- The installer should auto-download Python
- If it fails, install manually from https://python.org
- Check "Add Python to PATH" during installation

### "Git clone failed"
- Check internet connection
- Try again (temporary GitHub issue)
- Use GitHub Desktop as alternative

### "Access denied"
- Make sure to run installer as Administrator
- Right-click → "Run as Administrator"

### "Antivirus blocked"
- Add exception for Chain-Breaker
- Windows Defender may show warning (click "More info" → "Run anyway")

---

## 📞 Support

- 📧 Email: [your-email]
- 🐛 Issues: https://github.com/kaibuzz0/chain-breaker/issues
- 📖 Docs: https://github.com/kaibuzz0/chain-breaker/wiki

---

## ⚖️ License

Chain-Breaker is open source under MIT License.

The Windows installers are also MIT licensed and free to use.

---

**⚡ Chain-Breaker: Preserving Scripture for Eternity ⚡**
