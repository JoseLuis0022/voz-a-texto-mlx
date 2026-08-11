# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para empaquetar Voz a Texto como app .app de macOS.

Uso:
    ./.venv/bin/pyinstaller packaging/VozATexto.spec --noconfirm

El resultado queda en dist/Voz a Texto.app
"""

import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"

a = Analysis(
    [str(APP_DIR / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(APP_DIR / "resources"), "app/resources"),
    ],
    hiddenimports=[
        "mlx_whisper",
        "mlx_whisper.audio",
        "mlx",
        "huggingface_hub",
        "psutil",
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
    [],
    exclude_binaries=True,
    name="VozATexto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VozATexto",
)

app = BUNDLE(
    coll,
    name="Voz a Texto.app",
    icon=None,  # TODO: apuntar a app/resources/icon.icns cuando exista
    bundle_identifier="com.joseluismacedo.vozatexto",
    info_plist={
        "CFBundleName": "Voz a Texto",
        "CFBundleDisplayName": "Voz a Texto",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
)
