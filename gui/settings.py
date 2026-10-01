"""Persisted user preferences.

Settings live in ``%APPDATA%\\bosectl-win\\settings.json`` — the location
Windows users and backup tools expect for per-user application state. The
file is written atomically and every read is defensive: a corrupt or
partially-written file must never stop the app from starting, it just
falls back to defaults.
"""

from __future__ import annotations

import json
import os
import tempfile

__all__ = ["Settings", "settings_path", "config_dir"]

APP_DIR_NAME = "bosectl-win"

DEFAULTS = {
    "mac": "",
    "device_type": "",
    "appearance": "auto",       # auto | light | dark
    "timeout": 6.0,
    "auto_connect": False,
    "last_view": "audio",
    "geometry": "",
    "recent": [],               # [{"mac": ..., "name": ..., "type": ...}]
    "show_advanced": False,
}

MAX_RECENT = 6


def config_dir():
    """Return (and create) the per-user config directory."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        # A read-only profile is survivable: fall back to the temp dir so
        # the app still runs, it just will not remember anything.
        path = os.path.join(tempfile.gettempdir(), APP_DIR_NAME)
        os.makedirs(path, exist_ok=True)
    return path


def settings_path():
    return os.path.join(config_dir(), "settings.json")


class Settings:
    """A dict-like store backed by a JSON file, with typed accessors."""

    def __init__(self, path=None):
        self.path = path or settings_path()
        self._data = dict(DEFAULTS)
        self.load()

    # ── persistence ──

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    if key in DEFAULTS:
                        self._data[key] = value
        except (OSError, ValueError):
            # Missing, unreadable or corrupt: defaults are already in place.
            pass
        return self

    def save(self):
        """Write the file atomically so a crash cannot truncate it."""
        directory = os.path.dirname(self.path)
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False

    # ── typed access ──

    def get(self, key, default=None):
        if key in self._data:
            return self._data[key]
        return DEFAULTS.get(key, default)

    def set(self, key, value, autosave=True):
        self._data[key] = value
        if autosave:
            self.save()

    def update(self, mapping, autosave=True):
        self._data.update(mapping)
        if autosave:
            self.save()

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    # ── convenience ──

    def remember_device(self, mac, name, device_type):
        """Record a recently used device, most recent first, de-duplicated."""
        if not mac:
            return
        recent = [d for d in self.get("recent", [])
                  if isinstance(d, dict) and d.get("mac") != mac]
        recent.insert(0, {"mac": mac, "name": name or "", "type": device_type or ""})
        self.set("recent", recent[:MAX_RECENT])

    def resolve_appearance(self):
        """Turn the ``appearance`` preference into 'light' or 'dark'."""
        pref = self.get("appearance", "auto")
        if pref in ("light", "dark"):
            return pref
        from .theme import _current_mode
        return _current_mode()
