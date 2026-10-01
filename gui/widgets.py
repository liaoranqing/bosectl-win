"""Reusable UI components for the BoseCtl desktop app.

Small, declarative building blocks so the view modules stay readable and
every surface ends up with identical padding, radius and type treatment.
Each component pulls its colours from the active :class:`~gui.theme.Theme`,
so light and dark mode need no per-view branching.
"""

from __future__ import annotations

import customtkinter as ctk

from .theme import RADIUS, SPACE, get_theme

__all__ = [
    "Card", "PageHeader", "SectionTitle", "Muted", "Body", "Divider",
    "StatTile", "PrimaryButton", "SecondaryButton", "GhostButton",
    "ToggleRow", "SliderRow", "SegmentedRow", "DropdownRow", "EntryRow",
    "Banner", "BusyBar", "EmptyState", "KeyValueRow", "Chip",
]


class Card(ctk.CTkFrame):
    """A white surface with a hairline border and soft radius."""

    def __init__(self, master, padding=SPACE["lg"], **kwargs):
        t = get_theme()
        kwargs.setdefault("fg_color", t["surface"])
        kwargs.setdefault("corner_radius", RADIUS["md"])
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", t["border"])
        super().__init__(master, **kwargs)
        self._padding = padding
        self._inner = ctk.CTkFrame(self, fg_color="transparent")
        self._inner.pack(fill="both", expand=True, padx=padding, pady=padding)

    @property
    def body(self):
        """The padded container to add children to."""
        return self._inner


class PageHeader(ctk.CTkFrame):
    """Title + one-line description, standard at the top of every view."""

    def __init__(self, master, title, subtitle="", **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=title, font=t.font("title", "bold"),
                     text_color=t["text"], anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=t.font("body"),
                         text_color=t["text_secondary"], anchor="w",
                         justify="left").pack(anchor="w", pady=(2, 0))


class SectionTitle(ctk.CTkLabel):
    """A small all-caps-ish heading that separates blocks inside a card."""

    def __init__(self, master, text, **kwargs):
        t = get_theme()
        super().__init__(master, text=text, font=t.font("subheading", "bold"),
                         text_color=t["text"], anchor="w", **kwargs)


class Body(ctk.CTkLabel):
    def __init__(self, master, text, **kwargs):
        t = get_theme()
        kwargs.setdefault("justify", "left")
        kwargs.setdefault("anchor", "w")
        super().__init__(master, text=text, font=t.font("body"),
                         text_color=t["text"], **kwargs)


class Muted(ctk.CTkLabel):
    def __init__(self, master, text, size="small", **kwargs):
        t = get_theme()
        kwargs.setdefault("justify", "left")
        kwargs.setdefault("anchor", "w")
        super().__init__(master, text=text, font=t.font(size),
                         text_color=t["text_muted"], **kwargs)


class Divider(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        t = get_theme()
        super().__init__(master, height=1, fg_color=t["border"], **kwargs)


class Chip(ctk.CTkLabel):
    """A small pill used for tags such as the device model or preset badge."""

    def __init__(self, master, text, tone="neutral", **kwargs):
        t = get_theme()
        tones = {
            "neutral": (t["neutral_soft"], t["text_secondary"]),
            "accent": (t["accent_soft"], t["accent_text"]),
            "success": (t["success_soft"], t["success"]),
            "warning": (t["warning_soft"], t["warning"]),
            "danger": (t["danger_soft"], t["danger"]),
        }
        bg, fg = tones.get(tone, tones["neutral"])
        super().__init__(master, text=text, font=t.font("micro", "bold"),
                         fg_color=bg, text_color=fg,
                         corner_radius=RADIUS["pill"], padx=10, pady=3,
                         **kwargs)


class StatTile(ctk.CTkFrame):
    """A metric tile: caption, large value, optional sub-caption."""

    def __init__(self, master, caption, value="—", sub="", **kwargs):
        t = get_theme()
        super().__init__(master, fg_color=t["surface"], corner_radius=RADIUS["md"],
                         border_width=1, border_color=t["border"], **kwargs)
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACE["lg"], pady=SPACE["md"])
        self._caption = ctk.CTkLabel(inner, text=caption, font=t.font("small"),
                                     text_color=t["text_muted"], anchor="w")
        self._caption.pack(anchor="w")
        self._value = ctk.CTkLabel(inner, text=value, font=t.font("metric", "bold"),
                                   text_color=t["text"], anchor="w")
        self._value.pack(anchor="w", pady=(2, 0))
        self._sub = ctk.CTkLabel(inner, text=sub, font=t.font("micro"),
                                 text_color=t["text_muted"], anchor="w")
        if sub:
            self._sub.pack(anchor="w")
        else:
            self._sub.pack_forget()

    def update_value(self, value=None, sub=None, accent=None):
        t = get_theme()
        if value is not None:
            self._value.configure(text=value)
        if sub is not None:
            if sub:
                self._sub.configure(text=sub)
                if not self._sub.winfo_ismapped():
                    self._sub.pack(anchor="w")
            else:
                self._sub.pack_forget()
        self._value.configure(text_color=accent or t["text"])

    def value_text(self):
        """The value currently displayed.

        Exposed because the label is a private child: callers (and the GUI
        smoke test) should not have to reach into ``_value`` to read it.
        """
        return self._value.cget("text")


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, text, command=None, **kwargs):
        t = get_theme()
        kwargs.setdefault("fg_color", t["accent"])
        kwargs.setdefault("hover_color", t["accent_hover"])
        kwargs.setdefault("text_color", t["text_on_accent"])
        kwargs.setdefault("corner_radius", RADIUS["sm"])
        kwargs.setdefault("height", 34)
        kwargs.setdefault("font", t.font("body", "bold"))
        super().__init__(master, text=text, command=command, **kwargs)


