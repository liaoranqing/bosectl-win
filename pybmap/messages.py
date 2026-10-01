"""User-facing translations of pybmap errors.

The library's exception *messages* are kept byte-for-byte identical to
upstream bosectl. That matters: ``bosectl-qt`` and other callers match on
substrings like ``"Device or resource busy"``, and upstream's own test suite
asserts them too. Localising the messages inside the library would break
both.

So localisation lives here, one layer up. The GUI calls
:func:`friendly_error` before showing a dialog and the Windows CLI wrapper
calls :func:`translate_message` on whatever upstream printed. Any message
this module does not recognise is returned unchanged, so new upstream text
degrades to English rather than being swallowed.

Every pattern below is keyed to a string that really exists in this tree —
:mod:`tests.test_messages` asserts as much — so the table cannot silently
rot into a list of typos.
"""

from .errors import (
    BmapAuthError, BmapBusyError, BmapConnectionError, BmapDesyncError,
    BmapDeviceError, BmapError, BmapInvalidArgError, BmapNotFoundError,
    BmapTimeoutError,
)

__all__ = ["friendly_error", "translate_message", "error_hint",
           "is_user_fixable", "PATTERNS", "UPSTREAM_ONLY_PATTERNS"]

#: Patterns that no code in *this* tree produces any more.
#:
#: Upstream raises these from its Linux and macOS transports, which this
#: port replaces. The Windows transports phrase the same conditions in
#: Chinese directly (see ``transport.describe_wsa_error``). The entries are
#: kept so that a caller handing us upstream-shaped text — an older library
#: version, a packaged tool built from upstream, a log pasted from a Linux
#: box — still gets a translation rather than raw English.
#:
#: ``tests/test_messages.py`` uses this set to hold the rest of the table to
#: a stronger standard: every other needle must exist in the source tree.
UPSTREAM_ONLY_PATTERNS = frozenset({
    "Connection refused",
    "Timed out connecting",
    "Failed to connect to",
    "No response from device",
    "Communication error",
    "Connection closed by peer",
    "Invalid Bluetooth MAC",
    "Not connected",
})

# Ordered (substring, replacement) pairs. First match wins, so the more
# specific patterns come before the general ones.
PATTERNS = (
    # ── connection / discovery ──────────────────────────────────────────────
    ("No connected BMAP device found",
     "未找到已配对的 Bose 设备。请先在「设置 → 蓝牙和其他设备」中完成配对，"
     "确认耳机已开机；也可以在程序里直接手动填写蓝牙地址。"),
    ("device_type is required when mac is specified",
     "手动指定蓝牙地址时，请同时选择设备型号。"),
    ("No BMAP channel found on",
     "无法与设备建立 BMAP 通信。请确认：蓝牙已开启、耳机已配对并开机，"
     "且没有被手机等其他设备占用连接。"),
    ("Headphones busy",
     "设备正忙：上一个连接尚未完全释放。请等 5 秒左右再试。"),
    ("Connection refused",
     "设备拒绝连接。请确认耳机已配对、已开机，并处于可连接范围内。"),
    ("Timed out connecting",
     "连接超时。请确认蓝牙已开启、耳机已开机且距离足够近。"),
    ("Failed to connect to",
     "无法连接到设备。请确认耳机已配对并处于可连接范围。"),
    ("No response from device",
     "设备没有响应。请确认耳机已开机；若刚连接过，请稍等几秒再试。"),
    ("Communication error",
     "与设备通信出错。连接可能已断开，请重新连接。"),
    ("Connection closed by peer",
     "连接已被设备关闭。请重新连接。"),
    ("Invalid Bluetooth MAC",
     "蓝牙地址格式无效，正确格式类似 AA:BB:CC:DD:EE:FF。"),
    ("Unknown device type",
     "不支持该设备型号。"),
    # ── protocol level ──────────────────────────────────────────────────────
    ("Authentication required",
     "该操作需要 Bose 云端鉴权，本工具无法执行。"
     "日常设置（模式、降噪、均衡器、多点连接等）走的是免鉴权的 SETGET，不受影响。"),
    ("Response came from",
     "设备回应与请求不匹配（通常是刚断开重连、旧数据残留）。"
     "请重新连接后再试。"),
    ("Invalid or empty response",
     "设备返回了无法识别的响应。请重试；若持续出现，请重新连接。"),
    ("Empty battery response",
     "设备没有返回电量数据。请稍后重试。"),
    ("Battery response missing aggregate component",
     "设备返回的电量数据不完整（缺少汇总电量）。请稍后重试。"),
    ("Mode config write failed",
     "写入模式配置失败。该模式可能不可编辑，或需要先在 Bose 应用中创建。"),
    ("Mode switch failed",
     "切换模式失败。该模式可能尚未创建，或当前固件不支持。"),
    ("Unknown mode",
     "未知的模式名称。可用 bosectl profiles 查看全部模式。"),
    ("Unknown command",
     "未知的命令。运行 bosectl --help 查看全部可用命令。"),
    # ── feature availability ────────────────────────────────────────────────
    ("Device does not expose an ANC on/off toggle",
     "该耳机型号不能单独开关主动降噪（它的降噪随模式变化）。"),
    ("Button remapping not supported",
     "该耳机型号不支持按键重映射。"),
    ("Device does not support",
     "该耳机型号不支持此功能。"),
    ("is not editable on this device",
     "当前模式是设备内置预设，无法修改。请先新建一个自定义配置。"),
    ("Cannot modify preset mode",
     "内置预设模式不能修改。请新建一个自定义配置。"),
    ("Cannot delete preset mode",
     "内置预设模式不能删除。"),
    ("is a preset mode name",
     "该名称与内置预设重名，请换一个名称。"),
    ("Profile '",
     "找不到该自定义配置。请用 bosectl profiles 查看现有配置名称。"),
    ("No free profile slot available",
     "自定义配置槽位已满。请先删除一个不再使用的配置。"),
    ("Current mode config not available",
     "当前模式没有可编辑的配置。请先创建自定义配置。"),
    # ── argument validation ─────────────────────────────────────────────────
    ("Name must be at most",
     "设备名称过长，请缩短后重试。"),
    ("CNC level must be",
     "降噪等级需要在 0-10 之间（0 = 最强降噪）。"),
    ("Not connected",
     "尚未连接到设备。"),
)

