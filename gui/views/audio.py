"""Audio view — noise control, spatial audio, equalizer, sidetone.

Every control is feature-gated: the QC35 generation speaks ANR rather than
CNC, the QuietComfort Headphones expose neither ANC/wind toggles nor
sidetone, and the Ultra Open Earbuds have no noise control at all. Instead
of failing on click, unsupported blocks render an explanatory note.

Slider and dropdown writes are debounced, because a drag emits a value per
pixel and each one would otherwise be a separate RFCOMM round-trip.
"""

from __future__ import annotations

import customtkinter as ctk

from ..labels import (
    ANR_LABELS,
    ANR_LABELS_BY_VALUE,
    ANR_VALUES,
    SIDETONE_LABELS,
    SIDETONE_LABELS_BY_VALUE,
    SIDETONE_VALUES,
    SPATIAL_LABELS,
    SPATIAL_QUOTE_BY_ID,
    SPATIAL_VALUES,
)
from ..theme import SPACE, get_theme
from ..widgets import (
    Card,
    Divider,
    DropdownRow,
    Muted,
    PageHeader,
    SecondaryButton,
    SectionTitle,
    SegmentedRow,
    SliderRow,
    ToggleRow,
)
from .base import View

#: Milliseconds to coalesce slider drags before writing to the device.
DEBOUNCE_MS = 220

EQ_PRESETS = {
    "平直": (0, 0, 0),
    "低音增强": (6, 1, -1),
    "人声": (-2, 4, 2),
    "古典": (2, -1, 3),
    "轻音乐": (-1, 2, 4),
}
EQ_BANDS = ("低音", "中音", "高音")


