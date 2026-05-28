# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for bpc-fetch Windows exe."""
from pathlib import Path
import sys

block_cipher = None
src_root = Path("src/bpc_fetch")
data_root = Path("data")

a = Analysis(
    [str(src_root / "__main__.py")],
    pathex=[],
    binaries=[],
    datas=[
        (str(data_root / "sites.js"), "data"),
        (str(data_root / "sites_cache.json"), "data"),
    ],
    hiddenimports=[
        "bpc_fetch",
        "bpc_fetch.cli",
        "bpc_fetch.sites",
        "bpc_fetch.strategy",
        "bpc_fetch.extract",
        "bpc_fetch.search",
        "bpc_fetch.browser",
        "bpc_fetch.discover",
        "bpc_fetch.crawl",
        "trafilatura",
        "markdownify",
        "bs4",
        "httpx",
        "playwright",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
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
    name="bpc-fetch",
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
)
