# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec file for Chain-Breaker
# Build with: pyinstaller ChainBreaker.spec

block_cipher = None

a = Analysis(
    ['vault_cli.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('scripture_vault', 'scripture_vault'),
        ('*.md', '.'),
        ('requirements.txt', '.'),
    ],
    hiddenimports=[
        'pycryptodome',
        'httpx',
        'pydantic',
        'numpy',
        'cryptography',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ChainBreaker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',  # Add an icon file
)