class AudioView(View):
    title = "声音"
    icon = "♪"
    requires_device = True

    def build(self):
        page = self.scroll_page()
        PageHeader(page, "声音",
                   "降噪、空间音频与均衡器的调整会立即写入耳机。").pack(
            fill="x", padx=SPACE["xl"], pady=(SPACE["xl"], SPACE["lg"]))

        self._debounce_jobs = {}
        self._build_noise(page)
        self._build_spatial(page)
        self._build_eq(page)
        self._build_sidetone(page)

    # ── noise control ──

    def _build_noise(self, page):
        get_theme()
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "降噪").pack(anchor="w")

        self.noise_holder = ctk.CTkFrame(body, fg_color="transparent")
        self.noise_holder.pack(fill="x", pady=(SPACE["sm"], 0))

        # CNC (QuietComfort Ultra / 45 / Earbuds)
        self.ctl_cnc = SliderRow(
            self.noise_holder, "降噪强度 (CNC)", from_=0, to=10, steps=10,
            command=self._on_cnc, formatter=self._fmt_cnc)
        self.ctl_cnc.pack(fill="x", padx=0)
        self.cnc_note = Muted(
            self.noise_holder,
            "0 = 最强降噪 · 10 = 最大环境音透入。只有开启主动降噪且关闭"
            "抗风噪时，该滑杆的差别才听得出来。")
        self.cnc_note.pack(anchor="w", pady=(SPACE["xs"], 0))

        # ANR (QC35 generation)
        self.ctl_anr = SegmentedRow(self.noise_holder, "降噪模式 (ANR)",
                                    ANR_LABELS, command=self._on_anr)
        self.anr_note = Muted(
            self.noise_holder, "该型号使用 ANR 四档模式，而不是连续的 CNC 等级。")
        self.anr_note.pack(anchor="w", pady=(SPACE["xs"], 0))

        Divider(body).pack(fill="x", pady=SPACE["lg"])

        self.ctl_anc = ToggleRow(
            body, "主动降噪 (ANC)", "关闭后完全进入通透模式，降噪等级不再生效。",
            command=self._on_anc)
        self.ctl_anc.pack(fill="x")

        self.ctl_wind = ToggleRow(
            body, "抗风噪 (Wind Block)", "抑制风噪，但会掩盖降噪等级的变化。",
            command=self._on_wind)
        self.ctl_wind.pack(fill="x", pady=(SPACE["sm"], 0))

        self.noise_note = self.not_supported(body, "")
        self.noise_note.pack(anchor="w")

    def _fmt_cnc(self, value):
        level = int(round(value))
        if level == 0:
            return "0 · 最强"
        if level == 10:
            return "10 · 最弱"
        return str(level)

    def _on_cnc(self, value):
        level = int(round(value))
        self.app.set_tile("noise", "%d / 10" % level, sub="0 = 最强降噪")
        self._debounce("cnc", lambda: self.app.call(
            self.dev.set_cnc, level, label="设置降噪等级",
            success="降噪等级已设为 %d" % level, refresh=False,
            on_ok=lambda r: self.app.refresh_status()))

    def _on_anr(self, label):
        value = ANR_VALUES.get(label, "off")
        self.app.set_tile("noise", label, sub="ANR 模式")
        self.app.call(self.dev.set_anr, value, label="设置降噪模式",
                      success="降噪模式已设为「%s」" % label)

    def _on_anc(self):
        enabled = self.ctl_anc.get()
        self.app.call(self.dev.set_anc, enabled, label="切换主动降噪",
                      success="主动降噪已%s" % ("开启" if enabled else "关闭"))

    def _on_wind(self):
        enabled = self.ctl_wind.get()
        self.app.call(self.dev.set_wind, enabled, label="切换抗风噪",
                      success="抗风噪已%s" % ("开启" if enabled else "关闭"))

    # ── spatial audio ──

    def _build_spatial(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "空间音频").pack(anchor="w")
        self.ctl_spatial = SegmentedRow(body, "模式", SPATIAL_LABELS,
                                        command=self._on_spatial)
        self.ctl_spatial.pack(fill="x", pady=(SPACE["sm"], 0))
        Muted(body, "「房间」为固定声场，「头部追踪」随头部转动定位，"
                    "仅部分型号支持。").pack(anchor="w", pady=(SPACE["xs"], 0))
        self.spatial_card = card

    def _on_spatial(self, label):
        if label not in SPATIAL_VALUES:
            return
        value = SPATIAL_VALUES[label]
        self.app.set_tile("spatial", label)
        self.app.call(self.dev.set_spatial, value, label="设置空间音频",
                      success="空间音频已设为「%s」" % label)

    # ── equalizer ──

    def _build_eq(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body = card.body
        SectionTitle(body, "均衡器").pack(anchor="w")
        Muted(body, "每段 −10 到 +10 dB。写入按段逐条发送，拖动结束后生效。",
              wraplength=620).pack(anchor="w", pady=(2, SPACE["md"]))

        self.eq_holder = ctk.CTkFrame(body, fg_color="transparent")
        self.eq_holder.pack(fill="x")
        self.ctl_eq = {}
        for index, name in enumerate(EQ_BANDS):
            row = SliderRow(self.eq_holder, name, from_=-10, to=10, steps=20,
                            command=self._on_eq, formatter=self._fmt_eq)
            row.pack(fill="x", pady=(SPACE["xs"], SPACE["sm"]))
            self.ctl_eq[index] = row

        foot = ctk.CTkFrame(body, fg_color="transparent")
        foot.pack(fill="x", pady=(SPACE["sm"], 0))

        self.eq_presets = ctk.CTkSegmentedButton(
            foot, values=list(EQ_PRESETS),
            command=self._on_eq_preset,
            selected_color=get_theme()["accent"],
            selected_hover_color=get_theme()["accent_hover"],
            unselected_color=get_theme()["surface_sunken"],
            unselected_hover_color=get_theme()["overlay"],
            text_color=get_theme()["text"], height=32, font=get_theme().font("small"))
        self.eq_presets.pack(side="left")

        SecondaryButton(foot, "恢复平直", self._on_eq_flat,
                        width=110).pack(side="right")
        self.eq_card = card

    def _fmt_eq(self, value):
        level = int(round(value))
        return "%+d dB" % level

    def _on_eq(self, _value):
        """Debounced commit of all three bands (one write per band)."""
        self._debounce("eq", self._write_eq)

    def _on_eq_preset(self, name):
        values = EQ_PRESETS.get(name)
        if not values:
            return
        for index, value in enumerate(values):
            self.ctl_eq[index].set(value)
        self._write_eq(success="已应用均衡器预设「%s」" % name)

    def _on_eq_flat(self):
        for index in range(3):
            self.ctl_eq[index].set(0)
        self.eq_presets.set("平直")
        self._write_eq(success="均衡器已恢复平直")

    def _write_eq(self, success="均衡器已更新"):
        values = [int(round(row.get())) for index, row in
                  sorted(self.ctl_eq.items())]
        self.app.call(self.dev.set_eq, *values, label="设置均衡器",
                      success=success)

    # ── sidetone ──

    def _build_sidetone(self, page):
        card = Card(page)
        card.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["xl"]))
        body = card.body
        SectionTitle(body, "通话侧音 (Sidetone)").pack(anchor="w")
        Muted(body, "让自己在通话中听到自己的声音，避免不自觉提高音量。",
              wraplength=620).pack(anchor="w", pady=(2, SPACE["md"]))
        self.ctl_sidetone = DropdownRow(body, "侧音强度", SIDETONE_LABELS,
                                        command=self._on_sidetone)
        self.ctl_sidetone.pack(fill="x")
        self.sidetone_card = card

    def _on_sidetone(self, label):
        value = SIDETONE_VALUES.get(label, "off")
        self.app.call(self.dev.set_sidetone, value, label="设置侧音",
                      success="侧音已设为「%s」" % label)

    # ── capability gating ──

    def on_device(self, dev):
        super().on_device(dev)
        self.apply_capabilities()

    def apply_capabilities(self):
        """Show only the blocks this model actually supports.

        Each control travels with its own caption, so an unsupported block
        disappears entirely rather than leaving an orphaned explanation.
        """
        caps = self.caps
        self._pair(self.ctl_cnc, self.cnc_note, caps.supports("cnc"))
        self._pair(self.ctl_anr, self.anr_note, caps.supports("anr"))
        self._pair(self.ctl_anc, None, caps.anc_toggle)
        self._pair(self.ctl_wind, None, caps.anc_toggle)
        self._card(self.spatial_card, caps.supports("spatial"))
        self._card(self.eq_card, caps.supports("eq"))
        self._card(self.sidetone_card, caps.supports("sidetone"))

        if caps.noise_control is None:
            self.noise_note.configure(
                text="该型号（%s）不提供降噪控制。" % (caps.name or "当前设备"))
            self.noise_note.pack(anchor="w")
        else:
            self.noise_note.pack_forget()

    def _pair(self, widget, caption, supported):
        """Show or hide a control together with its caption."""
        self._pack_or_hide(widget, supported)
        if caption is not None:
            self._pack_or_hide(caption, supported)

    def _card(self, card, supported):
        self._pack_or_hide(card, supported)

    def _pack_or_hide(self, widget, supported):
        if widget is None:
            return
        try:
            if supported:
                if not widget.winfo_ismapped():
                    widget.pack(fill="x")
            else:
                widget.pack_forget()
        except Exception:
            pass

    # ── refresh ──

    def refresh(self, status=None):
        if self.dev is None or status is None:
            return
        caps = self.caps

        if caps.supports("cnc"):
            self.ctl_cnc.set(status.cnc_level)
            self.app.set_tile("noise", "%d / 10" % status.cnc_level,
                              sub="0 = 最强降噪")
        if caps.supports("eq") and status.eq:
            for band in status.eq:
                row = self.ctl_eq.get(band.band_id)
                if row is not None:
                    row.set(band.current)
        if caps.supports("sidetone"):
            self.ctl_sidetone.set(
                SIDETONE_LABELS_BY_VALUE.get(status.sidetone, "关闭"))

        if caps.supports("anr"):
            self.app.read(self.dev.anr, on_ok=self._show_anr, label="读取降噪模式")
        if caps.supports("audio_settings"):
            self.app.read(self.dev.audio_settings, on_ok=self._show_audio_settings,
                          label="读取音频设置")

    def _show_anr(self, level):
        label = ANR_LABELS_BY_VALUE.get(level, "关闭")
        self.ctl_anr.set(label)
        self.app.set_tile("noise", label, sub="ANR 模式")

    def _show_audio_settings(self, settings):
        label = SPATIAL_QUOTE_BY_ID.get(settings.spatial, "关闭")
        self.ctl_spatial.set(label)
        self.app.set_tile("spatial", label)
        self.ctl_anc.set(settings.anc_toggle)
        self.ctl_wind.set(settings.wind_block)

    # ── debounce ──

    def _debounce(self, key, action):
        job = self._debounce_jobs.pop(key, None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._debounce_jobs[key] = self.after(DEBOUNCE_MS, action)
