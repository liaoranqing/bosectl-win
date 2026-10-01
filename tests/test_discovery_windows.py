"""Tests for the Windows discovery layer.

The enumeration itself depends on hardware, but the address decoding, the
product-ID mapping and the name heuristics are pure functions and are where
the real bugs live: a reversed-byte address that decodes wrongly sends the
connect attempt to a random device, and a wrong product-ID mapping selects
the wrong register layout.
"""

import sys

import pytest

from pybmap import discovery
from pybmap.catalog import lookup_device

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows discovery required")


# ── address formatting ───────────────────────────────────────────────────────

class TestAddressFormatting:
    @pytest.mark.parametrize("value,expected", [
        (0x68F21F0DF511, "68:F2:1F:0D:F5:11"),
        (0x001122334455, "00:11:22:33:44:55"),
        (0x000000000001, "00:00:00:00:00:01"),
        (0xFFFFFFFFFFFF, "FF:FF:FF:FF:FF:FF"),
    ])
    def test_fmt_mac(self, value, expected):
        assert discovery._fmt_mac(value) == expected

    @pytest.mark.parametrize("key,expected", [
        # BTHPORT keys hold the address with its bytes reversed, so the
        # printed MAC is the key read backwards in two-character groups:
        # 68:F2:1F:0D:F5:11  ->  11 F5 0D 1F F2 68  ->  "11F50D1FF268".
        ("11F50D1FF268", "68:F2:1F:0D:F5:11"),
        ("554433221100", "00:11:22:33:44:55"),
        ("11f50d1ff268", "68:F2:1F:0D:F5:11"),
    ])
    def test_registry_key_decoding(self, key, expected):
        assert discovery._mac_from_reversed_hex(key) == expected

    @pytest.mark.parametrize("key", ["", "11F5", "ZZZZZZZZZZZZ", None,
                                     "11F5D0F1F26800"])
    def test_registry_key_rejects_junk(self, key):
        assert discovery._mac_from_reversed_hex(key) is None

    def test_mac_in_instance_id(self):
        instance = ("BTHENUM\\{0000110b-0000-1000-8000-00805f9b34fb}"
                    "_VID&000205a7_PID&4082\\7&1a2b3c4d&0&68F21F0DF511_C00000000")
        assert discovery._mac_in_text(instance) == "68:F2:1F:0D:F5:11"

    def test_mac_from_instance_id_ignores_the_service_guid(self):
        """The GUID's own hex run must not be mistaken for the address.

        ``00805f9b34fb`` sits earlier in the string and decodes to the
        perfectly well-formed ``00:80:5F:9B:34:FB``; an unanchored search
        would return that instead of the real address.
        """
        instance = ("BTHENUM\\{0000110b-0000-1000-8000-00805f9b34fb}"
                    "_VID&000205a7_PID&4082\\7&1a2b3c4d&0&68F21F0DF511_C00000000")
        assert discovery._mac_from_instance_id(instance) == "68:F2:1F:0D:F5:11"

    def test_mac_in_text_handles_separated_spellings(self):
        assert discovery._mac_in_text("Dev_001122334455") == "00:11:22:33:44:55"
        assert discovery._mac_in_text("paired to AA-BB-CC-DD-EE-FF today") == \
            "AA:BB:CC:DD:EE:FF"

    def test_mac_in_text_rejects_unanchored_hex(self):
        # A GUID segment buried in a longer string is not an address, even
        # though it decodes to a well-formed one.
        assert discovery._mac_in_text("prefix 00805f9b34fb suffix") is None
        assert discovery._mac_in_text("") is None
        assert discovery._mac_in_text(None) is None


# ── product ID -> device config ──────────────────────────────────────────────

class TestDeviceTypeResolution:
    @pytest.mark.parametrize("product_id,expected", [
        (0x4082, "qc_ultra2"),      # QuietComfort Ultra Headphones (2nd Gen)
        (0x4062, "qc_ultra2_earbuds"),
        (0x4075, "qc_prince"),
        (0x402F, "qc_earbuds"),
        (0x4039, "qc45"),
        (0x4068, "ultra_open"),
        (0x400C, "qc35"),           # QuietComfort 35
        (0x4020, "qc35"),           # QuietComfort 35 II
    ])
    def test_known_products_map_to_configs(self, product_id, expected):
        assert discovery.device_type_for_product_id(product_id) == expected

    @pytest.mark.parametrize("product_id", [None, 0, 0x9999, 0x4015])
    def test_unknown_or_unsupported_products_return_none(self, product_id):
        assert discovery.device_type_for_product_id(product_id) is None

    def test_every_mapped_type_exists_in_the_registry(self):
        """A mapping to a config that is not installed would crash connect()."""
        from pybmap.devices import DEVICES
        from pybmap.catalog import known_devices
        for entry in known_devices():
            if not entry.config:
                continue
            assert entry.config in DEVICES, entry


