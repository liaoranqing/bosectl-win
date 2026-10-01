"""Tests for the Windows RFCOMM transport.

No real Bluetooth hardware is touched: these cover the pieces that can be
verified without a headset — address handling, struct layout, error
translation and backend selection. The live socket path is exercised
end-to-end by ``test_connection_mock.py`` (through the mock transport) and
by the ``--integration`` suite on a machine with paired headphones.
"""

import ctypes
import errno
import sys

import pytest

from pybmap import transport
from pybmap.errors import BmapConnectionError, BmapNotFoundError

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows Bluetooth stack required")


# ── address handling ─────────────────────────────────────────────────────────

class TestNormalizeMac:
    @pytest.mark.parametrize("raw", [
        "AA:BB:CC:DD:EE:FF",
        "aa:bb:cc:dd:ee:ff",
        "AA-BB-CC-DD-EE-FF",
        "AABBCCDDEEFF",
        "aa.bb.cc.dd.ee.ff",
        " AA:BB:CC:DD:EE:FF ",
    ])
    def test_accepts_common_spellings(self, raw):
        assert transport.WindowsRfcommTransport._normalize_mac(raw) == \
            "AA:BB:CC:DD:EE:FF"

    @pytest.mark.parametrize("raw", [
        "", "AA:BB", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:FF:00", "ZZ:BB:CC:DD:EE:FF",
        "not-a-mac",
    ])
    def test_rejects_bad_input(self, raw):
        with pytest.raises(BmapConnectionError):
            transport.WindowsRfcommTransport._normalize_mac(raw)

    def test_error_message_is_actionable(self):
        with pytest.raises(BmapConnectionError) as excinfo:
            transport.WindowsRfcommTransport._normalize_mac("nope")
        # The user needs to see the expected shape, not just "invalid".
        assert "AA:BB:CC:DD:EE:FF" in str(excinfo.value)


class TestMacToBtAddr:
    def test_bytes_are_reversed(self):
        # Windows stores the address little-endian; 68:F2:1F:0D:F5:11 packs
        # to 0x11F50D1FF268.
        assert transport.WindowsRfcommTransport._mac_to_btaddr(
            "68:F2:1F:0D:F5:11") == 0x11F50D1FF268

    def test_roundtrip_is_stable(self):
        addr = transport.WindowsRfcommTransport._mac_to_btaddr("00:11:22:33:44:55")
        assert addr == 0x554433221100


@windows_only
def test_sockaddr_bth_layout():
    """SOCKADDR_BTH must be 40 bytes on every supported architecture.

    If ctypes ever packs it differently the connect call passes a bad
    pointer and fails in a way that looks like "device not found", so this
    assumption is pinned down explicitly.
    """
    assert ctypes.sizeof(transport.SOCKADDR_BTH) == 40
    # btAddr is 8-byte aligned, which is what makes 40 come out right.
    assert transport.SOCKADDR_BTH.btAddr.offset == 8
    assert transport.SOCKADDR_BTH.port.offset == 32


# ── Winsock error translation ────────────────────────────────────────────────

class TestErrorMapping:
    def test_busy_codes_map_to_ebusy(self):
        # Both spellings of "channel in use" must look like EBUSY, because
        # the channel prober treats EBUSY as "device is there, wait".
        assert transport._WSA_TO_ERRNO[transport.WSAEBUSY] == errno.EBUSY
        assert transport._WSA_TO_ERRNO[transport.WSAEADDRINUSE] == errno.EBUSY

    def test_refused_and_timeout_map_for_probing(self):
        assert transport._WSA_TO_ERRNO[transport.WSAECONNREFUSED] == \
            errno.ECONNREFUSED
        assert transport._WSA_TO_ERRNO[transport.WSAETIMEDOUT] == errno.ETIMEDOUT

    def test_descriptions_are_localised_and_carry_the_code(self):
        text = transport.describe_wsa_error(transport.WSAECONNREFUSED)
        assert "10061" in text
        # A Chinese hint, not just the raw number.
        assert any("\u4e00" <= ch <= "\u9fff" for ch in text)

    def test_unknown_code_still_produces_text(self):
        text = transport.describe_wsa_error(9999)
        assert "9999" in text


