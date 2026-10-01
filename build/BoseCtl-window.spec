# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the windowed desktop app (``BoseCtl.exe``).

Build with::

    pyinstaller --clean --noconfirm build/BoseCtl-window.spec

The file name deliberately differs from ``bosectl-console.spec`` by more than
letter case. Windows and macOS filesystems are case-insensitive, so names like
``BoseCtl.spec`` and ``bosectl.spec`` are *the same file* there: git stores
one, silently drops the other, and the checkout is missing a spec. That is why
this repository bans case-only collisions — see
``tests/test_version.py::test_no_tracked_paths_collide_by_letter_case``.

Notes on the choices here:

* **One file.** A single portable .exe is what "just run it" means on
  Windows. The trade-off is a 2-3 s first-launch unpack; ``docs/BUILD.md``
  describes the onedir alternative for anyone who wants a faster start.
* **``console=False``.** A windowed subsystem binary, so double-clicking
  never flashes a console window.
* **Version resource.** Pulled from ``build/version_info.py`` so the file
  properties dialog and the About page cannot disagree.
* **customtkinter data.** The package ships theme JSON, fonts and icons as
  data files. ``pyinstaller-hooks-contrib`` has a hook for it, but the
  collection is spelled out anyway so the build does not silently lose the
  theme assets when the hooks package is missing or downgraded.
"""

import os
import sys

sys.path.insert(0, SPECPATH)

import version_info  # noqa: E402  (local build helper in this directory)

from PyInstaller.utils.hooks import (  # noqa: E402
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

ROOT = os.path.dirname(SPECPATH)
ENTRY = os.path.join(SPECPATH, "entry_gui.py")

# Resources bundled into the executable.
datas = [
    # gui/resources.py resolves the icon as <bundle root>/icon.ico.
    (os.path.join(SPECPATH, "icon.ico"), "."),
]
datas += collect_data_files("customtkinter")
try:
    datas += copy_metadata("customtkinter")  # dist-info, for version checks
except Exception:  # pragma: no cover - metadata may be absent in odd envs
    pass

hiddenimports = collect_submodules("customtkinter") + [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.font",
    "tkinter.messagebox",
    "tkinter.constants",
    "PIL._tkinter_finder",
    "packaging.version",
    "packaging.specifiers",
    "packaging.requirements",
    "darkdetect",
]

# Nothing here needs a scientific stack, and pulling one in would multiply
# the download size for no benefit.
excludes = [
    "pytest", "_pytest", "unittest", "doctest", "pydoc",
    "numpy", "scipy", "pandas", "matplotlib", "PIL.ImageQt",
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
    name="BoseCtl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX trips some AV heuristics; not worth it
    runtime_tmpdir=None,
    console=False,             # windowed: no console flash on launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, "icon.ico"),
    version=version_info._vs_version_info("BoseCtl.exe", "BoseCtl"),
)
