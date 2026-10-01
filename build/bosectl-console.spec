# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the console CLI (``bosectl-cli.exe``).

Build with::

    pyinstaller --clean --noconfirm --workpath build/work --distpath dist build/bosectl-console.spec

The executable is deliberately named ``bosectl-cli.exe``, not ``bosectl.exe``:
``BoseCtl.exe`` and ``bosectl.exe`` lower-case to the same string, so on a
case-insensitive filesystem they are one file. Downloading both artefacts from
a Release into the same folder would silently overwrite one with the other,
and the CI job that verifies checksums would do the same to itself. The
suffix also matches the spec's own name, so it is clear which build produced
which binary.

Kept separate from the GUI spec on purpose: the CLI has no GUI dependency,
so excluding tkinter, customtkinter and Pillow cuts the executable from
roughly 30 MB to a couple of MB and removes the slow first-launch unpack of
the GUI's theme assets. Windows also fixes the console/windowed subsystem at
link time, so one binary cannot serve both roles well.
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
    name="bosectl-cli",
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
    version=version_info._vs_version_info("bosectl-cli.exe", "bosectl-cli"),
)
