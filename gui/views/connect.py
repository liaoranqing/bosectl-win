"""Connect view — device picking, scanning and manual entry."""

from __future__ import annotations

import customtkinter as ctk

import pybmap
from pybmap.messages import friendly_error

from ..labels import DEVICE_LABELS, DEVICE_LABELS_BY_KEY
from ..theme import RADIUS, SPACE, get_theme
from ..widgets import (
    Banner,
    Card,
    Chip,
    DropdownRow,
    EmptyState,
    EntryRow,
    Muted,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    SectionTitle,
    ToggleRow,
)
from .base import View


class ConnectView(View):
    title = "连接"
    icon = "⌁"
    requires_device = False
    subtitle = "选择已配对的耳机，或用演示模式先体验全部功能"

    def build(self):
        get_theme()
        page = self.scroll_page()

        PageHeader(page, "连接设备",
                   "BoseCtl 通过蓝牙 RFCOMM 直接与耳机通信，全程本地完成，"
                   "不联网、不需要账号。").pack(fill="x", padx=SPACE["xl"],
                                                pady=(SPACE["xl"], SPACE["lg"]))

        self.banner = Banner(page, "", "info")
        self.banner.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))

        self._build_demo_card(page)
        self._build_scan_card(page)
        self._build_manual_card(page)
        self._build_help_card(page)

    # ── demo ──

    def _build_demo_card(self, page):
        get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        SectionTitle(left, "演示模式").pack(anchor="w")
        Muted(left, "没有耳机在手边？演示模式驱动内置的模拟设备，"
                    "所有功能都可以点、都可以改，只是不会发到真实硬件。",
              wraplength=520).pack(anchor="w", pady=(2, 0))
        PrimaryButton(head, "启动演示模式",
                      lambda: self.app.connect(mock=True),
                      width=150).pack(side="right")

    # ── paired devices ──

    def _build_scan_card(self, page):
        get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        SectionTitle(head, "已配对的蓝牙设备").pack(side="left")
        self.ctl_rescan = SecondaryButton(head, "重新扫描", self.scan, height=30,
                                          width=110)
        self.ctl_rescan.pack(side="right")

        self.scan_meta = Muted(body, "尚未扫描。", size="micro")
        self.scan_meta.pack(anchor="w", pady=(SPACE["xs"], SPACE["sm"]))

        self.device_list = ctk.CTkFrame(body, fg_color="transparent")
        self.device_list.pack(fill="x")

    def scan(self):
        """Enumerate paired devices on the worker thread."""
        self._set_banner("正在扫描蓝牙设备…", "info")
        for child in self.device_list.winfo_children():
            child.destroy()
        Muted(self.device_list, "正在扫描…").pack(anchor="w", pady=SPACE["sm"])

        self.app.worker.run(
            pybmap.discover, True,
            on_ok=self._render_devices,
            on_error=lambda e: self._set_banner(
                "扫描失败：%s" % friendly_error(e), "danger"),
            label="扫描蓝牙设备")

    def _render_devices(self, devices):
        for child in self.device_list.winfo_children():
            child.destroy()
        if not devices:
            EmptyState(
                self.device_list, "没有找到已配对的蓝牙设备",
                "请先在「设置 → 蓝牙和其他设备」中把耳机与电脑配对，"
                "然后回到这里点「重新扫描」。也可以直接在下方手动填写地址。"
            ).pack(fill="x")
            self._set_banner("未发现已配对设备。请先完成 Windows 蓝牙配对。", "warning")
            return

        self._set_banner("", "info")
        bose = [d for d in devices if d.get("bose")]
        others = [d for d in devices if not d.get("bose")]
        self.scan_meta.configure(
            text="共 %d 台设备，其中 %d 台识别为 Bose。" % (len(devices), len(bose)))

        if not bose and others:
            # The most common first-run situation, and the one that produces
            # a bewildering "cannot establish BMAP communication" later: the
            # headphones were never paired to this PC, so the only device on
            # offer is something else entirely.
            self._set_banner(
                "已配对的设备里没有 Bose 耳机。如果你的耳机还没和这台电脑配对，"
                "请先到「设置 → 蓝牙和其他设备 → 添加设备」完成配对，再点「重新扫描」。",
                "warning")

        for device in bose:
            self._device_row(device, highlight=True)
        if others:
            Muted(self.device_list, "其他蓝牙设备",
                  size="micro").pack(anchor="w", pady=(SPACE["md"], SPACE["xs"]))
            for device in others[:12]:
                self._device_row(device, highlight=False)

    def _device_row(self, device, highlight):
        t = get_theme()
        row = ctk.CTkFrame(self.device_list,
                           fg_color=t["accent_soft"] if highlight else t["surface_alt"],
                           corner_radius=RADIUS["sm"],
                           border_width=1,
                           border_color=t["border"])
        row.pack(fill="x", pady=3)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=SPACE["md"],
                  pady=SPACE["sm"])

        name_row = ctk.CTkFrame(info, fg_color="transparent")
        name_row.pack(anchor="w")
        ctk.CTkLabel(name_row, text=device.get("name") or "未命名设备",
                     font=t.font("body", "bold"), text_color=t["text"],
                     anchor="w").pack(side="left")
        if device.get("connected"):
            Chip(name_row, "已连接", "success").pack(side="left", padx=(SPACE["sm"], 0))
        elif device.get("paired"):
            Chip(name_row, "已配对", "neutral").pack(side="left", padx=(SPACE["sm"], 0))
        if not device.get("bose"):
            Chip(name_row, "未识别为 Bose", "warning").pack(
                side="left", padx=(SPACE["sm"], 0))

        detail = device.get("mac", "")
        if device.get("product_id"):
            detail += " · PID 0x%04X" % device["product_id"]
        suggested = device.get("suggested_type")
        if suggested:
            detail += " · 识别为 %s" % DEVICE_LABELS.get(suggested, suggested)
        Muted(info, detail, "micro").pack(anchor="w")

        # Say why the row is under "other devices" rather than leaving the
        # user to work it out from a failed connection. A device with no Bose
        # product ID is usually a phone, a BLE peripheral or a headset that
        # only ever paired in low-energy mode — none of which expose a BMAP
        # channel, so connecting is guaranteed to fail.
        if not device.get("bose"):
            Muted(info,
                  "没有读到 Bose 产品 ID：可能不是 Bose 耳机，或只是以低功耗"
                  "（BLE）方式配对，本身没有可控制的蓝牙通道。",
                  "micro", wraplength=520).pack(anchor="w")

        suggested = device.get("suggested_type")
        PrimaryButton(
            row, "连接",
            lambda: self._connect(device.get("mac", ""), suggested,
                                  recognized=bool(device.get("bose"))),
            width=76, height=30).pack(side="right", padx=SPACE["md"], pady=SPACE["sm"])

    # ── manual ──

    def _build_manual_card(self, page):
        get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "手动连接").pack(anchor="w")
        Muted(body, "扫描不到时，可以手动指定设备型号与蓝牙地址。",
              wraplength=520).pack(anchor="w", pady=(2, SPACE["md"]))

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="col")
        grid.grid_columnconfigure(1, weight=1, uniform="col")

        labels = [DEVICE_LABELS.get(k, k) for k in pybmap.DEVICES]
        self.ctl_device = DropdownRow(grid, "设备型号", labels,
                                      command=self._on_type_change)
        self.ctl_device.grid(row=0, column=0, sticky="ew", padx=(0, SPACE["md"]))

        self.ctl_mac = EntryRow(grid, "蓝牙地址", placeholder="AA:BB:CC:DD:EE:FF")
        self.ctl_mac.grid(row=0, column=1, sticky="ew")

        self.ctl_timeout = DropdownRow(
            grid, "连接超时",
            ["4 秒", "6 秒", "8 秒", "12 秒", "20 秒"],
            caption="耳机睡眠时首次连接可能较慢，可适当调大。")
        self.ctl_timeout.grid(row=1, column=0, sticky="ew", padx=(0, SPACE["md"]),
                              pady=(SPACE["md"], 0))

        options = ctk.CTkFrame(grid, fg_color="transparent")
        options.grid(row=1, column=1, sticky="ew", pady=(SPACE["md"], 0))
        self.ctl_auto = ToggleRow(options, "启动时自动连接",
                                  "下次打开程序时自动连到这台设备。")
        self.ctl_auto.pack(anchor="w")

        action_row = ctk.CTkFrame(body, fg_color="transparent")
        action_row.pack(fill="x", pady=(SPACE["lg"], 0))
        PrimaryButton(action_row, "连接此设备", self._connect_manual,
                      width=140).pack(side="left")
        Muted(action_row, "首次连接通常需要 1-3 秒。", "micro").pack(
            side="left", padx=SPACE["md"])

    def _on_type_change(self, label):
        self.settings_device_type = self._type_from_label(label)

    @staticmethod
    def _type_from_label(label):
        return DEVICE_LABELS_BY_KEY.get(
            label, label if label in pybmap.DEVICES else "qc_ultra2")

    def _connect_manual(self):
        mac = self.ctl_mac.value()
        if not mac:
            self._set_banner("请先填写蓝牙地址，正确格式类似 AA:BB:CC:DD:EE:FF。",
                             "warning")
            return
        device_type = self._type_from_label(self.ctl_device.value())
        self.settings_save(device_type)
        self._connect(mac, device_type)

    def settings_save(self, device_type):
        timeout = self._timeout_value()
        self.app.settings.update({
            "device_type": device_type,
            "mac": self.ctl_mac.value(),
            "timeout": timeout,
            "auto_connect": self.ctl_auto.get(),
        })

    def _timeout_value(self):
        try:
            return float(self.ctl_timeout.value().split()[0])
        except (ValueError, IndexError):
            return 6.0

    def _connect(self, mac, device_type, recognized=True):
        if not mac:
            self._set_banner("这台设备没有可用地址，请手动填写。", "warning")
            return
        if not recognized:
            # Try anyway — product-ID detection can fail on a perfectly good
            # headset — but say up front that this is likely the wrong device,
            # so the failure that follows is not a surprise.
            self._set_banner(
                "该设备没有被识别为 Bose 耳机，BMAP 通信大概率不可用；"
                "仍将尝试连接 %s…" % mac, "warning")
        else:
            self._set_banner("正在连接 %s…" % mac, "info")
        self.app.connect(mac=mac, device_type=device_type or "qc_ultra2")

    # ── help ──

    def _build_help_card(self, page):
        t = get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["xl"]))
        body = card.body
        SectionTitle(body, "配对与排错").pack(anchor="w")
        steps = [
            ("1. 配对耳机", "Windows「设置 → 蓝牙和其他设备 → 添加设备」中"
                            "选择你的 Bose 耳机，等待显示“已连接”。"),
            ("2. 关掉手机上的 Bose 应用", "耳机的 BMAP 通道同一时间只允许一个"
                                        "连接。手机端 Bose 应用或另一台电脑占用时，"
                                        "本程序会提示“设备正忙”。"),
            ("3. 选择正确型号", "不同型号的 RFCOMM 通道和寄存器布局不同。"
                              "扫描列表会自动识别；识别不到时请手动选择。"),
            ("4. 典型错误", "“设备正忙”→等 5 秒重试；“设备拒绝连接”→确认已配对且"
                            "耳机开机；“连接超时”→确认蓝牙已打开、距离足够近。"),
        ]
        for title, detail in steps:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=(SPACE["sm"], 0))
            ctk.CTkLabel(row, text=title, font=t.font("small", "bold"),
                         text_color=t["text"], anchor="w").pack(anchor="w")
            Muted(row, detail, wraplength=640).pack(anchor="w")
        SecondaryButton(body, "查看环境自检", lambda: self.app.select_view("advanced"),
                        width=150).pack(anchor="w", pady=(SPACE["md"], 0))

    # ── hooks ──

    def on_first_show(self):
        self._load_settings()
        self.scan()

    def on_show(self):
        if not self.device_list.winfo_children():
            self.scan()

    def on_device(self, dev):
        super().on_device(dev)
        if dev is None:
            self._load_settings()
            if not self.device_list.winfo_children():
                self.scan()

    def _load_settings(self):
        s = self.app.settings
        self.ctl_mac.set(s.get("mac") or "")
        device_type = s.get("device_type") or "qc_ultra2"
        self.ctl_device.set(DEVICE_LABELS.get(device_type, DEVICE_LABELS["qc_ultra2"]))
        seconds = float(s.get("timeout", 6.0) or 6.0)
        self.ctl_timeout.set("%d 秒" % int(round(seconds)))
        self.ctl_auto.set(bool(s.get("auto_connect")))

    def _set_banner(self, text, tone):
        try:
            self.banner.set(text, tone)
        except Exception:
            pass