class SecondaryButton(ctk.CTkButton):
    def __init__(self, master, text, command=None, **kwargs):
        t = get_theme()
        kwargs.setdefault("fg_color", t["surface_sunken"])
        kwargs.setdefault("hover_color", t["overlay"])
        kwargs.setdefault("text_color", t["text"])
        kwargs.setdefault("corner_radius", RADIUS["sm"])
        kwargs.setdefault("height", 34)
        kwargs.setdefault("font", t.font("body"))
        super().__init__(master, text=text, command=command, **kwargs)


class GhostButton(ctk.CTkButton):
    def __init__(self, master, text, command=None, **kwargs):
        t = get_theme()
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("hover_color", t["surface_sunken"])
        kwargs.setdefault("text_color", t["accent_text"])
        kwargs.setdefault("corner_radius", RADIUS["sm"])
        kwargs.setdefault("height", 32)
        kwargs.setdefault("font", t.font("body"))
        super().__init__(master, text=text, command=command, **kwargs)


class ToggleRow(ctk.CTkFrame):
    """A settings row: title, description, and a switch on the right."""

    def __init__(self, master, title, description="", command=None, **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        text_col = ctk.CTkFrame(self, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text_col, text=title, font=t.font("body", "bold"),
                     text_color=t["text"], anchor="w",
                     justify="left").pack(anchor="w")
        if description:
            ctk.CTkLabel(text_col, text=description, font=t.font("small"),
                         text_color=t["text_muted"], anchor="w", justify="left",
                         wraplength=460).pack(anchor="w")

        self._var = ctk.BooleanVar(value=False)
        self.switch = ctk.CTkSwitch(self, text="", variable=self._var,
                                    onvalue=True, offvalue=False,
                                    progress_color=t["accent"],
                                    button_color=t["surface"],
                                    command=command, width=44)
        self.switch.pack(side="right", padx=(SPACE["md"], 0))
        self._suppress = False

    def get(self):
        return bool(self._var.get())

    def set(self, value, notify=False):
        """Set state without firing the command unless ``notify`` is True."""
        self._suppress = not notify
        try:
            self._var.set(bool(value))
        finally:
            self._suppress = False

    def set_enabled(self, enabled):
        self.switch.configure(state="normal" if enabled else "disabled")


class SliderRow(ctk.CTkFrame):
    """A labelled slider with a live value readout and range captions."""

    def __init__(self, master, title, from_=0, to=10, steps=10, command=None,
                 formatter=None, **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        self._formatter = formatter or (lambda v: str(int(round(v))))

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=title, font=t.font("body", "bold"),
                     text_color=t["text"], anchor="w").pack(side="left")
        self._readout = ctk.CTkLabel(head, text=self._formatter(from_),
                                     font=t.font("body", "bold"),
                                     text_color=t["accent_text"], anchor="e")
        self._readout.pack(side="right")

        self.slider = ctk.CTkSlider(
            self, from_=from_, to=to, number_of_steps=steps,
            command=self._on_move, progress_color=t["accent"],
            button_color=t["accent"], button_hover_color=t["accent_hover"],
            fg_color=t["track"], height=18)
        self.slider.pack(fill="x", pady=(SPACE["sm"], 0))

        self._command = command
        self._suppress = False

    def _on_move(self, value):
        self._readout.configure(text=self._formatter(value))
        if self._suppress:
            return
        if self._command:
            self._command(value)

    def get(self):
        return self.slider.get()

    def set(self, value, notify=False):
        """Move the slider. The command only fires when ``notify`` is True.

        Programmatic updates during a status refresh must never echo back to
        the device — that would turn a read into a write loop.
        """
        self._suppress = not notify
        try:
            self.slider.set(value)
            self._readout.configure(text=self._formatter(value))
        finally:
            self._suppress = False
        if notify and self._command:
            self._command(value)

    def set_enabled(self, enabled):
        self.slider.configure(state="normal" if enabled else "disabled")


class SegmentedRow(ctk.CTkFrame):
    """A labelled segmented control (radio-style choices)."""

    def __init__(self, master, title, values, labels=None, command=None, **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=title, font=t.font("body", "bold"),
                     text_color=t["text"], anchor="w").pack(anchor="w")
        self._values = list(values)
        self._labels = list(labels) if labels else [str(v) for v in values]
        self.seg = ctk.CTkSegmentedButton(
            self, values=self._labels, command=self._on_change,
            selected_color=t["accent"], selected_hover_color=t["accent_hover"],
            unselected_color=t["surface_sunken"],
            unselected_hover_color=t["overlay"], text_color=t["text"],
            height=32, corner_radius=RADIUS["sm"], font=t.font("small"))
        self.seg.pack(fill="x", pady=(SPACE["sm"], 0))
        self._command = command
        self._suppress = False

    def _on_change(self, label):
        if self._suppress:
            return
        if self._command:
            self._command(label)

    def value(self):
        return self.seg.get()

    def set(self, label, notify=False):
        self._suppress = not notify
        try:
            self.seg.set(label)
        finally:
            self._suppress = False
        if notify and self._command:
            self._command(label)

    def set_enabled(self, enabled):
        self.seg.configure(state="normal" if enabled else "disabled")


class DropdownRow(ctk.CTkFrame):
    """A labelled option menu, optionally with a caption underneath."""

    def __init__(self, master, title, values, command=None, caption="", **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=title, font=t.font("body", "bold"),
                     text_color=t["text"], anchor="w").pack(anchor="w")
        self.menu = ctk.CTkOptionMenu(
            self, values=list(values), command=self._on_change,
            fg_color=t["surface_sunken"], button_color=t["border_strong"],
            button_hover_color=t["border"], text_color=t["text"],
            dropdown_fg_color=t["surface"], dropdown_text_color=t["text"],
            dropdown_hover_color=t["accent_soft"], height=32,
            corner_radius=RADIUS["sm"], font=t.font("small"), dynamic_resizing=False)
        self.menu.pack(fill="x", pady=(SPACE["sm"], 0))
        if caption:
            ctk.CTkLabel(self, text=caption, font=t.font("micro"),
                         text_color=t["text_muted"], anchor="w",
                         wraplength=460, justify="left").pack(anchor="w",
                                                              pady=(SPACE["xs"], 0))
        self._command = command
        self._suppress = False

    def _on_change(self, value):
        if self._suppress:
            return
        if self._command:
            self._command(value)

    def value(self):
        return self.menu.get()

    def set(self, value, notify=False):
        self._suppress = not notify
        try:
            self.menu.set(value)
        finally:
            self._suppress = False
        if notify and self._command:
            self._command(value)

    def set_enabled(self, enabled):
        self.menu.configure(state="normal" if enabled else "disabled")


class EntryRow(ctk.CTkFrame):
    """A labelled text entry with an optional action button."""

    def __init__(self, master, title, placeholder="", action_text="",
                 command=None, width=None, **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=title, font=t.font("body", "bold"),
                     text_color=t["text"], anchor="w").pack(anchor="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(SPACE["sm"], 0))
        self.var = ctk.StringVar()
        self.entry = ctk.CTkEntry(
            row, textvariable=self.var, placeholder_text=placeholder,
            height=34, corner_radius=RADIUS["sm"], fg_color=t["surface_sunken"],
            border_color=t["border_strong"], text_color=t["text"],
            placeholder_text_color=t["text_muted"], font=t.font("small"))
        self.entry.pack(side="left", fill="x", expand=True)
        if width:
            self.entry.configure(width=width)
        self.button = None
        if action_text:
            self.button = PrimaryButton(row, action_text, command,
                                        width=96, height=34)
            self.button.pack(side="left", padx=(SPACE["sm"], 0))

    def value(self):
        return self.var.get().strip()

    def set(self, value):
        self.var.set(value or "")

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)
        if self.button:
            self.button.configure(state=state)


class Banner(ctk.CTkFrame):
    """An inline, non-modal message strip (info / warning / danger / success).

    The strip reserves no space while empty: it remembers how it was packed
    and re-applies those options when it becomes visible again, so toggling
    the message does not shift the surrounding layout.
    """

    TONES = ("info", "warning", "danger", "success")

    def __init__(self, master, text="", tone="info", **kwargs):
        t = get_theme()
        super().__init__(master, corner_radius=RADIUS["sm"], **kwargs)
        self._label = ctk.CTkLabel(self, text=text, font=t.font("small"),
                                   anchor="w", justify="left", wraplength=620)
        self._label.pack(fill="x", padx=SPACE["md"], pady=SPACE["sm"])
        self._pack_kwargs = {}
        self._visible = False
        self._text = ""
        self._tone = tone
        self.set(text, tone)

    def pack(self, **kwargs):  # noqa: D102 - documented above
        self._pack_kwargs = dict(kwargs)
        super().pack(**kwargs)

    def set(self, text, tone="info"):
        t = get_theme()
        bg, fg = {
            "info": (t["accent_soft"], t["accent_text"]),
            "warning": (t["warning_soft"], t["warning"]),
            "danger": (t["danger_soft"], t["danger"]),
            "success": (t["success_soft"], t["success"]),
        }.get(tone, (t["accent_soft"], t["accent_text"]))
        self._text = text or ""
        self._tone = tone
        self._label.configure(text=self._text, text_color=fg)
        self.configure(fg_color=bg)
        self._sync()

    def _sync(self):
        wanted = bool(self._text.strip())
        if wanted and not self._visible:
            self._visible = True
            super().pack(**(self._pack_kwargs or {"fill": "x"}))
        elif not wanted and self._visible:
            self._visible = False
            super().pack_forget()

    def clear(self):
        self.set("")


class BusyBar(ctk.CTkProgressBar):
    """A thin indeterminate bar shown while a device operation is running."""

    def __init__(self, master, **kwargs):
        t = get_theme()
        # CTkProgressBar rejects "transparent", so the trough is painted as
        # the canvas colour to blend into the window behind it.
        super().__init__(master, height=3, corner_radius=0,
                         progress_color=t["accent"],
                         fg_color=t["canvas"], mode="indeterminate", **kwargs)
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            try:
                self.configure(mode="indeterminate")
                super().start()
            except Exception:
                pass

    def stop(self):
        if self._running:
            self._running = False
            try:
                super().stop()
            except Exception:
                pass


class KeyValueRow(ctk.CTkFrame):
    """A label/value pair used in the diagnostics and about views."""

    def __init__(self, master, key, value="—", mono=False, **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=key, font=t.font("small"),
                     text_color=t["text_muted"], anchor="w",
                     width=170).pack(side="left")
        self._value = ctk.CTkLabel(
            self, text=value,
            font=t.raw_font(11.5, "bold") if mono else t.font("small", "bold"),
            text_color=t["text"], anchor="w", justify="left", wraplength=420)
        self._value.pack(side="left", fill="x", expand=True)

    def set(self, value):
        self._value.configure(text=value)


class EmptyState(ctk.CTkFrame):
    """Centered placeholder for an empty list or an unavailable feature."""

    def __init__(self, master, title, detail="", **kwargs):
        t = get_theme()
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=title, font=t.font("subheading", "bold"),
                     text_color=t["text_secondary"], anchor="center",
                     justify="center").pack(pady=(SPACE["lg"], SPACE["xs"]))
        if detail:
            ctk.CTkLabel(self, text=detail, font=t.font("small"),
                         text_color=t["text_muted"], anchor="center",
                         justify="center", wraplength=420).pack(pady=(0, SPACE["lg"]))
