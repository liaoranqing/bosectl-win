"""About view — version, provenance, supported models, licence."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

import pybmap

from .. import resources
from ..theme import SPACE, get_theme
from ..widgets import (
    Card,
    Chip,
    Divider,
    KeyValueRow,
    Muted,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    SectionTitle,
)
from .base import View

UPSTREAM_URL = "https://github.com/aaronsb/bosectl"

CAPABILITY_LABELS = {
    "cnc": "连续降噪等级 (CNC)",
    "anr": "降噪模式 (ANR)",
    "eq": "三段均衡器",
    "spatial": "空间音频",
    "audio_settings": "音频设置直写 [31.10]",
    "multipoint": "多点连接",
    "auto_pause": "摘下自动暂停",
    "auto_answer": "自动接听",
    "prompts": "语音提示",
    "sidetone": "通话侧音",
    "buttons": "按键映射",
    "modes": "模式 / 配置文件",
    "source": "音频源查询",
    "routing": "音频路由切换",
    "pairing": "配对模式",
    "power": "关机指令",
}


class AboutView(View):
    title = "关于"
    icon = "ⓘ"
    requires_device = False

    def build(self):
        page = self.scroll_page()
        PageHeader(page, "关于 BoseCtl for Windows",
                   "本地控制 Bose 耳机的开源工具。不联网、不需要账号、"
                   "不上传任何数据。").pack(fill="x", padx=SPACE["xl"],
                                          pady=(SPACE["xl"], SPACE["lg"]))
        self._build_version(page)
        self._build_capabilities(page)
        self._build_devices(page)
        self._build_license(page)

    # ── version ──

    def _build_version(self, page):
        t = get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        title = ctk.CTkFrame(head, fg_color="transparent")
        title.pack(side="left")
        ctk.CTkLabel(title, text="BoseCtl", font=t.raw_font(22, "bold"),
                     text_color=t["text"], anchor="w").pack(anchor="w")
        Muted(title, "Windows 移植版").pack(anchor="w")
        Chip(head, "v%s" % pybmap.__version__, "accent").pack(side="right",
                                                              pady=SPACE["xs"])

        Divider(body).pack(fill="x", pady=SPACE["md"])

        rows = [
            ("移植版本", "pybmap %s（%s）" % (pybmap.__version__, pybmap.PORT_NAME)),
            ("上游项目", "aaronsb/bosectl（Python / Rust / C++）"),
            ("通信方式", "蓝牙 RFCOMM 直连，Winsock AF_BTH"),
            ("运行形态", "已打包 EXE" if resources.is_frozen() else "Python 源码运行"),
            ("配置文件", self.app.settings.path),
        ]
        for key, value in rows:
            KeyValueRow(body, key, value).pack(fill="x", pady=2)

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(SPACE["md"], 0))
        PrimaryButton(buttons, "打开上游仓库",
                      lambda: webbrowser.open(UPSTREAM_URL), width=150).pack(side="left")
        SecondaryButton(buttons, "打开配置目录",
                        lambda: self._open_config(), width=150).pack(
            side="left", padx=SPACE["sm"])
        SecondaryButton(buttons, "窗口自检 / 诊断",
                        lambda: self.app.select_view("advanced"),
                        width=150).pack(side="left")

    def _open_config(self):
        import os
        import subprocess
        import sys
        folder = os.path.dirname(self.app.settings.path)
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # noqa: S606 - documented shell open
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            self.app.set_status("无法打开目录：%s" % folder, tone="warning")

    # ── capabilities ──

    def _build_capabilities(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "当前设备能力").pack(anchor="w")
        self.caps_summary = Muted(body, "未连接设备。", wraplength=640)
        self.caps_summary.pack(anchor="w", pady=(2, SPACE["sm"]))
        self.caps_grid = ctk.CTkFrame(body, fg_color="transparent")
        self.caps_grid.pack(fill="x")
        self.caps_card = card

    def _render_capabilities(self):
        for child in self.caps_grid.winfo_children():
            child.destroy()
        if self.dev is None:
            self.caps_summary.configure(text="未连接设备。连接后这里会列出耳机"
                                            "实际支持的功能。")
            return
        caps = self.caps
        self.caps_summary.configure(
            text="已连接：%s。下面列出该型号实际可用的功能，"
                 "未列出的项目在界面上会被自动隐藏。" % (caps.name or "Bose 设备"))
        columns = 3
        for index, (field, label) in enumerate(CAPABILITY_LABELS.items()):
            supported = caps.supports(field)
            chip = Chip(self.caps_grid, ("✓ " if supported else "✕ ") + label,
                        "success" if supported else "neutral")
            chip.grid(row=index // columns, column=index % columns,
                      sticky="w", padx=(0, SPACE["sm"]), pady=3)
        for col in range(columns):
            self.caps_grid.grid_columnconfigure(col, weight=1, uniform="caps")

    # ── supported models ──

    def _build_devices(self, page):
        t = get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "支持的型号").pack(anchor="w")
        Muted(body, "来自上游设备目录，共 %d 个机型已收录，其中 %d 个已验证可控制。"
              % (len(pybmap.known_devices()), len(pybmap.supported_devices()))).pack(
            anchor="w", pady=(2, SPACE["md"]))

        for device in pybmap.supported_devices():
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=device.name, font=t.font("small", "bold"),
                         text_color=t["text"], anchor="w",
                         width=300).pack(side="left")
            Chip(row, "0x%04X" % device.product_id, "neutral").pack(side="left")
            Muted(row, device.codename, "micro").pack(side="left",
                                                      padx=SPACE["sm"])

        more = [d for d in pybmap.known_devices()
                if d.product_id not in {x.product_id for x in pybmap.supported_devices()}]
        if more:
            Muted(body, "另有 %d 个机型已登记但尚未实现协议支持。"
                  % len(more)).pack(anchor="w", pady=(SPACE["sm"], 0))

    # ── licence ──

    def _build_license(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["xl"]))
        body = card.body
        SectionTitle(body, "开源许可与致谢").pack(anchor="w")
        for text in (
            "本项目的 BMAP 协议实现、设备目录与连接层来自 aaronsb/bosectl，"
            "以 MIT 许可证发布。Windows 移植部分同样以 MIT 许可证发布。",
            "BMAP 的 SETGET 与 START 操作符在 Settings / AudioModes 功能块上"
            "无需鉴权，本工具只使用这些标准操作。不提取密钥、不破解加密。",
            "上游作者：Aaron Bockelie 及 bosectl 贡献者。",
        ):
            Muted(body, text, wraplength=640).pack(anchor="w", pady=(0, SPACE["sm"]))
        SecondaryButton(body, "查看 MIT 许可证全文",
                        lambda: self._show_license(), width=180).pack(anchor="w")

    def _show_license(self):
        import os
        path = resources.resource_path("LICENSE")
        if os.path.isfile(path):
            try:
                os.startfile(path)  # noqa: S606
                return
            except Exception:
                pass
        webbrowser.open("https://opensource.org/license/mit")

    # ── lifecycle ──

    def on_device(self, dev):
        super().on_device(dev)
        self._render_capabilities()

    def on_show(self):
        self._render_capabilities()
