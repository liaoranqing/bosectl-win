"""Tests for the user-facing message localisation.

The library's own exception text is deliberately left in upstream's English
so callers (and upstream's tests) can match on it. This layer is what users
actually read, so it carries the Chinese. The properties worth protecting
are: every real failure gets a translation, nothing is ever swallowed, and
the original text survives for bug reports.

The last test in this file is the interesting one: it checks each table
entry against the source tree, so a pattern can only be added if some code
in this repository actually produces that string. Without it the table
silently rots into a list of plausible-looking but unreachable typos.
"""

import os
import re

import pytest

from pybmap import messages
from pybmap.errors import (
    BmapAuthError, BmapBusyError, BmapConnectionError, BmapDesyncError,
    BmapDeviceError, BmapError, BmapInvalidArgError, BmapNotFoundError,
    BmapTimeoutError,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _has_cjk(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


# ── real upstream strings, copied from the raise sites ───────────────────────

BUSY = ("Headphones busy (another connection is still closing); "
        "try again in a few seconds (AA:BB:CC:DD:EE:FF, tried 8, 2, 9): "
        "[Errno 16] Device or resource busy")
NO_CHANNEL = ("No BMAP channel found on AA:BB:CC:DD:EE:FF (tried 8, 2, 9): "
              "Failed to connect to AA:BB:CC:DD:EE:FF: [Errno 111] "
              "Connection refused")
NO_DEVICE = ("No connected BMAP device found. Pair and connect "
             "via bluetoothctl, or pass mac= explicitly.")
NEEDS_TYPE = "device_type is required when mac is specified"
UNKNOWN_TYPE = "Unknown device type 'qc99'. Supported: qc35, qc45, qc_ultra2"
TIMEOUT = "No response from device"
CLOSED = "Connection closed by peer"
COMM_ERROR = "Communication error: [Errno 104] Connection reset by peer"
BAD_MAC = "Invalid Bluetooth MAC: 'nope'"
AUTH = ("Authentication required: fblock=0x1f func=0x0a op=ERROR "
        "payload=05000000")
DESYNC = ("Response came from [1.5], expected [1.7]. Reopen the connection.")
EMPTY_RESP = "Invalid or empty response"
EMPTY_BATT = "Empty battery response"
MISSING_AGG = "Battery response missing aggregate component 2"
MODE_WRITE = "Mode config write failed"
MODE_SWITCH = "Mode switch failed: fblock=0x1f func=0x03 op=ERROR"
UNKNOWN_MODE = "Unknown mode: gym"
NO_AUDIO = "Device does not support direct audio settings"
NO_MODECFG = "Device does not support mode configuration"
NO_ANC = "Device does not expose an ANC on/off toggle"
NO_REMAP = "Button remapping not supported on this device"
PRESET_EDIT = "Current mode 'Quiet' is not editable on this device"
PRESET_MOD = "Cannot modify preset mode 'Quiet'"
PRESET_DEL = "Cannot delete preset mode 'Quiet'"
PRESET_NAME = "'quiet' is a preset mode name; choose a different profile name"
NOT_FOUND = "Profile 'Gym' not found"
NO_SLOT = "No free profile slot available"
NO_CURCFG = "Current mode config not available"
NAME_LONG = "Name must be at most 32 bytes of UTF-8"
CNC_RANGE = "CNC level must be 0-10, got 99"
NOT_CONNECTED = "Not connected"

ALL_SAMPLES = (
    BUSY, NO_CHANNEL, NO_DEVICE, NEEDS_TYPE, UNKNOWN_TYPE, TIMEOUT, CLOSED,
    COMM_ERROR, BAD_MAC, AUTH, DESYNC, EMPTY_RESP, EMPTY_BATT, MISSING_AGG,
    MODE_WRITE, MODE_SWITCH, UNKNOWN_MODE, NO_AUDIO, NO_MODECFG, NO_ANC,
    NO_REMAP, PRESET_EDIT, PRESET_MOD, PRESET_DEL, PRESET_NAME, NOT_FOUND,
    NO_SLOT, NO_CURCFG, NAME_LONG, CNC_RANGE, NOT_CONNECTED,
)


@pytest.mark.parametrize("text", ALL_SAMPLES)
def test_every_real_message_is_translated(text):
    result = messages.translate_message(text)
    assert result != text, "no translation for %r" % text
    assert _has_cjk(result)


@pytest.mark.parametrize("text", ALL_SAMPLES)
def test_original_text_is_always_preserved(text):
    """Nothing is dropped: the upstream line is kept verbatim underneath."""
    assert text in messages.translate_message(text)


def test_unknown_message_passes_through_unchanged():
    text = "Something upstream added last week"
    assert messages.translate_message(text) == text


@pytest.mark.parametrize("text", ["", None])
def test_empty_input_is_safe(text):
    assert not messages.translate_message(text)


# ── exception-typed entry point ──────────────────────────────────────────────

def test_friendly_error_accepts_exceptions():
    assert _has_cjk(messages.friendly_error(BmapBusyError(BUSY)))


def test_friendly_error_accepts_plain_exceptions():
    assert messages.friendly_error(ValueError("boom")) == "boom"


# ── hints ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("exc", [
    BmapBusyError("x"), BmapNotFoundError("x"), BmapTimeoutError("x"),
    BmapAuthError("x"), BmapDesyncError("x"), BmapInvalidArgError("x"),
    BmapDeviceError("x"),
])
def test_every_error_type_has_a_hint(exc):
    hint = messages.error_hint(exc)
    assert hint and _has_cjk(hint)


