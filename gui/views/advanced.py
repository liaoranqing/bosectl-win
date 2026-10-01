"""Advanced view — routing, device actions, diagnostics, raw BMAP console.

These are bosectl's power-user operations (``source``, ``route``, ``pair``,
``off``, ``raw``, ``dump``) plus a Windows-specific environment self-check.
The self-check matters here more than on Linux: Windows hides Bluetooth
state behind several layers, and when a connection fails the user needs to
know whether the radio is on, whether the device is paired, and whether the
product ID could be read.
"""

from __future__ import annotations

import customtkinter as ctk

import pybmap
from pybmap.messages import friendly_error

from ..theme import RADIUS, SPACE, get_theme
from ..widgets import (
    Banner,
    Card,
    Divider,
    EntryRow,
    KeyValueRow,
    Muted,
    PageHeader,
    SecondaryButton,
    SectionTitle,
)
from .base import View


class AdvancedView(View):
    title = "高级"
    icon = "⚙"
    requires_device = True

    def build(self):
        page = self.scroll_page()
        PageHeader(page, "高级工具",
                   "音频路由、设备动作、环境自检和原始 BMAP 数据包。").pack(
            fill="x", padx=SPACE["xl"], pady=(SPACE["xl"], SPACE["lg"]))
        self._build_route(page)
        self._build_actions(page)
        self._build_diagnostics(page)
        self._build_console(page, )
        self._build_battery(page)

    # ── source & routing ──

    def _build_route(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "音频源与路由").pack(anchor="w")
        Muted(body, "查看耳机当前播放的来源，或把音频转交给另一台已配对的设备。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        self.kv_source = KeyValueRow(body, "当前音频源")
        self.kv_source.pack(fill="x", pady=2)

        self.ctl_route = EntryRow(body, "目标设备蓝牙地址",
                                  placeholder="AA:BB:CC:DD:EE:FF",
                                  action_text="切换", command=self._route)
        self.ctl_route.pack(fill="x", pady=(SPACE["md"], 0))
        self.route_card = card

    def _read_source(self):
        self.app.read(self.dev.source, on_ok=self._show_source,
                      label="读取音频源")

    def _show_source(self, source):
        if source is None:
            self.kv_source.set("—")
            return
        if source.source_mac:
            self.kv_source.set("%s（%s）" % (source.source_type, source.source_mac))
        else:
            self.kv_source.set(source.source_type or "—")

    def _route(self):
        mac = self.ctl_route.value()
        if not mac:
            self.app.set_status("请填写目标设备的蓝牙地址", tone="warning")
            return
        self.app.call(self.dev.route, mac, label="切换音频路由",
                      success="已请求把音频切换到 %s" % mac)

    # ── device actions ──

    def _build_actions(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "设备动作").pack(anchor="w")
        Muted(body, "进入配对模式可让耳机被新设备发现；关机等同于长按电源键。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.ctl_pair = SecondaryButton(row, "进入配对模式", self._pair, width=150)
        self.ctl_pair.pack(side="left")
        self.ctl_off = SecondaryButton(row, "关闭耳机", self._power_off, width=130)
        self.ctl_off.pack(side="left", padx=SPACE["sm"])
        self.ctl_dump = SecondaryButton(row, "导出全部模式状态", self._dump, width=160)
        self.ctl_dump.pack(side="left", padx=SPACE["sm"])
        self.actions_card = card

    def _pair(self):
        self.app.call(self.dev.pair, label="进入配对模式",
                      success="耳机已进入蓝牙配对模式")

    def _power_off(self):
        if not self.app.confirm("关闭耳机", "确定要关闭耳机电源吗？\n\n"
                                            "关闭后需要手动开机才能再次连接。"):
            return
        self.app.call(self.dev.power_off, label="关闭耳机",
                      success="已发送关机指令")

    def _dump(self):
        self.app.read(self.dev.modes, on_ok=self._render_dump,
                      label="导出模式状态")

    def _render_dump(self, modes):
        if not modes:
            self.console_write("（设备没有返回任何模式）")
            return
        lines = ["槽位  名称                 可编辑  已配置  降噪  空间  抗风噪"]
        for idx in sorted(modes):
            cfg = modes[idx]
            lines.append("%-5s %-20s %-7s %-7s %-5s %-5s %s" % (
                idx, cfg.name or "-", "是" if cfg.editable else "否",
                "是" if cfg.configured else "否",
                cfg.cnc_level if cfg.cnc_level is not None else "-",
                cfg.spatial, "是" if cfg.wind_block else "否"))
        self.console_write("\n".join(lines))

    # ── diagnostics ──

    def _build_diagnostics(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        SectionTitle(head, "Windows 蓝牙环境自检").pack(side="left")
        SecondaryButton(head, "运行自检", self.run_diagnostics, height=30,
                        width=110).pack(side="right")
        Muted(body, "确认蓝牙适配器、配对状态与产品 ID 是否可读。"
                    "连接失败时，先看这里。").pack(anchor="w", pady=(2, SPACE["md"]))

        self.diag_rows = ctk.CTkFrame(body, fg_color="transparent")
        self.diag_rows.pack(fill="x")
        self.diag_banner = Banner(body, "", "info")
        self.diag_banner.pack(fill="x", pady=(SPACE["sm"], 0))
        self.diag_banner.clear()

    def run_diagnostics(self):
        self.diag_banner.set("正在自检…", "info")
        self.app.worker.run(pybmap.diagnose, on_ok=self._render_diagnostics,
                            on_error=lambda e: self.diag_banner.set(
                                "自检失败：%s" % friendly_error(e), "danger"),
                            label="蓝牙自检")

    def _render_diagnostics(self, report):
        for child in self.diag_rows.winfo_children():
            child.destroy()
        winrt = "已安装" if report.get("winrt_available") else "未安装（不影响使用）"
        present = bool(report.get("radio_present"))
        connectable = bool(report.get("radio_connectable"))
        items = [
            ("操作系统", report.get("platform", "—")),
            ("蓝牙适配器", "已检测到" if present else "未检测到"),
            ("蓝牙开关", "已开启" if connectable else ("已关闭" if present else "—")),
            ("已配对设备数", str(report.get("paired_count", 0))),
            ("可枚举设备数", str(report.get("enumerated_count", 0))),
            ("识别为 Bose 的设备", str(report.get("bose_count", 0))),
            ("可读取产品 ID 的设备", str(report.get("product_ids_known", 0))),
            ("WinRT 投影", winrt),
        ]
        for key, value in items:
            KeyValueRow(self.diag_rows, key, value).pack(fill="x", pady=2)

        devices = report.get("devices", [])
        if devices:
            Divider(self.diag_rows).pack(fill="x", pady=SPACE["sm"])
            for device in devices[:10]:
                label = device.get("name") or "未命名"
                detail = device.get("mac", "")
                if device.get("product_id"):
                    detail += "  PID 0x%04X" % device["product_id"]
                if device.get("suggested_type"):
                    detail += "  → %s" % device["suggested_type"]
                KeyValueRow(self.diag_rows,
                            label + ("（Bose）" if device.get("bose") else ""),
                            detail).pack(fill="x", pady=1)

        if not present:
            self.diag_banner.set(
                "未检测到蓝牙适配器。请确认电脑有蓝牙（或在「设备管理器」中检查"
                "蓝牙驱动）。台式机通常需要外接蓝牙适配器。", "warning")
        elif not connectable:
            self.diag_banner.set(
                "蓝牙适配器存在，但蓝牙处于关闭状态。请在「设置 → 蓝牙和其他设备」"
                "中打开蓝牙开关。", "warning")
        elif report.get("paired_count", 0) == 0:
            self.diag_banner.set(
                "没有已配对的蓝牙设备。请先在 Windows「设置 → 蓝牙和其他设备」"
                "中完成耳机配对。", "warning")
        else:
            self.diag_banner.set(
                "自检完成：共检测到 %d 台已配对设备，其中 %d 台识别为 Bose。"
                % (report.get("paired_count", 0), report.get("bose_count", 0)),
                "success")

    # ── raw console ──

    def _build_console(self, page):
        t = get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "原始 BMAP 数据包").pack(anchor="w")
        Muted(body, "格式：[功能块, 功能, 操作符, 长度, ...负载] 十六进制。"
                    "例如 1f 01 05 00 表示读取全部模式。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        self.ctl_raw = EntryRow(body, "十六进制数据", placeholder="1f 01 05 00",
                                action_text="发送", command=self._send_raw)
        self.ctl_raw.pack(fill="x")

        self.console = ctk.CTkTextbox(
            body, height=170, corner_radius=RADIUS["sm"],
            fg_color=t["surface_sunken"], border_width=1,
            border_color=t["border"], text_color=t["text"],
            font=t.raw_font(11), wrap="none")
        self.console.pack(fill="x", pady=(SPACE["md"], 0))
        self.console.configure(state="disabled")

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(SPACE["sm"], 0))
        SecondaryButton(row, "清空输出", self._clear_console, width=110).pack(side="left")
        SecondaryButton(row, "复制输出", self._copy_console, width=110).pack(
            side="left", padx=SPACE["sm"])

    def _send_raw(self):
        hex_str = self.ctl_raw.value().replace(" ", "")
        if not hex_str:
            return
        try:
            int(hex_str, 16)
        except ValueError:
            self.console_write("！十六进制格式有误：%s" % hex_str)
            return
        self.console_write("> %s" % hex_str.upper())

        def done(responses):
            if not responses:
                self.console_write("< （没有响应，或数据包长度不足 4 字节）")
                return
            for resp in responses:
                self.console_write("< %s" % pybmap.fmt_response(resp))

        self.app.read(self.dev.send_raw, hex_str, on_ok=done, label="发送原始数据包")

    def console_write(self, text):
        try:
            self.console.configure(state="normal")
            self.console.insert("end", text + "\n")
            self.console.see("end")
            self.console.configure(state="disabled")
        except Exception:
            pass

    def _clear_console(self):
        try:
            self.console.configure(state="normal")
            self.console.delete("1.0", "end")
            self.console.configure(state="disabled")
        except Exception:
            pass

    def _copy_console(self):
        try:
            text = self.console.get("1.0", "end").strip()
            self.app.clipboard_clear()
            self.app.clipboard_append(text)
            self.app.set_status("已复制 %d 个字符到剪贴板" % len(text), tone="success")
        except Exception:
            pass

    # ── battery detail ──

    def _build_battery(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["xl"]))
        body = card.body
        SectionTitle(body, "电池明细").pack(anchor="w")
        Muted(body, "耳塞与充电盒会分别上报电量。").pack(anchor="w",
                                                     pady=(2, SPACE["md"]))
        self.battery_rows = ctk.CTkFrame(body, fg_color="transparent")
        self.battery_rows.pack(fill="x")
        self.kv_aggregate = KeyValueRow(self.battery_rows, "综合电量")
        self.kv_aggregate.pack(fill="x", pady=2)
        self._component_rows = {}
        self.battery_card = card

    # ── lifecycle ──

    def on_device(self, dev):
        super().on_device(dev)
        if dev is None:
            return
        caps = self.caps
        if not caps.supports("source") and not caps.supports("routing"):
            self.route_card.pack_forget()
        if not caps.supports("pairing"):
            self.ctl_pair.configure(state="disabled")
        if not caps.supports("power"):
            self.ctl_off.configure(state="disabled")
        if not caps.supports("modes"):
            self.ctl_dump.configure(state="disabled")
        if not caps.battery_components:
            self.battery_card.pack_forget()

    def on_first_show(self):
        self.run_diagnostics()

    def on_show(self):
        if self.dev is not None and self.caps.supports("source"):
            self._read_source()

    def refresh(self, status=None):
        if status is None:
            return
        if status.battery is None:
            self.kv_aggregate.set("—")
        else:
            self.kv_aggregate.set("%d%%" % status.battery)

        labels = self.caps.battery_components
        readings = {r.component_id: r.level for r in (status.battery_readings or [])}
        for component_id, label in labels.items():
            row = self._component_rows.get(component_id)
            if row is None:
                row = KeyValueRow(self.battery_rows, label)
                row.pack(fill="x", pady=2)
                self._component_rows[component_id] = row
            level = readings.get(component_id)
            row.set("—" if level is None else "%d%%" % level)