class TestSuggestDeviceType:
    @pytest.mark.parametrize("name,expected", [
        ("Bose QuietComfort Ultra Headphones", "qc_ultra2"),
        ("LE-Bose QC Ultra 2", "qc_ultra2"),
        ("Bose QuietComfort Ultra Earbuds", "qc_ultra2_earbuds"),
        ("Bose Ultra Open Earbuds", "ultra_open"),
        ("Bose QuietComfort 45", "qc45"),
        ("Bose QC45", "qc45"),
        ("Bose QuietComfort 35 II", "qc35"),
        ("Bose QuietComfort Earbuds", "qc_earbuds"),
        ("Bose QuietComfort Headphones", "qc_prince"),
    ])
    def test_name_heuristics(self, name, expected):
        assert discovery.suggest_device_type(name) == expected

    def test_product_id_wins_over_name(self):
        # A misleading friendly name must not override the authoritative ID.
        assert discovery.suggest_device_type(
            "Something Else", product_id=0x4039) == "qc45"

    @pytest.mark.parametrize("name", ["", None, "JBL Flip 5", "Random Device"])
    def test_unknown_names_return_none(self, name):
        assert discovery.suggest_device_type(name) is None


class TestIsBose:
    @pytest.mark.parametrize("name", [
        "Bose QuietComfort Ultra", "LE-Bose QC Ultra 2", "QuietComfort 45",
        "QC35 II", "Bose SoundLink Flex", "Bose Ultra Open Earbuds",
    ])
    def test_recognises_bose(self, name):
        assert discovery.is_bose(name) is True

    @pytest.mark.parametrize("name", ["", None, "JBL Tune", "AirPods Pro",
                                      "Sony WH-1000XM5"])
    def test_rejects_others(self, name):
        assert discovery.is_bose(name) is False

    def test_le_duplicate_prefix_is_stripped(self):
        # Windows lists LE mirrors as "LE-<name>"; they must not look like a
        # different product.
        assert discovery._clean_name("LE-Bose QC Ultra 2") == "Bose QC Ultra 2"
        assert discovery.suggest_device_type("LE-Bose QC Ultra 2") == "qc_ultra2"


# ── enumeration contracts ────────────────────────────────────────────────────

class TestEnumerationContracts:
    def test_discover_returns_a_list(self):
        result = discovery.discover()
        assert isinstance(result, list)

    def test_discover_all_returns_a_list_with_expected_keys(self):
        for device in discovery.discover_all():
            assert set(device) >= {"name", "mac", "bose"}
            if device.get("mac"):
                assert discovery._MAC_RE.match(device["mac"])

    def test_merge_prefers_live_state_and_fills_names(self):
        paired = [{"name": "", "mac": "AA:BB:CC:DD:EE:FF", "paired": True}]
        live = [{"name": "Bose QC Ultra", "mac": "AA:BB:CC:DD:EE:FF",
                 "connected": True, "authenticated": True}]
        merged = discovery._merge(paired, live)
        assert len(merged) == 1
        assert merged[0]["name"] == "Bose QC Ultra"
        assert merged[0]["connected"] is True

    def test_merge_drops_records_without_a_valid_address(self):
        assert discovery._merge([{"name": "x", "mac": ""},
                                 {"name": "y", "mac": "garbage"}]) == []

    def test_find_bmap_device_returns_a_pair(self):
        result = discovery.find_bmap_device()
        assert isinstance(result, tuple) and len(result) == 2

    def test_scan_alias_is_discover(self):
        assert discovery.scan is discovery.discover


@windows_only
class TestDiagnosticsReport:
    def test_report_shape(self):
        report = discovery.diagnose()
        for key in ("platform", "radio_present", "radio_connectable",
                    "paired_count", "enumerated_count", "bose_count",
                    "product_ids_known", "winrt_available",
                    "supported_devices", "devices"):
            assert key in report, key
        # The Advanced view renders these directly, so the types matter.
        assert isinstance(report["radio_present"], bool)
        assert isinstance(report["radio_connectable"], bool)
        assert isinstance(report["devices"], list)
        assert isinstance(report["paired_count"], int)

    def test_radio_connectable_implies_present(self):
        # "Bluetooth is on" cannot be true on a machine with no adapter.
        if discovery.radio_connectable():
            assert discovery.radio_present()

    def test_radio_probes_never_raise(self):
        assert isinstance(discovery.radio_present(), bool)
        assert isinstance(discovery.radio_connectable(), bool)

    def test_registry_enumeration_never_raises(self):
        assert isinstance(discovery.discover_registry(), list)

    def test_bluetoothapis_enumeration_never_raises(self):
        assert isinstance(discovery.discover_ctypes(), list)

    def test_winrt_enumeration_never_raises(self):
        assert isinstance(discovery.discover_winrt(), list)