def test_generic_error_has_no_hint():
    assert messages.error_hint(BmapError("plain")) == ""
    assert messages.error_hint(ValueError("plain")) == ""


# ── fixability classification ────────────────────────────────────────────────

@pytest.mark.parametrize("exc,expected", [
    (BmapBusyError("x"), True),          # retry after a wait
    (BmapConnectionError("x"), True),    # check Bluetooth / pairing
    (BmapNotFoundError("x"), True),      # pair the device
    (BmapTimeoutError("x"), True),
    (BmapAuthError("x"), False),         # firmware refuses SET; retrying is pointless
    (BmapDeviceError("x"), False),
    (ValueError("x"), False),            # not a BMAP failure at all
])
def test_is_user_fixable(exc, expected):
    assert messages.is_user_fixable(exc) is expected


def test_unsupported_feature_is_not_fixable():
    """A "your model cannot do this" error must not read as retryable."""
    assert messages.is_user_fixable(BmapError(NO_REMAP)) is False
    assert messages.is_user_fixable(BmapError(NO_AUDIO)) is False


# ── the table cannot rot ─────────────────────────────────────────────────────

def _tree_sources():
    """Concatenated source of every module that raises these errors."""
    chunks = []
    for sub in ("pybmap", "gui"):
        base = os.path.join(ROOT, sub)
        for dirpath, _dirnames, filenames in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                if os.path.basename(path) in ("messages.py",):
                    continue
                with open(path, encoding="utf-8") as handle:
                    chunks.append(handle.read())
    for name in ("cli.py", "bosectl.py"):
        with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
            chunks.append(handle.read())
    return "\n".join(chunks)


def test_patterns_are_reachable_in_this_tree():
    """Every pattern must match a string some module actually produces.

    Entries in :data:`messages.UPSTREAM_ONLY_PATTERNS` are exempt: they
    cover upstream's Linux/macOS transports, which this port replaces.
    """
    source = _tree_sources()
    unreachable = []
    for needle, _replacement in messages.PATTERNS:
        if needle in messages.UPSTREAM_ONLY_PATTERNS:
            continue
        if needle not in source:
            unreachable.append(needle)
    assert not unreachable, (
        "these patterns match nothing in the source tree, so they are dead "
        "weight or, worse, a typo: %r" % unreachable)


def test_upstream_only_set_matches_the_table():
    needles = {needle for needle, _ in messages.PATTERNS}
    assert messages.UPSTREAM_ONLY_PATTERNS <= needles, (
        "UPSTREAM_ONLY_PATTERNS names patterns that are not in PATTERNS")


def test_table_entries_are_well_formed():
    for entry in messages.PATTERNS:
        assert isinstance(entry, tuple) and len(entry) == 2, entry
        needle, replacement = entry
        assert needle and replacement
        assert isinstance(needle, str) and isinstance(replacement, str)
        assert _has_cjk(replacement), entry
        # A needle that is already Chinese would shadow a later, more
        # specific English pattern.
        assert not _has_cjk(needle), entry


def test_no_duplicate_needles():
    needles = [needle for needle, _ in messages.PATTERNS]
    duplicates = {n for n in needles if needles.count(n) > 1}
    assert not duplicates, duplicates


def test_no_pattern_is_shadowed_by_an_earlier_one():
    """First match wins, so an earlier needle must not contain a later one.

    If it did, the later entry would be unreachable and its message would
    silently get the wrong translation.
    """
    needles = [needle for needle, _ in messages.PATTERNS]
    for index, earlier in enumerate(needles):
        for later in needles[index + 1:]:
            assert later not in earlier, (earlier, later)


def test_pattern_module_has_no_leftover_private_alias_drift():
    """``_PATTERNS`` may only be an alias of the public table."""
    if hasattr(messages, "_PATTERNS"):
        assert messages._PATTERNS == messages.PATTERNS
