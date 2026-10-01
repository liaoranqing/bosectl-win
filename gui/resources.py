"""Windows shell integration: DPI, taskbar identity, window icon.

These are the small platform details that separate an app that "runs" from
one that feels native:

* **DPI awareness.** Without an explicit call, Windows bitmap-scales the
  window on a 125%/150% display and every glyph is blurry. It must be set
  before Tk creates its first window — hence the call at import time.
* **AppUserModelID.** A packaged EXE otherwise gets grouped under
  ``python.exe`` on the taskbar, so the window keeps a generic Python icon
  and pinning does not work. Setting an explicit ID fixes both.
* **Icon.** Loaded from the bundle when frozen, from the source tree in
  development.
"""

from __future__ import annotations

import os
import sys

__all__ = [
    "enable_dpi_awareness", "set_app_user_model_id", "resource_path",
    "app_icon_path", "apply_window_icon", "is_frozen", "APP_ID",
]

APP_ID = "BoseCtl.Windows.1"
ICON_NAME = "icon.ico"


def is_frozen():
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def enable_dpi_awareness():
    """Opt into per-monitor DPI awareness. Safe to call on any platform.

    customtkinter runs its own DPI setup when the first window is created,
    and it also reads the scaling back to size widgets. Letting it own the
    call avoids two components disagreeing about the process DPI mode, so
    the raw Win32 path is only a fallback for when it is unavailable.
    """
    if sys.platform != "win32":
        return
    try:
        import customtkinter as ctk
        ctk.ScalingTracker.activate_high_dpi_awareness()
        return
    except Exception:
        pass
    import ctypes
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2; available since Windows 8.1.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def set_app_user_model_id(app_id=APP_ID):
    """Give the process a stable taskbar identity."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(app_id))
    except Exception:
        pass


def resource_path(*parts):
    """Resolve a bundled resource in both source and frozen layouts."""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def app_icon_path():
    """Path to the .ico, or None when it is not bundled."""
    for candidate in (resource_path(ICON_NAME),
                      resource_path("build", ICON_NAME)):
        if os.path.isfile(candidate):
            return candidate
    return None


def apply_window_icon(window):
    """Set the title-bar and taskbar icon, ignoring failure."""
    path = app_icon_path()
    if not path:
        return False
    try:
        window.iconbitmap(path)
        return True
    except Exception:
        return False
