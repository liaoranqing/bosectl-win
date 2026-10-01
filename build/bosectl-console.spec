# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the console CLI (``bosectl.exe``).

Build with::

    pyinstaller --clean --noconfirm build/bosectl-console.spec

Kept separate from the GUI spec on purpose: the CLI has no GUI dependency,
so excluding tkinter, customtkinter and Pillow cuts the executable from
roughly 30 MB to a couple of MB and removes the slow first-launch unpack of
the GUI's theme assets. Windows also fixes the console/windowed subsystem at
link time, so one binary cannot serve both roles well.

(The name avoids differing from ``BoseCtl-window.spec`` by letter case only —
see the note in that file.)
"""

import os
import sys

sys.path.insert(0, SPECPATH)

import version_info  # noqa: E402  (local build helper in this directory)

ROOT = os.path.dirname(SPECPATH)
ENTRY = os.path.join(SPECPATH, "entry_cli.py")

datas = []

hiddenimports = [
    # Imported lazily inside pybmap so the library stays import-light; the
    # freezer has to be told about them explicitly.
    "pybmap.cli",
    "pybmap.mock",
    "pybmap.discovery",
]

excludes = [
    "tkinter", "customtkinter", "darkdetect", "PIL",
    "gui",
    "pytest", "_pytest", "unittest", "doctest", "pydoc",
    "numpy", "scipy", "pandas", "matplotlib",
    "IPython", "notebook", "setuptools", "pip", "wheel",
]

a = Analysis(
    [ENTRY],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="bosectl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,              # keep stdout/stderr attached
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, "icon.ico"),
    version=version_info._vs_version_info("bosectl.exe", "bosectl"),
)
