"""End-to-end tests driving the BmapConnection against the mock device.

These exercise the real protocol codec, parsers, and connection logic
without any Bluetooth hardware.
"""

import pytest

import pybmap
from pybmap.errors import BmapError


@pytest.fixture
def dev():
    with pybmap.connect(mock=True) as d:
        yield d


def test_status_reads(dev):
    s = dev.status()
    assert isinstance(s.battery, int) and 0 <= s.battery <= 100
    assert s.name
    assert s.firmware
    assert s.mode in ("quiet", "aware", "immersion", "cinema")


def test_cnc_roundtrip(dev):
    dev.set_cnc(7)
    cur, mx = dev.cnc()
    assert cur == 7
    assert mx == 10


def test_spatial_roundtrip(dev):
    dev.set_spatial("head")
    assert dev.audio_settings().spatial == 2
    dev.set_spatial("off")
    assert dev.audio_settings().spatial == 0


def test_wind_and_anc_toggles(dev):
    dev.set_wind(False)
    assert dev.audio_settings().wind_block is False
    dev.set_anc(False)
    assert dev.audio_settings().anc_toggle is False
    dev.set_wind(True)
    dev.set_anc(True)


def test_eq_roundtrip(dev):
    dev.set_eq(4, -3, 6)
    bands = {b.name: b.current for b in dev.eq()}
    assert bands["Bass"] == 4
    assert bands["Mid"] == -3
    assert bands["Treble"] == 6


def test_mode_switch(dev):
    dev.set_mode("aware")
    assert dev.mode() == "aware"
    dev.set_mode("cinema")
    assert dev.mode() == "cinema"


def test_modes_list(dev):
    modes = dev.modes()
    assert 0 in modes and modes[0].name == "Quiet"
    assert all(hasattr(m, "name") for m in modes.values())


def test_profile_create_update_delete(dev):
    slot = dev.create_profile("TestProfile", cnc_level=3, spatial=1)
    assert 4 <= slot <= 10
    dev.update_profile("TestProfile", cnc_level=8)
    found = [m for m in dev.modes().values() if m.name == "TestProfile"]
    assert found and found[0].cnc_level == 8
    dev.delete_profile("TestProfile")
    found = [m for m in dev.modes().values() if m.name == "TestProfile"]
    assert not found


def test_profile_name_rejection(dev):
    # "quiet" is a preset name and must be refused for custom profiles.
    with pytest.raises(BmapError):
        dev.create_profile("quiet")


def test_send_raw_returns_responses(dev):
    # A BMAP frame is [fblock, func, flags, length, ...payload]: 1f 01 05 00
    # is a zero-length START on [31.1] (GetAllModes), which the device
    # answers with one STATUS frame per mode slot on [31.6].
    resps = dev.send_raw("1f 01 05 00".replace(" ", ""))
    assert len(resps) >= 1
    assert all(r.fblock == 31 and r.func == 6 for r in resps)


def test_send_raw_rejects_short_packet(dev):
    # Fewer than four bytes cannot carry a length field; upstream returns
    # an empty list rather than raising.
    assert dev.send_raw("1f0105") == []
