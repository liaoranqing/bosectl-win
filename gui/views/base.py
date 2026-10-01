"""Base class shared by every view in the main window."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import SPACE, get_theme


class Capabilities:
    """What the connected model can actually do.

    The device modules differ a lot: a QC35 only speaks ANR and has no EQ or
    modes, a QC Ultra 2 has the full AudioModes block, and the Ultra Open
    Earbuds have EQ but no noise control at all. Views ask this object
    instead of guessing, so a control that the firmware would reject is
    greyed out with an explanation rather than failing on click.
    """

    _FIELDS = (
        "cnc", "anr", "eq", "spatial", "audio_settings", "multipoint",
        "auto_pause", "auto_answer", "prompts", "sidetone", "buttons",
        "modes", "source", "routing", "pairing", "power",
    )

    #: View-level capability -> the feature key in the device module. A few
    #: names differ: prompts live in ``voice_prompts``, and the AudioModes
    #: block is registered as ``get_all_modes`` / ``mode_config``.
    _PROBES = {
        "prompts": ("voice_prompts",),
        "modes": ("get_all_modes", "mode_config"),
        "power": ("power",),
    }

    def __init__(self, dev=None):
        self.device_type = ""
        self.name = ""
        self.battery_components = {}
        self._has = {f: False for f in self._FIELDS}
        self.anc_toggle = False
        self.noise_control = None
        if dev is not None:
            self.inspect(dev)

    def inspect(self, dev):
        module = getattr(dev, "_device", None)
        self.name = getattr(module, "DEVICE_INFO", {}).get("name", "") or ""
        self.device_type = getattr(module, "__name__", "").rsplit(".", 1)[-1]
        self.battery_components = dict(getattr(dev, "battery_components", {}) or {})
        for field in self._FIELDS:
            keys = self._PROBES.get(field, (field,))
            found = False
            for key in keys:
                try:
                    if dev.has_feature(key):
                        found = True
                        break
                except Exception:
                    pass
            self._has[field] = found
        self.anc_toggle = (self._has["audio_settings"]
                           and getattr(module, "SUPPORTS_ANC_TOGGLE", True))
        # Noise control is either CNC (newer) or ANR (QC35 generation).
        self.noise_control = "cnc" if self._has["cnc"] else (
            "anr" if self._has["anr"] else None)
        # Spatial audio rides on AudioSettingsConfig where present, and
        # otherwise on the editable ModeConfig.
        self._has["spatial"] = self._has["spatial"] or (
            self._has["audio_settings"] or self._has["modes"])
        return self

    def __getattr__(self, item):
        has = self.__dict__.get("_has")
        if has and item in has:
            return has[item]
        raise AttributeError(item)

    def supports(self, field):
        return bool(self._has.get(field))

    def summary_lines(self):
        """Short human-readable capability summary for the About view."""
        yes = [f for f, v in self._has.items() if v]
        no = [f for f, v in self._has.items() if not v]
        return yes, no


class View(ctk.CTkFrame):
    """A page in the main window.

    Subclasses implement :meth:`build` and optionally :meth:`on_show`,
    :meth:`refresh` and :meth:`on_device`. The app calls those hooks; the
    view never drives the connection itself.
    """

    #: Nav label shown in the rail.
    title = "View"
    #: Nav icon glyph (a simple unicode symbol keeps the EXE asset-free).
    icon = "•"
    #: Views that need a live device are disabled until one is connected.
    requires_device = True
    #: Short description in the header.
    subtitle = ""

    def __init__(self, master, app):
        t = get_theme()
        super().__init__(master, fg_color=t["canvas"])
        self.app = app
        self.dev = None
        self._built = False
        self._enabled = False
        self.build()
        self._built = True

    # ── lifecycle hooks ──

    def build(self):
        """Create the widgets. Called once, during construction."""

    def on_show(self):
        """Called every time the view becomes visible."""

    def on_first_show(self):
        """Called once, the first time this view is displayed.

        Used for work that should not run until the user actually opens the
        page (an extra device read, scanning for devices, and so on).
        """

    def on_device(self, dev):
        """Called after connect/disconnect. ``dev`` may be None."""
        self.dev = dev
        self.set_enabled(dev is not None)

    def refresh(self, status=None):
        """Called after a status snapshot is read.

        Args:
            status: A :class:`pybmap.types.DeviceStatus`, or None when only
                the enabled state changed.
        """

    def set_enabled(self, enabled):
        """Enable or grey out the interactive parts of the view."""
        self._enabled = enabled
        self._apply_enabled(enabled)

    def _apply_enabled(self, enabled):
        for attr in self._enablable():
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            try:
                if hasattr(widget, "set_enabled"):
                    widget.set_enabled(enabled)
                else:
                    widget.configure(state="normal" if enabled else "disabled")
            except Exception:
                pass

    def _enablable(self):
        """Names of attributes to toggle. Override or collect automatically."""
        return [name for name in vars(self)
                if name.startswith("ctl_") or name.endswith("_row")]

    # ── helpers ──

    @property
    def caps(self):
        return self.app.caps

    def scroll_page(self):
        """A scrollable page container that fills the content area.

        Every view is scrollable: at 125%/150% Windows scaling the content
        is taller than the window, and a clipped settings page with no way
        to reach the bottom row is the most common tablet/DPI complaint.
        """
        t = get_theme()
        page = ctk.CTkScrollableFrame(self, fg_color=t["canvas"],
                                      scrollbar_button_color=t["border_strong"],
                                      scrollbar_button_hover_color=t["border"])
        page.pack(fill="both", expand=True)
        return page

    def grid_cards(self, parent, columns=2, gap=SPACE["md"]):
        """A responsive card grid; returns the container to pack cards into."""
        get_theme()
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.pack(fill="x", pady=(0, gap))
        for col in range(columns):
            holder.grid_columnconfigure(col, weight=1, uniform="card")
        return holder

    def not_supported(self, parent, message):
        """Grey-out note for a feature this model lacks."""
        t = get_theme()
        return ctk.CTkLabel(parent, text=message, font=t.font("small"),
                            text_color=t["text_muted"], anchor="w",
                            justify="left", wraplength=520)
