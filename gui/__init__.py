"""BoseCtl for Windows — desktop front end.

A CustomTkinter application that wraps :mod:`pybmap`. It exposes every
operation the ``bosectl`` CLI offers — modes, CNC/ANR, EQ, spatial audio,
profiles, device settings, button remapping, routing, raw packets — through
a Windows-native layout, plus a hardware-free demo mode.

Modules:
    ``app``        window shell, connection lifecycle, worker wiring
    ``theme``      design tokens and light/dark palettes
    ``widgets``    reusable components built from those tokens
    ``views``      one module per page in the navigation rail
    ``worker``     serialised background execution of device I/O
    ``settings``   per-user preferences in %APPDATA%\\bosectl-win
    ``resources``  DPI, taskbar identity and icon handling
"""

from __future__ import annotations

__all__ = ["main", "BoseCtlApp", "APP_TITLE"]


def __getattr__(name):
    """Import the app lazily so ``import gui`` stays cheap and headless-safe."""
    if name in ("main", "BoseCtlApp", "APP_TITLE"):
        from . import app as _app
        return getattr(_app, name)
    raise AttributeError(name)