#: Extra one-line, actionable hint keyed by exception type.
_HINTS = {
    BmapBusyError: "提示：连续快速连接会触发此错误，等 5 秒左右即可。",
    BmapNotFoundError: "提示：「设置 → 蓝牙和其他设备」里应能看到已配对的耳机。",
    BmapTimeoutError: "提示：耳机待机后会短暂休眠，操作一次即可唤醒。",
    BmapAuthError: "提示：只有 SET / 固件类操作需要鉴权，日常设置不受影响。",
    BmapDesyncError: "提示：断开后重新连接即可恢复。",
}

#: Translated phrases that mean "retrying will not help".
_NOT_FIXABLE = ("需要 Bose 云端鉴权", "不支持此功能", "不能单独开关",
                "不能修改", "不能删除", "槽位已满", "请换一个名称",
                "不支持按键重映射")


def friendly_error(exc):
    """Translate an exception into a user-facing Chinese message.

    Args:
        exc: Any exception; typically a :class:`BmapError`.

    Returns:
        A human-readable message. Unknown messages pass through unchanged so
        nothing is ever hidden from the user.
    """
    return translate_message(str(exc))


def translate_message(text):
    """Translate an upstream error string into Chinese.

    Exposed separately from :func:`friendly_error` because the CLI wrapper
    only ever sees the text upstream printed, not the exception object.
    Returns ``text`` unchanged when nothing matches.
    """
    if not text:
        return text
    for needle, replacement in PATTERNS:
        if needle in text:
            if text.strip() == replacement:
                return text
            # Append the original line in full rather than trying to parse a
            # sub-field out of it: upstream's messages embed the device
            # address, the probed channel list and the OS error, and every
            # one of them matters in a bug report. Nothing is dropped.
            return "%s\n原始信息：%s" % (replacement, text.strip())
    return text


def error_hint(exc):
    """Return a short, type-specific follow-up hint, or an empty string."""
    for kind, hint in _HINTS.items():
        if isinstance(exc, kind):
            return hint
    if isinstance(exc, BmapInvalidArgError):
        return "提示：请检查设备型号和蓝牙地址是否填写正确。"
    if isinstance(exc, BmapDeviceError):
        return "提示：该设置项可能被固件锁定，或需要先在 Bose 应用中启用。"
    return ""


def is_user_fixable(exc):
    """True when retrying or changing something on the user's side can help.

    Distinguishes "your Bluetooth is off / not paired" (worth a hint) from
    "this firmware refuses the operation" (retrying will not help).
    """
    if isinstance(exc, (BmapAuthError, BmapDeviceError)):
        return False
    if isinstance(exc, BmapError):
        message = friendly_error(exc)
        return not any(fragment in message for fragment in _NOT_FIXABLE)
    return False
