"""Device view — name, connection behaviour, voice prompts, button remap.

Everything here maps onto a public ``BmapConnection`` method, so no part of
the GUI reaches past the library API. Where bosectl itself has no write
path (the voice-prompt language is read-only in the BMAP API — upstream's
CLI only exposes ``prompts on|off``), the value is shown read-only with a
note rather than offering a control that cannot work.
"""

from __future__ import annotations

import customtkinter as ctk

from pybmap.constants import ACTION_MODES, BUTTON_EVENTS, BUTTON_IDS

from ..theme import RADIUS, SPACE, get_theme
from ..widgets import (Body, Card, Chip, Divider, DropdownRow, EntryRow,
                       KeyValueRow, Muted, PageHeader, PrimaryButton,
                       SecondaryButton, SectionTitle, ToggleRow)
from .base import View

MAX_NAME_BYTES = 32

#: Actions worth surfacing first; the rest stay available in the dropdown.
_COMMON_ACTIONS = ("ANC", "VPA", "PlayPause", "ConversationMode",
                   "SpatialAudioMode", "ModesCarousel", "Disabled")


class DeviceView(View):
    title = "设备"
    icon = "◎"
    requires_device = True

    def build(self):
        page = self.scroll_page()
        PageHeader(page, "设备设置",
                   "名称、连接行为、语音提示与可编程按键。").pack(
            fill="x", padx=SPACE["xl"], pady=(SPACE["xl"], SPACE["lg"]))

        self._build_identity(page)
        self._build_connection(page)
        self._build_prompts(page)
        self._build_buttons(page)

    # ── identity ──

    def _build_identity(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "设备名称").pack(anchor="w")
        Muted(body, "这是耳机在蓝牙列表中显示的名称，最长 %d 字节 UTF-8。"
                    % MAX_NAME_BYTES).pack(anchor="w", pady=(2, SPACE["md"]))
        self.ctl_name = EntryRow(body, "名称", placeholder="例如：Bose QC Ultra",
                                 action_text="保存", command=self._save_name)
        self.ctl_name.pack(fill="x")

        info = ctk.CTkFrame(body, fg_color="transparent")
        info.pack(fill="x", pady=(SPACE["md"], 0))
        self.kv_firmware = KeyValueRow(info, "固件版本")
        self.kv_firmware.pack(fill="x", pady=2)
        self.kv_product = KeyValueRow(info, "产品型号")
        self.kv_product.pack(fill="x", pady=2)

    def _save_name(self):
        name = self.ctl_name.value()
        if not name:
            self.app.set_status("名称不能为空", tone="warning")
            return
        if len(name.encode("utf-8")) > MAX_NAME_BYTES:
            self.app.set_status("名称过长：UTF-8 编码后不能超过 %d 字节"
                                % MAX_NAME_BYTES, tone="warning")
            return
        self.app.call(self.dev.set_name, name, label="设置设备名称",
                      success="设备名称已更新为「%s」" % name,
                      on_ok=lambda r: self.app.read(self.dev.name,
                                                    on_ok=self.ctl_name.set))

    # ── connection behaviour ──

    def _build_connection(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "连接与佩戴").pack(anchor="w")
        Muted(body, "这些开关写在耳机固件里，对其他设备同样生效。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        self.ctl_multipoint = ToggleRow(
            body, "多点连接 (Multipoint)",
            "同时保持两台设备连接，例如电脑与手机，来电时自动切换。",
            command=self._on_multipoint)
        self.ctl_multipoint.pack(fill="x")

        self.ctl_autopause = ToggleRow(
            body, "摘下自动暂停", "取下耳机时自动暂停播放，戴上后继续。",
            command=self._on_autopause)
        self.ctl_autopause.pack(fill="x", pady=(SPACE["sm"], 0))

        self.ctl_autoanswer = ToggleRow(
            body, "自动接听来电", "来电无需操作即自动接听。",
            command=self._on_autoanswer)
        self.ctl_autoanswer.pack(fill="x", pady=(SPACE["sm"], 0))

        self.connection_card = card

    def _on_multipoint(self):
        on = self.ctl_multipoint.get()
        self.app.call(self.dev.set_multipoint, on, label="设置多点连接",
                      success="多点连接已%s" % ("开启" if on else "关闭"))

    def _on_autopause(self):
        on = self.ctl_autopause.get()
        self.app.call(self.dev.set_auto_pause, on, label="设置自动暂停",
                      success="摘下自动暂停已%s" % ("开启" if on else "关闭"))

    def _on_autoanswer(self):
        on = self.ctl_autoanswer.get()
        self.app.call(self.dev.set_auto_answer, on, label="设置自动接听",
                      success="自动接听已%s" % ("开启" if on else "关闭"))

    # ── voice prompts ──

    def _build_prompts(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "语音提示").pack(anchor="w")

        self.ctl_prompts = ToggleRow(
            body, "启用语音提示",
            "开机、切换模式、电量变化时的语音播报。",
            command=self._on_prompts)
        self.ctl_prompts.pack(fill="x", pady=(SPACE["sm"], 0))

        Divider(body).pack(fill="x", pady=SPACE["md"])
        Muted(body, "当前语言（只读）").pack(anchor="w")
        self.prompt_language = ctk.CTkLabel(
            body, text="—", font=get_theme().font("body", "bold"),
            text_color=get_theme()["text"], anchor="w")
        self.prompt_language.pack(anchor="w")
        Muted(body, "BMAP 只提供语音提示的开关与语言读取；"
                    "语言本身在手机端 Bose 应用中设置。").pack(
            anchor="w", pady=(2, 0))
        self.prompts_card = card

    def _on_prompts(self):
        on = self.ctl_prompts.get()
        self.app.call(self.dev.set_prompts, on, label="设置语音提示",
                      success="语音提示已%s" % ("开启" if on else "关闭"))

    # ── button remap ──

    def _build_buttons(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["xl"]))
        body = card.body
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        SectionTitle(head, "可编程按键").pack(side="left")
        SecondaryButton(head, "读取按键", self._read_buttons, height=30,
                        width=110).pack(side="right")
        Muted(body, "读取当前按键映射，然后选择要执行的动作并应用。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        self.button_summary = ctk.CTkLabel(
            body, text="尚未读取。", font=get_theme().font("small"),
            text_color=get_theme()["text_secondary"], anchor="w",
            justify="left", wraplength=620)
        self.button_summary.pack(anchor="w", pady=(0, SPACE["md"]))

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="btn")

        self.ctl_button = DropdownRow(
            grid, "按键", [BUTTON_IDS[k] for k in sorted(BUTTON_IDS)])
        self.ctl_button.grid(row=0, column=0, sticky="ew", padx=(0, SPACE["sm"]))
        self.ctl_button.set("Shortcut")

        self.ctl_event = DropdownRow(
            grid, "触发方式", [BUTTON_EVENTS[k] for k in sorted(BUTTON_EVENTS)])
        self.ctl_event.grid(row=0, column=1, sticky="ew", padx=(0, SPACE["sm"]))
        self.ctl_event.set("single_press")

        self.ctl_action = DropdownRow(grid, "执行动作", self._action_choices())
        self.ctl_action.grid(row=0, column=2, sticky="ew")
        self.ctl_action.set("ANC")

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(SPACE["md"], 0))
        PrimaryButton(row, "应用映射", self._apply_buttons, width=140).pack(side="left")
        self.button_note = Muted(row, "", "small")
        self.button_note.pack(side="left", padx=SPACE["md"])
        self.buttons_card = card

    @staticmethod
    def _action_choices():
        ordered = [name for name in _COMMON_ACTIONS]
        rest = [ACTION_MODES[k] for k in sorted(ACTION_MODES)
                if ACTION_MODES[k] not in ordered]
        return ordered + rest

    def _read_buttons(self):
        self.app.read(self.dev.buttons, on_ok=self._show_buttons,
                      label="读取按键映射")

    def _show_buttons(self, mapping):
        if mapping is None:
            self.button_summary.configure(text="该型号没有返回按键信息。")
            return
        supported = "、".join(mapping.supported_actions[:8]) or "设备未列出可选项"
        self.button_summary.configure(
            text="当前：%s · %s → %s\n设备支持的动作：%s"
                 % (mapping.button_name, mapping.event_name,
                    mapping.action_name, supported))
        self.ctl_button.set(mapping.button_name, notify=False)
        self.ctl_event.set(mapping.event_name, notify=False)
        self.ctl_action.set(mapping.action_name, notify=False)
        t = get_theme()

    def _apply_buttons(self):
        button = self.ctl_button.value()
        event = self.ctl_event.value()
        action = self.ctl_action.value()
        self.button_note.configure(text="正在写入…")
        self.app.call(self.dev.set_buttons, button, event, action,
                      label="设置按键映射",
                      success="按键映射已更新：%s · %s → %s"
                              % (button, event, action),
                      on_ok=lambda mapping: self.button_note.configure(
                          text="已应用。重新读取可确认设备返回值。"),
                      on_error=lambda e: self.button_note.configure(text=""))

    # ── lifecycle ──

    def on_device(self, dev):
        super().on_device(dev)
        if dev is None:
            return
        caps = self.caps
        self._show_card(self.connection_card,
                        caps.supports("multipoint") or caps.supports("auto_pause")
                        or caps.supports("auto_answer"))
        self._show_row(self.ctl_multipoint, caps.supports("multipoint"))
        self._show_row(self.ctl_autopause, caps.supports("auto_pause"))
        self._show_row(self.ctl_autoanswer, caps.supports("auto_answer"))
        self._show_card(self.prompts_card, caps.supports("prompts"))
        self._show_row(self.ctl_prompts, caps.supports("prompts"))
        self._show_card(self.buttons_card, caps.supports("buttons"))
        if caps.supports("buttons"):
            self._read_buttons()

    @staticmethod
    def _show_card(card, visible):
        try:
            if visible:
                if not card.winfo_ismapped():
                    card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
            else:
                card.pack_forget()
        except Exception:
            pass

    @staticmethod
    def _show_row(row, visible):
        try:
            if visible:
                if not row.winfo_ismapped():
                    row.pack(fill="x")
            else:
                row.pack_forget()
        except Exception:
            pass

    def refresh(self, status=None):
        if self.dev is None or status is None:
            return
        self.ctl_name.set(status.name or "")
        self.kv_firmware.set(status.firmware or "—")
        self.kv_product.set(self.caps.name or "—")
        if self.caps.supports("multipoint"):
            self.ctl_multipoint.set(status.multipoint)
        if self.caps.supports("auto_pause"):
            self.ctl_autopause.set(status.auto_pause)
        if self.caps.supports("auto_answer"):
            self.ctl_autoanswer.set(status.auto_answer)
        if self.caps.supports("prompts"):
            self.ctl_prompts.set(status.prompts_enabled)
            self.prompt_language.configure(text=status.prompts_language or "—")
