"""Modes view — the four presets plus custom profile management.

Upstream's model: a device has a fixed set of preset modes plus a handful of
editable slots. bosectl can list, create, update, rename and delete those
slots; this view exposes all of it, and refuses preset names client-side so
the user gets an immediate explanation instead of a device error.
"""

from __future__ import annotations

import customtkinter as ctk

from pybmap.messages import friendly_error

from ..labels import (PRESET_HINTS, PRESET_LABELS, SPATIAL_LABELS,
                      SPATIAL_QUOTE_BY_ID, SPATIAL_VALUES)
from ..theme import RADIUS, SPACE, get_theme
from ..widgets import (Body, Card, Chip, DropdownRow, EmptyState, EntryRow,
                       Muted, PageHeader, PrimaryButton, SecondaryButton,
                       SectionTitle, SliderRow, ToggleRow)
from .base import View

#: (label, id) pairs for the profile editor's spatial dropdown, derived from
#: the single id -> label map so the two can never drift apart.
SPATIAL_CHOICES = [(label, value)
                   for value, label in sorted(SPATIAL_QUOTE_BY_ID.items())]


class ModesView(View):
    title = "模式"
    icon = "◐"
    requires_device = True

    def build(self):
        page = self.scroll_page()
        PageHeader(page, "模式与配置文件",
                   "四种预设随耳机出厂内置；自定义配置可保存你自己的降噪、"
                   "空间音频与抗风噪组合。").pack(fill="x", padx=SPACE["xl"],
                                              pady=(SPACE["xl"], SPACE["lg"]))

        self._build_presets(page)
        self._build_profiles(page)
        self._build_editor(page)

    # ── presets ──

    def _build_presets(self, page):
        t = get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "预设模式").pack(anchor="w")
        Muted(body, "点击即可切换。预设不可修改或删除。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        self.preset_grid = ctk.CTkFrame(body, fg_color="transparent")
        self.preset_grid.pack(fill="x")
        self.preset_buttons = {}
        self.preset_cards = {}

    def _render_presets(self):
        """Rebuild preset tiles for the connected model."""
        for child in self.preset_grid.winfo_children():
            child.destroy()
        self.preset_buttons = {}
        self.preset_cards = {}
        presets = getattr(self.dev, "preset_modes", {}) or {}
        if not presets:
            EmptyState(self.preset_grid, "该型号没有预设模式",
                       "耳机固件未暴露 AudioModes 预设，请使用下方自定义配置。").pack(
                fill="x")
            return

        t = get_theme()
        columns = 2
        for index, (name, meta) in enumerate(sorted(
                presets.items(), key=lambda kv: kv[1].get("idx", 0))):
            tile = ctk.CTkFrame(self.preset_grid, fg_color=t["surface_alt"],
                                corner_radius=RADIUS["md"], border_width=1,
                                border_color=t["border"])
            tile.grid(row=index // columns, column=index % columns,
                      sticky="nsew", padx=(0 if index % columns == 0 else SPACE["sm"], 0),
                      pady=(0, SPACE["sm"]))
            self.preset_grid.grid_columnconfigure(index % columns, weight=1,
                                                  uniform="preset")

            inner = ctk.CTkFrame(tile, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=SPACE["md"],
                       pady=SPACE["md"])
            title_row = ctk.CTkFrame(inner, fg_color="transparent")
            title_row.pack(fill="x")
            ctk.CTkLabel(title_row, text=PRESET_LABELS.get(name, name),
                         font=t.font("subheading", "bold"),
                         text_color=t["text"], anchor="w").pack(side="left")
            badge = Chip(title_row, "当前", "accent")
            Muted(inner, PRESET_HINTS.get(name, meta.get("description", "")),
                  "micro", wraplength=260).pack(anchor="w", pady=(2, SPACE["sm"]))
            PrimaryButton(inner, "切换到此模式",
                          lambda n=name: self._set_preset(n),
                          height=30).pack(fill="x")
            self.preset_buttons[name] = tile
            self.preset_cards[name] = badge

    def _set_preset(self, name):
        label = PRESET_LABELS.get(name, name)
        self.app.call(self.dev.set_mode, name, label="切换模式",
                      success="已切换到「%s」" % label)

    def _mark_active(self, mode_name, mode_idx):
        """Highlight whichever preset tile matches the current mode."""
        t = get_theme()
        current = (mode_name or "").lower()
        for name, tile in self.preset_buttons.items():
            active = (name == current)
            try:
                tile.configure(border_color=t["accent"] if active else t["border"],
                               border_width=2 if active else 1,
                               fg_color=t["accent_soft"] if active else t["surface_alt"])
            except Exception:
                pass
            badge = self.preset_cards.get(name)
            if badge is not None:
                try:
                    if active:
                        if not badge.winfo_ismapped():
                            badge.pack(side="left", padx=(SPACE["sm"], 0))
                    elif badge.winfo_ismapped():
                        badge.pack_forget()
                except Exception:
                    pass

    # ── profile list ──

    def _build_profiles(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        SectionTitle(head, "自定义配置").pack(side="left")
        SecondaryButton(head, "重新读取", self._reload_modes, height=30,
                        width=110).pack(side="right")
        Muted(body, "可编辑槽位里的配置可以随时切换、修改或删除。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        self.profile_list = ctk.CTkFrame(body, fg_color="transparent")
        self.profile_list.pack(fill="x")
        self.profile_card = card

    def _reload_modes(self):
        self.app.read(self.dev.modes, on_ok=self._render_profiles,
                      label="读取配置文件")

    def _render_profiles(self, modes):
        for child in self.profile_list.winfo_children():
            child.destroy()
        if not modes:
            EmptyState(self.profile_list, "没有可用的配置信息").pack(fill="x")
            return

        t = get_theme()
        editable = sorted([cfg for cfg in modes.values() if cfg.editable],
                          key=lambda c: c.mode_idx)
        used = [cfg for cfg in editable if cfg.configured and cfg.name
                and cfg.name.lower() != "none"]

        if not used:
            EmptyState(self.profile_list, "还没有自定义配置",
                       "用下面的「新建配置文件」创建第一个，"
                       "例如“通勤”“办公”“飞行”。").pack(fill="x")
            return

        for cfg in used:
            self._profile_row(cfg)

    def _profile_row(self, cfg):
        t = get_theme()
        row = ctk.CTkFrame(self.profile_list, fg_color=t["surface_alt"],
                           corner_radius=RADIUS["sm"], border_width=1,
                           border_color=t["border"])
        row.pack(fill="x", pady=3)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=SPACE["md"],
                  pady=SPACE["sm"])
        title = ctk.CTkFrame(info, fg_color="transparent")
        title.pack(anchor="w")
        ctk.CTkLabel(title, text=cfg.name, font=t.font("body", "bold"),
                     text_color=t["text"], anchor="w").pack(side="left")
        Chip(title, "槽位 %d" % cfg.mode_idx, "neutral").pack(
            side="left", padx=(SPACE["sm"], 0))
        Muted(info, self._describe(cfg), "micro").pack(anchor="w")

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=SPACE["md"])
        PrimaryButton(actions, "切换", lambda: self._switch(cfg.name),
                      width=64, height=30).pack(side="left", padx=2)
        SecondaryButton(actions, "编辑", lambda: self._load_into_editor(cfg),
                        width=64, height=30).pack(side="left", padx=2)
        SecondaryButton(actions, "删除", lambda: self._delete(cfg.name),
                        width=64, height=30).pack(side="left", padx=2)

    @staticmethod
    def _describe(cfg):
        parts = []
        if cfg.cnc_level is not None and cfg.cnc_level:
            parts.append("降噪 %d" % cfg.cnc_level)
        spatial = {0: "空间音频关", 1: "空间音频·房间", 2: "空间音频·头部"}.get(
            cfg.spatial, "")
        if spatial and cfg.spatial:
            parts.append(spatial)
        if cfg.wind_block:
            parts.append("抗风噪")
        if cfg.anc_toggle is False:
            parts.append("ANC 关")
        return " · ".join(parts) or "未设置参数"

    def _switch(self, name):
        self.app.call(self.dev.set_mode, name, label="切换配置",
                      success="已切换到配置「%s」" % name)

    def _delete(self, name):
        if not self.app.confirm("删除配置",
                                "确定要删除配置「%s」吗？该槽位将被清空。" % name):
            return
        self.app.call(self.dev.delete_profile, name, label="删除配置",
                      success="已删除配置「%s」" % name,
                      on_ok=lambda r: self._reload_modes())

    # ── editor ──

    def _build_editor(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["xl"]))
        body = card.body
        SectionTitle(body, "新建 / 更新配置文件").pack(anchor="w")
        Muted(body, "名称不可与预设重名（安静、感知、沉浸、影院）。"
                    "同名配置会被更新，新名称则会占用下一个空闲槽位。").pack(
            anchor="w", pady=(2, SPACE["md"]))

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="ed")
        grid.grid_columnconfigure(1, weight=1, uniform="ed")

        self.ctl_name = EntryRow(grid, "配置名称", placeholder="例如：通勤")
        self.ctl_name.grid(row=0, column=0, sticky="ew", padx=(0, SPACE["md"]))

        self.ctl_spatial = DropdownRow(grid, "空间音频",
                                       [label for label, _ in SPATIAL_CHOICES])
        self.ctl_spatial.grid(row=0, column=1, sticky="ew")
        self.ctl_spatial.set("关闭")

        self.ctl_cnc = SliderRow(grid, "降噪强度 (CNC)", from_=0, to=10, steps=10,
                                 formatter=self._fmt_cnc)
        self.ctl_cnc.grid(row=1, column=0, sticky="ew", padx=(0, SPACE["md"]),
                          pady=(SPACE["md"], 0))

        toggles = ctk.CTkFrame(grid, fg_color="transparent")
        toggles.grid(row=1, column=1, sticky="ew", pady=(SPACE["md"], 0))
        self.ctl_wind = ToggleRow(toggles, "抗风噪", "")
        self.ctl_wind.pack(fill="x")
        self.ctl_anc = ToggleRow(toggles, "主动降噪", "")
        self.ctl_anc.pack(fill="x", pady=(SPACE["xs"], 0))
        self.ctl_wind.set(True)
        self.ctl_anc.set(True)

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", pady=(SPACE["lg"], 0))
        PrimaryButton(actions, "保存配置", self._save_profile, width=140).pack(
            side="left")
        SecondaryButton(actions, "清空表单", self._clear_editor,
                        width=110).pack(side="left", padx=SPACE["sm"])
        self.editor_note = Muted(actions, "", "small")
        self.editor_note.pack(side="left", padx=SPACE["md"])

        self.editor_card = card

    @staticmethod
    def _fmt_cnc(value):
        return str(int(round(value)))

    def _capture(self):
        name = self.ctl_name.value()
        if not name:
            self.editor_note.configure(text="请先填写配置名称。")
            return None
        spatial = dict(SPATIAL_CHOICES).get(self.ctl_spatial.value(), 0)
        return {
            "name": name,
            "cnc_level": int(round(self.ctl_cnc.get())),
            "spatial": spatial,
            "wind_block": 1 if self.ctl_wind.get() else 0,
            "anc_toggle": 1 if self.ctl_anc.get() else 0,
        }

    def _save_profile(self):
        values = self._capture()
        if not values:
            return
        self.editor_note.configure(text="正在写入…")
        settings = {
            "cnc_level": values["cnc_level"],
            "spatial": values["spatial"],
            "wind_block": values["wind_block"],
            "anc_toggle": values["anc_toggle"],
        }

        def after_save(_result=None):
            self._clear_editor()
            self.app.notify("已保存", "配置「%s」已写入耳机。" % values["name"])
            self._reload_modes()

        def try_create(exc=None):
            """The update raised, which means the name is new: create it."""
            if exc is not None and "not found" not in str(exc).lower():
                self.editor_note.configure(text="")
                self.app.show_error(exc, title="保存配置失败")
                return
            self.app.call(self.dev.create_profile, values["name"],
                          label="创建配置",
                          success="已创建配置「%s」" % values["name"],
                          on_ok=after_save,
                          on_error=lambda e: self.editor_note.configure(
                              text="创建失败：%s" % friendly_error(e)),
                          **settings)

        # Try update first; a missing name is the signal to create instead,
        # so that first attempt must stay silent.
        self.app.call(self.dev.update_profile, values["name"],
                      label="更新配置", report_error=False,
                      success="已更新配置「%s」" % values["name"],
                      on_ok=after_save, on_error=try_create, **settings)

    def _load_into_editor(self, cfg):
        self.ctl_name.set(cfg.name)
        self.ctl_cnc.set(cfg.cnc_level or 0)
        label = next((name for name, value in SPATIAL_CHOICES
                      if value == cfg.spatial), "关闭")
        self.ctl_spatial.set(label)
        self.ctl_wind.set(bool(cfg.wind_block))
        self.ctl_anc.set(cfg.anc_toggle is not False)
        self.editor_note.configure(text="已载入「%s」，保存即更新该配置。" % cfg.name)

    def _clear_editor(self):
        self.ctl_name.set("")
        self.ctl_cnc.set(0)
        self.ctl_spatial.set("关闭")
        self.ctl_wind.set(True)
        self.ctl_anc.set(True)
        self.editor_note.configure(text="")

    # ── lifecycle ──

    def on_device(self, dev):
        super().on_device(dev)
        if dev is None:
            return
        self._render_presets()
        caps = self.caps
        # The editor lives in a grid; grid_remove keeps its column geometry.
        try:
            self.ctl_cnc.grid() if caps.supports("cnc") else self.ctl_cnc.grid_remove()
            self.ctl_spatial.grid() if caps.supports("spatial") \
                else self.ctl_spatial.grid_remove()
            self.ctl_anc.pack() if caps.anc_toggle else self.ctl_anc.pack_forget()
        except Exception:
            pass
        if not caps.supports("modes"):
            self.editor_card.pack_forget()
            self.profile_card.pack_forget()
        self._reload_modes()

    def on_show(self):
        if self.dev is not None and not self.profile_list.winfo_children():
            self._reload_modes()

    def refresh(self, status=None):
        if self.dev is None or status is None:
            return
        self._mark_active(status.mode, status.mode_idx)
