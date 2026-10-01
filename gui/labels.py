"""Shared label maps for the UI.

These dictionaries live in one place so a view, the status strip and the
About page all describe the same value identically. The keys are the exact
strings the BMAP layer uses (preset names, spatial modes, ANR levels,
sidetone levels, device type keys); the values are what the user reads.
"""

from __future__ import annotations

__all__ = [
    "PRESET_LABELS", "PRESET_HINTS", "DEVICE_LABELS", "DEVICE_LABELS_BY_KEY",
    "SPATIAL_LABELS", "SPATIAL_VALUES", "SPATIAL_LABELS_BY_VALUE",
    "SPATIAL_QUOTE_BY_ID", "ANR_LABELS", "ANR_VALUES", "ANR_LABELS_BY_VALUE",
    "SIDETONE_LABELS", "SIDETONE_VALUES", "SIDETONE_LABELS_BY_VALUE",
    "localize_mode", "localize_device_type",
]

# ── modes ────────────────────────────────────────────────────────────────────

PRESET_LABELS = {
    "quiet": "安静",
    "aware": "感知",
    "immersion": "沉浸",
    "cinema": "影院",
}

PRESET_HINTS = {
    "quiet": "最强降噪，隔绝环境",
    "aware": "通透模式，保留周围声音",
    "immersion": "空间音频 + 头部追踪",
    "cinema": "空间音频，固定声场",
}

# ── device types ─────────────────────────────────────────────────────────────

DEVICE_LABELS = {
    "qc_ultra2": "QuietComfort Ultra 耳机 (2nd Gen)",
    "qc_ultra2_earbuds": "QuietComfort Ultra 耳塞 (2nd Gen)",
    "qc45": "QuietComfort 45",
    "qc_prince": "QuietComfort Headphones",
    "qc_earbuds": "QuietComfort Earbuds (1st Gen)",
    "qc35": "QuietComfort 35 / 35 II",
    "ultra_open": "Ultra Open Earbuds",
}
DEVICE_LABELS_BY_KEY = {v: k for k, v in DEVICE_LABELS.items()}

# ── spatial audio ────────────────────────────────────────────────────────────

SPATIAL_VALUES = {"关闭": "off", "房间": "room", "头部追踪": "head"}
SPATIAL_LABELS = list(SPATIAL_VALUES)
SPATIAL_LABELS_BY_VALUE = {v: k for k, v in SPATIAL_VALUES.items()}
SPATIAL_QUOTE_BY_ID = {0: "关闭", 1: "房间", 2: "头部追踪"}

# ── noise reduction (ANR, QC35 generation) ───────────────────────────────────

ANR_VALUES = {"关闭": "off", "高": "high", "风噪抑制": "wind", "低": "low"}
ANR_LABELS = list(ANR_VALUES)
ANR_LABELS_BY_VALUE = {v: k for k, v in ANR_VALUES.items()}

# ── sidetone ─────────────────────────────────────────────────────────────────

SIDETONE_VALUES = {"关闭": "off", "低": "low", "中": "medium", "高": "high"}
SIDETONE_LABELS = list(SIDETONE_VALUES)
SIDETONE_LABELS_BY_VALUE = {v: k for k, v in SIDETONE_VALUES.items()}


def localize_mode(name):
    """Render a protocol mode name the way the UI shows it."""
    if not name:
        return "—"
    return PRESET_LABELS.get(str(name).lower(), str(name))


def localize_device_type(key):
    """Render a ``devices.DEVICES`` key as its marketing name."""
    return DEVICE_LABELS.get(key, key)
