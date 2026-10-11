# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files


def _collect_backend_datas():
    """Walk the backend package but skip runtime artifacts.

    PyInstaller would otherwise bundle the whole directory verbatim, which can
    leak local logs / databases / saved API keys (e.g. backend/server.log,
    ai_config.json) into the distributed build. Exclude those here so the
    published bundle only contains source + safe assets."""
    EXCLUDE_DIRS = {"__pycache__", ".git"}
    EXCLUDE_SUFFIXES = (".log", ".db", ".db-wal", ".db-shm", ".pyc", ".pyo")
    EXCLUDE_NAMES = {"ai_config.json"}
    out = []
    for dirpath, dirnames, filenames in os.walk("backend"):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn in EXCLUDE_NAMES or fn.endswith(EXCLUDE_SUFFIXES):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ".")
            out.append((full, os.path.dirname(rel)))
    return out


datas = _collect_backend_datas()
datas += [('frontend-v2/dist', 'frontend-v2/dist'), ('config.yaml', '.')]
datas += collect_data_files('webview')


a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'webview', 'backend.app.main'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['xtquant', 'akshare', 'pandas', 'numpy', 'openai'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StockPilot',
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StockPilot',
)
