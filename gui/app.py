"""BoseCtl for Windows — application shell.

Owns the window chrome (header, navigation rail, status bar), the single
device connection, and the background worker that serialises all BMAP I/O.
Views are dumb pages that the shell builds once and then drives through
lifecycle hooks, so connection handling lives in exactly one place.

The layout follows Windows 11 conventions: an in-window header instead of a
menu bar, a vertical navigation rail, a status bar along the bottom, and
light/dark theming taken from the Windows personalization setting.
"""

from __future__ import annotations

import sys
import tkinter.messagebox as mb

import customtkinter as ctk

import pybmap
from pybmap.errors import BmapError
from pybmap.messages import error_hint, friendly_error

from . import resources
from .settings import Settings
from .theme import RADIUS, SPACE, get_theme
from .views import VIEWS
from .views.base import Capabilities
from .widgets import BusyBar, SecondaryButton, StatTile
from .worker import DeviceWorker

APP_TITLE = "BoseCtl for Windows"


class BoseCtlApp(ctk.CTk):
    """The main window."""

    def __init__(self, settings=None):
        super().__init__()

        self.settings = settings or Settings()
        self.theme = get_theme(self.settings.resolve_appearance())
        self.dev = None
        self.caps = Capabilities()
        self._views = {}
        self._current = None
        self._shown_once = set()
        self._busy_label = ""
        self._busy_text = ""
        self._status_before_busy = ""

        self.title(APP_TITLE)
        self.configure(fg_color=self.theme["canvas"])
        self.minsize(980, 660)
        self._restore_geometry()
        resources.apply_window_icon(self)

        self.worker = DeviceWorker(self, on_busy=self._on_busy)

        self._build_header()
        self._build_status_strip()
        self._build_body()
        self._build_statusbar()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.select_view("connect")
        if self.settings.get("auto_connect"):
            self.after(400, self.try_auto_connect)

    # ── window plumbing ──────────────────────────────────────────────────────

    def _ui_scale(self):
        """Current DPI scaling factor, as customtkinter applies it."""
        try:
            return ctk.ScalingTracker.get_window_scaling(self) or 1.0
        except Exception:
            return 1.0

    def _restore_geometry(self):
        """Restore the saved size and position, clamped to this screen.

        Geometry is expressed in the same logical units customtkinter
        scales, so the physical screen size has to be divided by the scaling
        factor before it can be compared.
        """
        geometry = self.settings.get("geometry") or ""
        scale = self._ui_scale()
        screen_w = int(self.winfo_screenwidth() / scale)
        screen_h = int(self.winfo_screenheight() / scale)
        if geometry:
            try:
                size, _, pos = geometry.partition("+")
                width, _, height = size.partition("x")
                x, y = pos.split("+")[:2]
                width, height = int(width), int(height)
                x, y = int(x), int(y)
                if width >= 900 and height >= 600 and \
                        0 <= x < screen_w - 100 and 0 <= y < screen_h - 100:
                    self.geometry(geometry)
                    return
            except (ValueError, IndexError):
                pass
        width = min(1180, max(980, screen_w - 240))
        height = min(780, max(660, screen_h - 180))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    def _save_geometry(self):
        try:
            self.settings.set("geometry", self.geometry(), autosave=False)
            self.settings.save()
        except Exception:
            pass

    def _bind_shortcuts(self):
        """Keyboard shortcuts a Windows user will try unprompted."""
        self.bind("<Control-q>", lambda e: self._on_close())
        self.bind("<F5>", lambda e: self.refresh_status(manual=True))
        self.bind("<Control-r>", lambda e: self.refresh_status(manual=True))
        self.bind("<Control-Key-1>", lambda e: self.select_view("connect"))
        self.bind("<Control-Key-2>", lambda e: self.select_view("audio"))
        self.bind("<Control-Key-3>", lambda e: self.select_view("modes"))
        self.bind("<Control-Key-4>", lambda e: self.select_view("device"))
        self.bind("<Control-Key-5>", lambda e: self.select_view("advanced"))
        self.bind("<Control-Key-6>", lambda e: self.select_view("about"))

    # ── chrome ───────────────────────────────────────────────────────────────

    def _build_header(self):
        t = self.theme
        header = ctk.CTkFrame(self, fg_color=t["navy"], corner_radius=0, height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left", padx=(SPACE["xl"], 0), pady=SPACE["md"])
        ctk.CTkLabel(brand, text="BoseCtl", font=t.raw_font(17, "bold"),
                     text_color="#FFFFFF").pack(side="left")
        ctk.CTkLabel(brand, text="for Windows", font=t.font("micro"),
                     text_color=t["navy_muted"]).pack(side="left",
                                                      padx=(SPACE["sm"], 0),
                                                      pady=(5, 0))

        self._device_label = ctk.CTkLabel(
            header, text="未连接", font=t.font("small"),
            text_color=t["navy_muted"])
        self._device_label.pack(side="left", padx=SPACE["xl"])

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", fill="y", padx=(0, SPACE["lg"]))

        self._status_pill = ctk.CTkLabel(
            right, text="● 未连接", font=t.font("small", "bold"),
            text_color="#E5A0A0", fg_color="#1B2A4A",
            corner_radius=RADIUS["pill"], padx=12, pady=4)
        self._status_pill.pack(side="right", pady=SPACE["lg"])

        self._theme_button = ctk.CTkButton(
            right, text=self._theme_glyph(), width=38, height=32,
            fg_color="#1B2A4A", hover_color="#26375F",
            text_color="#E8EEF9", corner_radius=RADIUS["sm"],
            font=t.raw_font(14), command=self.toggle_appearance)
        self._theme_button.pack(side="right", padx=SPACE["sm"], pady=SPACE["lg"])

        self._refresh_button = ctk.CTkButton(
            right, text="↻ 刷新", width=92, height=32,
            fg_color="#1B2A4A", hover_color="#26375F",
            text_color="#E8EEF9", corner_radius=RADIUS["sm"],
            font=t.font("small"),
            command=lambda: self.refresh_status(manual=True))
        self._refresh_button.pack(side="right", padx=SPACE["sm"], pady=SPACE["lg"])
        self._refresh_button.configure(state="disabled")

        self.busy = BusyBar(self)
        self.busy.pack(fill="x", side="top")

    def _theme_glyph(self):
        return "☾" if self.theme.appearance == "light" else "☀"

    def _build_status_strip(self):
        """Persistent at-a-glance tiles, shown only while connected.

        Keeping battery and mode visible on every page saves a trip back to
        a dashboard view and matches how Windows apps surface device state.
        """
        t = self.theme
        self._strip = ctk.CTkFrame(self, fg_color=t["canvas"], corner_radius=0)
        holder = ctk.CTkFrame(self._strip, fg_color="transparent")
        holder.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["md"], 0))

        self.tile_battery = StatTile(holder, "电量", "—")
        self.tile_mode = StatTile(holder, "当前模式", "—")
        self.tile_noise = StatTile(holder, "降噪", "—")
        self.tile_spatial = StatTile(holder, "空间音频", "—")
        for tile in (self.tile_battery, self.tile_mode, self.tile_noise,
                     self.tile_spatial):
            tile.pack(side="left", fill="both", expand=True, padx=(0, SPACE["sm"]))
        self.tile_spatial.pack_configure(padx=0)
        self._strip_visible = False

    def _show_strip(self, visible):
        if visible and not self._strip_visible:
            self._strip_visible = True
            self._strip.pack(fill="x", after=self.busy)
        elif not visible and self._strip_visible:
            self._strip_visible = False
            self._strip.pack_forget()

    def _update_strip(self, status):
        """Refresh the tiles from a status snapshot.

        Battery and mode come straight from the snapshot. Noise and spatial
        are set by the audio view (via :meth:`set_tile`) because the ANR
        generation and the mode-config-only models expose them through
        different registers than the snapshot covers.
        """
        t = self.theme
        battery = status.battery
        if battery is None:
            self.tile_battery.update_value("—", sub="", accent=t["text"])
        else:
            tone = t["success"] if battery > 30 else (
                t["warning"] if battery > 10 else t["danger"])
            self.tile_battery.update_value("%d%%" % battery, sub="剩余电量",
                                           accent=tone)
        self.tile_mode.update_value(self._localize_mode(status.mode))
        if self.caps.supports("cnc") and status.cnc_max:
            self.tile_noise.update_value(
                "%d / %d" % (status.cnc_level, status.cnc_max),
                sub="0 = 最强降噪")

    def set_tile(self, key, value, sub=None, accent=None):
        """Override a status tile from a view that knows better."""
        tile = {"battery": self.tile_battery, "mode": self.tile_mode,
                "noise": self.tile_noise, "spatial": self.tile_spatial}.get(key)
        if tile is not None:
            tile.update_value(value, sub=sub, accent=accent)

    def _build_body(self):
        t = self.theme
        body = ctk.CTkFrame(self, fg_color=t["canvas"], corner_radius=0)
        body.pack(fill="both", expand=True)

        rail = ctk.CTkFrame(body, fg_color=t["surface"], corner_radius=0, width=200)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)

        self._nav_buttons = {}
        for key, view_cls in VIEWS:
            btn = ctk.CTkButton(
                rail, text="  %s   %s" % (view_cls.icon, view_cls.title),
                anchor="w", height=40, corner_radius=RADIUS["sm"],
                fg_color="transparent", hover_color=t["surface_sunken"],
                text_color=t["text_secondary"], font=t.font("body"),
                command=lambda k=key: self.select_view(k))
            btn.pack(fill="x", padx=SPACE["md"], pady=2)
            self._nav_buttons[key] = btn
            if view_cls.requires_device:
                btn.configure(state="disabled", text_color=t["text_muted"])

        footer = ctk.CTkFrame(rail, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=SPACE["md"], pady=SPACE["md"])
        self._disconnect_button = SecondaryButton(
            footer, "断开连接", self.disconnect, height=32)
        self._disconnect_button.pack(fill="x")
        self._disconnect_button.configure(state="disabled")

        self.content = ctk.CTkFrame(body, fg_color=t["canvas"], corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        for key, view_cls in VIEWS:
            view = view_cls(self.content, self)
            view.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._views[key] = view

    def _build_statusbar(self):
        t = self.theme
        bar = ctk.CTkFrame(self, fg_color=t["surface"], corner_radius=0, height=28,
                           border_width=1, border_color=t["border"])
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._status_text = ctk.CTkLabel(
            bar, text="就绪 · 连接 Bose 耳机以开始", font=t.font("micro"),
            text_color=t["text_muted"], anchor="w")
        self._status_text.pack(side="left", padx=SPACE["md"])
        self._status_right = ctk.CTkLabel(
            bar, text="pybmap %s · %s" % (pybmap.__version__, pybmap.PORT_NAME),
            font=t.font("micro"), text_color=t["text_muted"], anchor="e")
        self._status_right.pack(side="right", padx=SPACE["md"])

    # ── navigation ───────────────────────────────────────────────────────────

    def select_view(self, key):
        view = self._views.get(key)
        if view is None:
            return
        if view.requires_device and self.dev is None:
            self.set_status("请先连接设备", tone="warning")
            return
        self._current = key
        view.tkraise()
        t = self.theme
        for k, btn in self._nav_buttons.items():
            active = k == key
            btn.configure(
                fg_color=t["accent_soft"] if active else "transparent",
                text_color=t["accent_text"] if active else t["text_secondary"])
        self.settings.set("last_view", key, autosave=False)
        self.settings.save()
        if key not in self._shown_once:
            self._shown_once.add(key)
            try:
                view.on_first_show()
            except Exception:
                pass
        try:
            view.on_show()
        except Exception:
            pass

    def toggle_appearance(self):
        """Rebuild the whole window in the other appearance mode."""
        target = "dark" if self.theme.appearance == "light" else "light"
        self.settings.set("appearance", target)
        self._rebuild_ui(target)

    def _rebuild_ui(self, appearance):
        """Swap themes in place: rebuild every widget, keep the connection."""
        from .theme import set_appearance
        view_key = self._current
        geometry = self.geometry()
        self._save_geometry()
        self.theme = set_appearance(appearance)
        for child in list(self.winfo_children()):
            child.destroy()
        self._views = {}
        self._shown_once = set()
        self.configure(fg_color=self.theme["canvas"])
        self._build_header()
        self._build_status_strip()
        self._build_body()
        self._build_statusbar()
        self.geometry(geometry)
        for view in self._views.values():
            try:
                view.on_device(self.dev)
            except Exception:
                pass
        if self.dev is not None:
            for key, view_cls in VIEWS:
                if view_cls.requires_device:
                    self._nav_buttons[key].configure(
                        state="normal", text_color=self.theme["text_secondary"])
            self._disconnect_button.configure(state="normal")
            self._refresh_button.configure(state="normal")
            self._set_connection_pill("on", self.caps.name or "已连接")
        self.select_view(view_key if view_key in self._views else "connect")
        self.set_status("已切换到%s模式" % ("深色" if appearance == "dark" else "浅色"),
                        tone="success")

    # ── status helpers ───────────────────────────────────────────────────────

    def set_status(self, message, tone="info"):
        t = self.theme
        colors = {"info": t["text_muted"], "success": t["success"],
                  "warning": t["warning"], "danger": t["danger"]}
        try:
            self._status_text.configure(text=message,
                                        text_color=colors.get(tone, t["text_muted"]))
        except Exception:
            pass

    def _set_connection_pill(self, state, text):
        colors = {
            "off": ("#E5A0A0", "#1B2A4A"),
            "connecting": ("#F0D08A", "#1B2A4A"),
            "on": ("#8BE0A8", "#16351F"),
        }
        fg, bg = colors.get(state, colors["off"])
        try:
            self._status_pill.configure(text="● %s" % text, text_color=fg, fg_color=bg)
            self._device_label.configure(text=text if state == "on" else "未连接")
        except Exception:
            pass

    def _on_busy(self, busy, label=""):
        """Show or hide the progress bar and lock the refresh button.

        The status line is restored afterwards, but only when it still holds
        the transient "…" text this method put there. A message written by
        the operation itself always wins.
        """
        try:
            if busy:
                if not self._busy_label:
                    self._status_before_busy = self._status_text.cget("text")
                self._busy_label = label or self._busy_label
                self.busy.start()
                if label:
                    self._busy_text = "%s…" % label
                    self.set_status(self._busy_text)
            else:
                self.busy.stop()
                current = self._status_text.cget("text")
                if self._busy_text and current == self._busy_text:
                    self.set_status(self._status_before_busy or "就绪")
                self._busy_label = ""
                self._busy_text = ""
            self._refresh_button.configure(
                state="disabled" if (busy or self.dev is None) else "normal")
        except Exception:
            pass

    def show_error(self, exc, title="操作失败", parent=None):
        """Report a failure with a translated message and a typed hint."""
        message = friendly_error(exc)
        hint = error_hint(exc)
        if hint:
            message = "%s\n\n%s" % (message, hint)
        if not isinstance(exc, BmapError):
            message = "%s\n\n%s: %s" % (message, type(exc).__name__, exc)
        mb.showerror(title, message, parent=parent or self)
        self.set_status(_first_line(message), tone="danger")

    def notify(self, title, message):
        mb.showinfo(title, message, parent=self)

    def ask(self, title, prompt):
        return ctk.CTkInputDialog(text=prompt, title=title).get_input()

    def confirm(self, title, message):
        return mb.askyesno(title, message, parent=self)

    # ── device I/O helpers used by every view ────────────────────────────────

    def call(self, fn, *args, label="", success="", refresh=True, on_ok=None,
             on_error=None, quiet=False, report_error=True, **kwargs):
        """Run a device operation on the background worker.

        Args:
            fn: A bound method of the connected device.
            label: Progress text while the call runs.
            success: Status-bar text on success.
            refresh: Re-read the full status afterwards. Set False for
                writes whose effect is already known locally.
            on_ok / on_error: Extra callbacks.
            quiet: Suppress the success message.
            report_error: Show the error dialog when the call fails. Set
                False when ``on_error`` already handles the case (for
                example an update that falls back to a create).
        """
        if self.dev is None:
            if not quiet:
                mb.showwarning("未连接", "请先连接到 Bose 设备。", parent=self)
            return

        def handle_ok(result):
            if success and not quiet:
                self.set_status(success, tone="success")
            if on_ok:
                on_ok(result)
            if refresh:
                self.refresh_status()

        def handle_error(exc):
            if on_error:
                on_error(exc)
            if report_error:
                self.show_error(exc, title=label or "操作失败")

        self.worker.run(fn, *args, on_ok=handle_ok, on_error=handle_error,
                        label=label, **kwargs)

    def read(self, fn, *args, on_ok=None, label="", **kwargs):
        """Read a value without changing the status snapshot."""
        if self.dev is None:
            return
        self.worker.run(fn, *args, on_ok=on_ok, on_error=lambda e: None,
                        label=label, **kwargs)

    def refresh_status(self, manual=False):
        """Re-read the device status snapshot and push it to every view.

        Automatic refreshes carry no label so they animate the progress bar
        without touching the status line — otherwise the "已连接" or "已保存"
        message would be replaced by "读取设备状态…" a moment later.
        """
        if self.dev is None:
            return
        if manual:
            self.set_status("正在读取设备状态…")

        def handle(status):
            self._apply_status(status)
            if manual:
                self.set_status("设备状态已更新", tone="success")

        self.worker.run(self.dev.status, on_ok=handle,
                        on_error=lambda e: self.show_error(e, title="读取状态失败"),
                        label="读取设备状态" if manual else "")

    def _apply_status(self, status):
        try:
            self._device_label.configure(
                text="%s · %s" % (status.name or "设备", self.caps.name or ""),
                text_color="#C7D5EE")
        except Exception:
            pass
        try:
            self._update_strip(status)
        except Exception:
            pass
        for view in self._views.values():
            try:
                view.refresh(status)
            except Exception:
                pass

    def _localize_mode(self, name):
        from .labels import localize_mode
        return localize_mode(name)

    # ── connection lifecycle ─────────────────────────────────────────────────

    def connect(self, mac=None, device_type=None, mock=False):
        """Open a connection; on success switch to the last-used view."""
        if self.dev is not None:
            self.set_status("已连接，忽略重复连接请求", tone="warning")
            return
        self._set_connection_pill("connecting", "正在连接…")
        self.set_status("正在连接设备…")

        if mock:
            kwargs = {"mock": True}
        else:
            kwargs = {
                "mac": mac, "device_type": device_type,
                "timeout": float(self.settings.get("timeout", 6.0)),
            }

        def handle(dev):
            self.dev = dev
            self.caps = Capabilities(dev)
            for view in self._views.values():
                try:
                    view.on_device(dev)
                except Exception:
                    pass
            for key, view_cls in VIEWS:
                if view_cls.requires_device:
                    self._nav_buttons[key].configure(
                        state="normal", text_color=self.theme["text_secondary"])
            self._disconnect_button.configure(state="normal")
            self._set_connection_pill("on", self.caps.name or "已连接")
            self._show_strip(True)
            self.set_status("已连接：%s" % (self.caps.name or "Bose 设备"),
                            tone="success")
            if not mock:
                self.settings.update({"mac": mac or "",
                                      "device_type": device_type or ""})
                self.settings.remember_device(mac, self.caps.name, device_type)
            target = self.settings.get("last_view") or "audio"
            if target not in self._views or not self._views[target].requires_device:
                target = "audio"
            self.select_view(target)
            self.refresh_status()

        def fail(exc):
            self._set_connection_pill("off", "未连接")
            self.show_error(exc, title="连接失败")

        self.worker.run(lambda: pybmap.connect(**kwargs), on_ok=handle,
                        on_error=fail, label="连接设备")

    def try_auto_connect(self):
        """Reconnect to the remembered device on launch, when enabled."""
        mac = self.settings.get("mac") or ""
        device_type = self.settings.get("device_type") or ""
        if not mac or not device_type:
            detected_mac, detected_type = pybmap.find_bmap_device()
            mac = mac or detected_mac
            device_type = device_type or detected_type
        if not mac:
            self.set_status("未找到已配对的 Bose 设备", tone="warning")
            return
        self.set_status("正在自动连接到 %s…" % mac)
        self.connect(mac=mac, device_type=device_type or "qc_ultra2")

    def disconnect(self):
        """Close the link and return to the connect screen."""
        dev = self.dev
        self.dev = None
        self.caps = Capabilities()
        self._disconnect_button.configure(state="disabled")
        self._refresh_button.configure(state="disabled")
        self._set_connection_pill("off", "未连接")
        self._show_strip(False)
        for key, view_cls in VIEWS:
            if view_cls.requires_device:
                self._nav_buttons[key].configure(
                    state="disabled", text_color=self.theme["text_muted"])
        for view in self._views.values():
            try:
                view.on_device(None)
            except Exception:
                pass
        self.select_view("connect")
        self.set_status("已断开连接")
        if dev is not None:
            self.worker.run(dev.close, on_error=lambda e: None, label="断开连接")

    def _on_close(self):
        self._save_geometry()
        try:
            if self.dev is not None:
                self.dev.close()
        except Exception:
            pass
        try:
            self.worker.stop()
        except Exception:
            pass
        self.destroy()


def _first_line(text):
    return (text or "").splitlines()[0] if text else ""


def main(argv=None):
    """Entry point for the desktop app."""
    resources.enable_dpi_awareness()
    resources.set_app_user_model_id()

    argv = list(argv if argv is not None else sys.argv)
    demo = "--demo" in argv
    app = BoseCtlApp()
    if demo:
        app.after(300, lambda: app.connect(mock=True))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
