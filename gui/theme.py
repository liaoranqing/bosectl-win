"""Design tokens for the BoseCtl desktop UI.

Everything visual is defined once here — colours, type scale, spacing,
radii — so the views stay declarative and the whole app can be re-skinned
by editing this file. Two complete palettes are provided; the app follows
the Windows light/dark setting by default and lets the user override it.

Colour choices follow the Windows 11 / WinUI 3 convention rather than
customtkinter's stock theme: a soft neutral canvas, white cards with a
hairline border, one saturated accent reserved for the primary action on
each surface, and semantic success/warning/danger hues for state.
"""

from __future__ import annotations

import tkinter.font as tkfont

import customtkinter as ctk

__all__ = ["Theme", "get_theme", "set_appearance", "preferred_font_family"]


# ── Palettes ─────────────────────────────────────────────────────────────────

LIGHT = {
    "name": "light",
    "canvas": "#F3F5F8",        # window background
    "surface": "#FFFFFF",       # cards
    "surface_alt": "#F8FAFC",   # inset panels (scroll areas, list rows)
    "surface_sunken": "#EEF2F7",
    "overlay": "#E9EFF7",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    "text": "#0F172A",
    "text_secondary": "#475569",
    "text_muted": "#94A3B8",
    "text_on_accent": "#FFFFFF",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_soft": "#E8F0FE",
    "accent_text": "#1D4ED8",
    "navy": "#0B1B3A",
    "navy_text": "#E8EEF9",
    "navy_muted": "#93A6C9",
    "success": "#12B76A",
    "success_soft": "#E7F7EF",
    "warning": "#F79009",
    "warning_soft": "#FEF3E2",
    "danger": "#E5484D",
    "danger_soft": "#FDECEC",
    "neutral_soft": "#EEF1F5",
    "track": "#DDE3EC",
    "shadow": "#0F172A",
}

DARK = {
    "name": "dark",
    "canvas": "#12161C",
    "surface": "#1A1F27",
    "surface_alt": "#20262F",
    "surface_sunken": "#161B22",
    "overlay": "#232A34",
    "border": "#2B333E",
    "border_strong": "#3A4451",
    "text": "#ECF0F5",
    "text_secondary": "#AEB9C7",
    "text_muted": "#7A8798",
    "text_on_accent": "#FFFFFF",
    "accent": "#4C8DFF",
    "accent_hover": "#6BA1FF",
    "accent_soft": "#1C2A44",
    "accent_text": "#8FB8FF",
    "navy": "#0D1524",
    "navy_text": "#E8EEF9",
    "navy_muted": "#8195B6",
    "success": "#3DD68C",
    "success_soft": "#16291F",
    "warning": "#F7B955",
    "warning_soft": "#2A2113",
    "danger": "#F87171",
    "danger_soft": "#2C1A1C",
    "neutral_soft": "#242B35",
    "track": "#333C48",
    "shadow": "#000000",
}


# ── Type scale (points) ──────────────────────────────────────────────────────

TYPE = {
    "display": 30,
    "title": 20,
    "heading": 15,
    "subheading": 13,
    "body": 12.5,
    "small": 11.5,
    "micro": 10.5,
    "metric": 26,
}

# ── Spacing scale (pixels) ───────────────────────────────────────────────────

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32}

RADIUS = {"sm": 6, "md": 10, "lg": 14, "pill": 999}


def preferred_font_family():
    """Pick the best available UI font for Chinese + Latin text.

    Microsoft YaHei UI ships with every Chinese Windows and renders both
    scripts cleanly; Segoe UI is the fallback for Latin-only installs.
    """
    try:
        available = set(tkfont.families())
    except Exception:
        return "Segoe UI"
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI Variable Text",
                   "Segoe UI", "Tahoma"):
        if family in available:
            return family
    return "Segoe UI"


class Theme:
    """Resolved colour + font set for one appearance mode.

    Views never hardcode a colour: they ask the theme, which keeps light
    and dark in lockstep and makes re-skinning a one-file change.
    """

    def __init__(self, mode="light"):
        self.mode = "dark" if mode == "dark" else "light"
        self.c = DARK if self.mode == "dark" else LIGHT
        self.family = preferred_font_family()
        self._fonts = {}
        self._configure_customtkinter()

    # ── customtkinter integration ──

    def _configure_customtkinter(self):
        ctk.set_appearance_mode(self.mode)
        ctk.set_default_color_theme("blue")

    @property
    def appearance(self):
        return self.mode

    # ── colour access ──

    def __getitem__(self, key):
        return self.c[key]

    def get(self, key, default=None):
        return self.c.get(key, default)

    # ── fonts ──

    def font(self, role="body", weight="normal"):
        """Return a cached :class:`CTkFont` for a type-scale role."""
        size = TYPE.get(role, TYPE["body"])
        key = (role, weight)
        if key not in self._fonts:
            self._fonts[key] = ctk.CTkFont(family=self.family, size=int(round(size)),
                                           weight=weight)
        return self._fonts[key]

    def raw_font(self, size, weight="normal"):
        """A font at an arbitrary size, bypassing the scale."""
        key = ("_raw", size, weight)
        if key not in self._fonts:
            self._fonts[key] = ctk.CTkFont(family=self.family, size=int(round(size)),
                                           weight=weight)
        return self._fonts[key]

    def family_font(self, size, weight="normal"):
        """A plain Tk font tuple (for ttk/Text widgets)."""
        return (self.family, int(round(size)), weight)


_theme = None


def get_theme(mode=None):
    """Return the process-wide theme, creating it on first use."""
    global _theme
    if _theme is None or (mode is not None and mode != _theme.mode):
        _theme = Theme(mode or _current_mode())
    return _theme


def set_appearance(mode):
    """Switch appearance mode and rebuild the theme."""
    global _theme
    _theme = Theme(mode)
    return _theme


def _current_mode():
    """Read the Windows app theme setting (light unless it says dark)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value else "dark"
    except Exception:
        return "light"