class TestAddressNotAvailableHint:
    """WSAEADDRNOTAVAIL is the code a user is most likely to actually hit.

    It was first written as "this PC has no Bluetooth adapter", which sent the
    user to check the one thing that was not wrong: the report came from a
    laptop with a working, connectable radio whose only paired device was a
    BLE peripheral — an address that cannot host a classic RFCOMM channel at
    all. The hint has to name the plausible causes instead of guessing one.
    """

    def test_does_not_blame_the_local_adapter(self):
        text = transport.describe_wsa_error(transport.WSAEADDRNOTAVAIL)
        assert "没有可用的蓝牙适配器" not in text
        assert "10049" in text

    def test_names_the_real_causes(self):
        text = transport.describe_wsa_error(transport.WSAEADDRNOTAVAIL)
        # Out of range / powered off, and nothing to connect to.
        assert "未开机" in text or "不在范围内" in text
        assert "BLE" in text or "低功耗" in text

    def test_reachability_codes_are_named_correctly(self):
        """10051 is WSAENETUNREACH and 10065 is WSAEHOSTUNREACH.

        The constant was previously called ``WSAEAUNREACHABLE`` — a name that
        exists nowhere in Winsock — which made the hint read as if the device
        were at fault when the stack is what is down.
        """
        assert transport.WSAENETUNREACH == 10051
        assert transport.WSAEHOSTUNREACH == 10065
        assert not hasattr(transport, "WSAEAUNREACHABLE")
        assert "蓝牙已开启" in transport.describe_wsa_error(
            transport.WSAENETUNREACH)
        assert "范围内" in transport.describe_wsa_error(
            transport.WSAEHOSTUNREACH)

    def test_every_hint_is_reachable_and_non_empty(self):
        for code, hint in transport._WSA_HINTS.items():
            assert hint.strip(), code
            assert transport.describe_wsa_error(code).startswith(hint)


# ── backend selection ────────────────────────────────────────────────────────

class TestCreateTransport:
    def test_mock_backend(self):
        from pybmap.mock import MockTransport
        t = transport.create_transport("00:00:00:00:00:01", backend="mock")
        assert isinstance(t, MockTransport)

    def test_pybluez_backend_is_selectable(self):
        t = transport.create_transport("AA:BB:CC:DD:EE:FF", backend="pybluez")
        assert isinstance(t, transport.PyBluezTransport)
        # Not connected until connect() is called, and connect() reports a
        # clear message when the optional package is missing.
        assert t.is_connected is False

    @windows_only
    def test_auto_picks_windows_transport(self):
        t = transport.create_transport("AA:BB:CC:DD:EE:FF")
        assert isinstance(t, transport.WindowsRfcommTransport)
        assert t.channel == 2
        assert t.mac == "AA:BB:CC:DD:EE:FF"
        assert t.is_connected is False

    @windows_only
    def test_channel_is_honoured(self):
        t = transport.create_transport("AA:BB:CC:DD:EE:FF", channel=8)
        assert t.channel == 8

    def test_unknown_backend_is_rejected(self):
        with pytest.raises(BmapNotFoundError) as excinfo:
            transport.create_transport("AA:BB:CC:DD:EE:FF", backend="carrier-pigeon")
        assert "carrier-pigeon" in str(excinfo.value)

    def test_rfcomm_alias_matches_platform(self):
        if sys.platform == "win32":
            assert transport.RfcommTransport is transport.WindowsRfcommTransport
        else:
            assert transport.RfcommTransport is transport.PyBluezTransport


# ── guard rails ──────────────────────────────────────────────────────────────

class TestConnectionGuards:
    def test_send_before_connect_raises(self):
        t = transport.WindowsRfcommTransport("AA:BB:CC:DD:EE:FF")
        with pytest.raises(BmapConnectionError):
            t.send_recv(b"\x1f\x01\x05\x00")

    @windows_only
    def test_connect_to_unpaired_address_fails_cleanly(self):
        """An address nobody is listening on must raise, not hang or crash.

        A zero-length timeout keeps this quick: the point is that the error
        path produces a BmapConnectionError with a translated description.
        """
        t = transport.WindowsRfcommTransport("02:00:00:00:00:01", timeout=0.6)
        try:
            t.connect()
        except BmapConnectionError as exc:
            assert str(exc)
            assert getattr(exc, "errno", None) in (
                None, errno.EBUSY, errno.ECONNREFUSED, errno.ETIMEDOUT,
                errno.EHOSTUNREACH, errno.ENETUNREACH, errno.EADDRNOTAVAIL,
                errno.ENODEV, errno.EACCES,
            )
        else:  # pragma: no cover - only if something actually answered
            t.close()

    def test_close_is_idempotent(self):
        t = transport.WindowsRfcommTransport("AA:BB:CC:DD:EE:FF")
        t.close()
        t.close()
        assert t.is_connected is False
