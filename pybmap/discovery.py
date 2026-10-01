"""Device discovery on Windows.

Upstream bosectl finds a paired headset by shelling out to
``bluetoothctl`` and reading the device's ``Modalias`` (which carries the
USB-style VID/PID, i.e. the Bose product ID). Windows has no
``bluetoothctl``, so this module reconstructs the same information from
three independent sources and merges them:

1. **Registry** — ``HKLM\\SYSTEM\\CurrentControlSet\\Services\\BTHPORT\\
   Parameters\\Devices`` lists every *paired* device as a subkey whose name
   is the address, with a ``Name`` value. Needs no elevation, works even
   when the WinRT projections are absent, and is what makes auto-detection
   possible inside a frozen EXE.
2. **bluetoothapis.dll** — ``BluetoothFindFirstDevice`` adds live state
   (connected / authenticated) that the registry does not carry.
3. **SetupAPI** — ``SetupDi*`` exposes each Bluetooth device's PnP
   hardware IDs, which contain ``VID&000205a7_PID&4082``. That is the
   Windows equivalent of Linux's Modalias and is the only reliable way to
   map a device to its Bose product ID, so it drives device-type
   auto-detection.

Every source is wrapped so a failure degrades to the next one; the GUI
always offers manual MAC entry and an explicit device-type dropdown as the
final fallback.
"""

import ctypes
import ctypes.wintypes
import re
import sys
import threading

from .catalog import BOSE_USB_VID, known_devices, lookup_device
from .devices import DEVICES

__all__ = [
    "discover", "discover_all", "find_bmap_device", "suggest_device_type",
    "is_bose", "device_type_for_product_id", "radio_present",
    "radio_connectable", "diagnose",
]

#: Only 12 hex digits in colon form are treated as an address.
_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# Windows spells a Bluetooth address in a device instance ID in several
# ways depending on the profile. Every one of them anchors the address, so
# the patterns are anchored too: a bare 12-hex-digit search would happily
# match a slice of the service-class GUID that sits earlier in the same
# string (``00805f9b34fb`` decodes to the very plausible-looking
# ``00:80:5F:9B:34:FB``).
_MAC_PATTERNS = (
    re.compile(r"&0&([0-9A-Fa-f]{12})"),          # classic BT: ...&0&<addr>_C...
    re.compile(r"Dev_([0-9A-Fa-f]{12})"),         # BTHENUM\Dev_<addr>
    re.compile(r"^(?:[0-9A-Fa-f]{12})$"),         # bare key value
    re.compile(r"((?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2})"),  # AA:BB:CC:DD:EE:FF
)

_IS_WINDOWS = sys.platform == "win32"

# SetupAPI / device-info constants.
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
SPDRP_FRIENDLYNAME = 0x0000000C
SPDRP_HARDWAREID = 0x00000001
SPDRP_DEVICEDESC = 0x00000000
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259

#: bluetoothapis.dll, loaded once. None when unavailable.
try:  # pragma: no cover - platform dependent
    _BT = ctypes.windll.bluetoothapis if _IS_WINDOWS else None
except Exception:  # pragma: no cover
    _BT = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_mac(value):
    """Format a 48-bit Bluetooth address as colon-hex uppercase."""
    hexstr = "%012X" % (int(value) & 0xFFFFFFFFFFFF)
    return ":".join(hexstr[i:i + 2] for i in range(0, 12, 2))


def _mac_from_reversed_hex(text):
    """Decode the little-endian address spelling used by BTHPORT keys.

    Windows stores paired devices under a 12-hex-character key holding the
    address with its bytes reversed, e.g. ``11F5D0F1F268`` is
    ``68:F2:1F:0D:F5:11``.
    """
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", text or ""):
        return None
    pairs = [text[i:i + 2].upper() for i in range(0, 12, 2)]
    return ":".join(reversed(pairs))


def _mac_in_text(text):
    """Pull the first anchored address out of a longer string, if any.

    Deliberately does *not* accept a bare 12-hex-digit run anywhere in the
    string: the surrounding PnP identifiers contain GUID segments that would
    match and decode to a bogus but well-formed address.
    """
    if not text:
        return None
    for pattern in _MAC_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        token = match.group(1) if match.groups() else match.group(0)
        if ":" in token or "-" in token:
            candidate = token.replace("-", ":").upper()
            if _MAC_RE.match(candidate):
                return candidate
            continue
        candidate = _fmt_mac(int(token, 16))
        if _MAC_RE.match(candidate):
            return candidate
    return None


def is_bose(name):
    """Heuristic: does a device name look like a Bose audio product?"""
    if not name:
        return False
    n = name.lower()
    if n.startswith("le-") or n.startswith("le_"):
        n = n[3:]
    return any(tok in n for tok in
               ("bose", "quietcomfort", "quiet comfort", "qc ", "qc2", "qc3",
                "soundlink", "ultra open"))


def _clean_name(name):
    """Strip the Windows LE- duplicate prefix from a device name."""
    n = (name or "").strip()
    if n.lower().startswith("le-") or n.lower().startswith("le_"):
        n = n[3:].strip()
    return n


# ── source 1: registry (paired devices) ───────────────────────────────────────

def discover_registry():
    """List paired Bluetooth devices from the BTHPORT registry hive.

    Returns:
        List of dicts with keys ``name``, ``mac``, ``paired``.
    """
    if not _IS_WINDOWS:
        return []
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return []

    path = (r"SYSTEM\CurrentControlSet\Services\BTHPORT"
            r"\Parameters\Devices")
    out = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as root:
            index = 0
            while True:
                try:
                    key_name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                mac = _mac_from_reversed_hex(key_name)
                if not mac:
                    continue
                name = ""
                try:
                    with winreg.OpenKey(root, key_name) as sub:
                        raw, _ = winreg.QueryValueEx(sub, "Name")
                        if isinstance(raw, bytes):
                            name = raw.decode("utf-8", "replace")
                        else:
                            name = str(raw)
                except OSError:
                    pass
                out.append({"name": _clean_name(name), "mac": mac, "paired": True})
    except OSError:
        return []
    return out


# ── source 2: bluetoothapis.dll (live connection state) ───────────────────────

class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [
        ("wYear", ctypes.c_ushort), ("wMonth", ctypes.c_ushort),
        ("wDayOfWeek", ctypes.c_ushort), ("wDay", ctypes.c_ushort),
        ("wHour", ctypes.c_ushort), ("wMinute", ctypes.c_ushort),
        ("wSecond", ctypes.c_ushort), ("wMilliseconds", ctypes.c_ushort),
    ]


class _BLUETOOTH_ADDRESS(ctypes.Union):
    _fields_ = [("ullLong", ctypes.c_ulonglong), ("rgBytes", ctypes.c_ubyte * 6)]


class _BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("Address", _BLUETOOTH_ADDRESS),
        ("ulClassofDevice", ctypes.c_ulong),
        ("fConnected", ctypes.c_int),
        ("fRemembered", ctypes.c_int),
        ("fAuthenticated", ctypes.c_int),
        ("stLastSeen", _SYSTEMTIME),
        ("stLastUsed", _SYSTEMTIME),
        ("szName", ctypes.c_wchar * 248),
        ("ulNamLen", ctypes.c_ulong),
    ]


class _BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("fReturnAuthenticated", ctypes.c_int),
        ("fReturnRemembered", ctypes.c_int),
        ("fReturnUnknown", ctypes.c_int),
        ("fReturnConnected", ctypes.c_int),
        ("fIssueInquiry", ctypes.c_int),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", ctypes.c_void_p),
    ]


def discover_ctypes():
    """Enumerate Bluetooth devices via bluetoothapis.dll.

    Returns:
        List of dicts: name, mac, connected, authenticated, paired.
    """
    if _BT is None:
        return []
    try:
        _BT.BluetoothFindFirstDevice.argtypes = [
            ctypes.POINTER(_BLUETOOTH_DEVICE_SEARCH_PARAMS),
            ctypes.POINTER(_BLUETOOTH_DEVICE_INFO),
        ]
        _BT.BluetoothFindFirstDevice.restype = ctypes.c_void_p
        _BT.BluetoothFindNextDevice.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_BLUETOOTH_DEVICE_INFO)]
        _BT.BluetoothFindNextDevice.restype = ctypes.c_int
        _BT.BluetoothFindDeviceClose.argtypes = [ctypes.c_void_p]
        _BT.BluetoothFindDeviceClose.restype = ctypes.c_int
    except Exception:  # pragma: no cover
        pass

    info = _BLUETOOTH_DEVICE_INFO()
    info.dwSize = ctypes.sizeof(_BLUETOOTH_DEVICE_INFO)
    params = _BLUETOOTH_DEVICE_SEARCH_PARAMS()
    params.dwSize = ctypes.sizeof(_BLUETOOTH_DEVICE_SEARCH_PARAMS)
    params.fReturnAuthenticated = 1
    params.fReturnRemembered = 1
    params.fReturnUnknown = 0
    params.fReturnConnected = 1
    params.fIssueInquiry = 0
    params.cTimeoutMultiplier = 0
    params.hRadio = None

    results = []
    try:
        handle = _BT.BluetoothFindFirstDevice(ctypes.byref(params),
                                             ctypes.byref(info))
        if not handle:
            return results
        try:
            while True:
                name = info.szName.split("\x00", 1)[0].strip()
                results.append({
                    "name": _clean_name(name),
                    "mac": _fmt_mac(info.Address.ullLong),
                    "connected": bool(info.fConnected),
                    "authenticated": bool(info.fAuthenticated),
                    "paired": bool(info.fRemembered) or bool(info.fAuthenticated),
                })
                info.dwSize = ctypes.sizeof(_BLUETOOTH_DEVICE_INFO)
                if not _BT.BluetoothFindNextDevice(handle, ctypes.byref(info)):
                    break
        finally:
            _BT.BluetoothFindDeviceClose(handle)
    except Exception:
        # A low-level failure must never take discovery down with it.
        return results
    return results


class _BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
    """``BLUETOOTH_FIND_RADIO_PARAMS`` — note it holds *only* ``dwSize``.

    This is not ``BLUETOOTH_DEVICE_SEARCH_PARAMS``. Passing the larger
    device-search structure to ``BluetoothFindFirstRadio`` makes the API
    reject the call (it validates ``dwSize``), which surfaces as "no
    Bluetooth adapter detected" on a machine that has one.
    """

    _fields_ = [("dwSize", ctypes.c_ulong)]


def _first_radio():
    """Return a live radio handle, or None. Caller must close it."""
    if _BT is None:
        return None
    try:
        _BT.BluetoothFindFirstRadio.argtypes = [
            ctypes.POINTER(_BLUETOOTH_FIND_RADIO_PARAMS),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        _BT.BluetoothFindFirstRadio.restype = ctypes.c_void_p
        _BT.BluetoothFindRadioClose.argtypes = [ctypes.c_void_p]
        _BT.BluetoothFindRadioClose.restype = ctypes.c_int
        _BT.BluetoothIsConnectable.argtypes = [ctypes.c_void_p]
        _BT.BluetoothIsConnectable.restype = ctypes.c_int

        params = _BLUETOOTH_FIND_RADIO_PARAMS()
        params.dwSize = ctypes.sizeof(_BLUETOOTH_FIND_RADIO_PARAMS)
        radio = ctypes.c_void_p()
        find = _BT.BluetoothFindFirstRadio(ctypes.byref(params),
                                          ctypes.byref(radio))
        if not find or not radio.value:
            if find:
                _BT.BluetoothFindRadioClose(find)
            return None
        # Keep the find handle with the radio; it must outlive the radio.
        return find, radio.value
    except Exception:
        return None


def radio_present():
    """True when the machine has at least one Bluetooth adapter."""
    found = _first_radio()
    if not found:
        return False
    find, radio = found
    try:
        return bool(radio)
    finally:
        _BT.BluetoothFindRadioClose(find)


def radio_connectable():
    """True when a Bluetooth adapter exists *and* is switched on.

    Distinguishing this from :func:`radio_present` is what lets the
    self-check tell "your PC has no Bluetooth" apart from "Bluetooth is
    turned off", which need very different fixes.
    """
    found = _first_radio()
    if not found:
        return False
    find, radio = found
    try:
        return bool(_BT.BluetoothIsConnectable(radio))
    except Exception:
        return False
    finally:
        _BT.BluetoothFindRadioClose(find)


# ── source 3: SetupAPI (PnP hardware IDs -> Bose product ID) ──────────────────

def _setupapi_product_ids():
    """Map ``mac -> product_id`` from Bluetooth PnP hardware IDs.

    Windows records ``VID&000205a7_PID&4082`` in each device's hardware ID
    list, which is the same information Linux exposes as Modalias. The
    address is the tail of the device instance ID.

    Returns:
        Dict of MAC -> int product id; empty when unavailable.
    """
    if not _IS_WINDOWS:
        return {}
    try:
        setupapi = ctypes.WinDLL("setupapi")
        cfgmgr = ctypes.WinDLL("cfgmgr32")
    except OSError:  # pragma: no cover
        return {}

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    # {e0cbf06c-cd8b-4647-bb8a-263b43f0f974} = GUID_DEVCLASS_BLUETOOTH
    guid = GUID(0xE0CBF06C, 0xCD8B, 0x4647,
                (ctypes.c_ubyte * 8)(0xBB, 0x8A, 0x26, 0x3B, 0x43, 0xF0, 0xF9, 0x74))

    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_ulong]
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiEnumDeviceInfo.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
    setupapi.SetupDiEnumDeviceInfo.restype = ctypes.c_int
    setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong)]
    setupapi.SetupDiGetDeviceInstanceIdW.restype = ctypes.c_int
    cfgmgr.CM_Get_Device_ID_Size.argtypes = [
        ctypes.POINTER(ctypes.c_ulong), ctypes.c_ulong, ctypes.c_ulong]

    class SP_DEVINFO_DATA(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("ClassGuid", GUID),
                    ("DevInst", ctypes.c_ulong), ("Reserved", ctypes.c_void_p)]

    out = {}
    devs = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                         DIGCF_PRESENT)
    if devs in (None, ctypes.c_void_p(-1).value, 0):
        return {}
    try:
        data = SP_DEVINFO_DATA()
        data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        index = 0
        while setupapi.SetupDiEnumDeviceInfo(devs, index, ctypes.byref(data)):
            index += 1
            buf = ctypes.create_unicode_buffer(1024)
            if not setupapi.SetupDiGetDeviceInstanceIdW(
                    devs, ctypes.byref(data), buf, 1024, None):
                continue
            instance = buf.value
            match = re.search(r"VID&([0-9A-Fa-f]{8})_PID&([0-9A-Fa-f]{4})", instance)
            if not match:
                continue
            if int(match.group(1), 16) != BOSE_USB_VID:
                continue
            mac = _mac_from_instance_id(instance)
            if mac:
                out.setdefault(mac, int(match.group(2), 16))
    except Exception:
        return out
    finally:
        try:
            setupapi.SetupDiDestroyDeviceInfoList(devs)
        except Exception:
            pass
    return out


def _mac_from_instance_id(instance):
    """Extract the device address from a BTHENUM device instance ID.

    Instance IDs look like::

        BTHENUM\\{0000110b-...}_VID&000205a7_PID&4082\\
            7&1a2b3c4d&0&68F21F0DF511_C00000000

    The address is the 12-hex run after the final ``&0&``. The GUID earlier
    in the same string also contains a 12-hex run, which is why the match
    is anchored rather than a plain search.
    """
    tail = (instance or "").rsplit("\\", 1)[-1]
    for pattern in _MAC_PATTERNS[:2]:
        match = pattern.search(tail)
        if match:
            return _fmt_mac(int(match.group(1), 16))
    return _mac_in_text(instance)


# ── source 4: WinRT (optional) ────────────────────────────────────────────────

def discover_winrt():  # pragma: no cover - needs the optional winrt package
    """Enumerate devices via Windows.Devices.Bluetooth, when available.

    Returns:
        List of dicts in the same shape as :func:`discover_ctypes`.
    """
    try:
        import asyncio
        import winrt.windows.devices.bluetooth as bt  # type: ignore
        import winrt.windows.devices.enumeration as dev_enum  # type: ignore
    except ImportError:
        return []

    async def _run():
        selector = bt.BluetoothDevice.get_device_selector()
        coll = await dev_enum.DeviceInformation.find_all_async(selector)
        out = []
        for item in coll:
            mac = ""
            try:
                dev = await bt.BluetoothDevice.from_id_async(item.id)
                if dev is not None:
                    mac = _fmt_mac(dev.bluetooth_address)
            except Exception:
                pass
            out.append({
                "name": _clean_name(item.name or ""),
                "mac": mac,
                "connected": bool(item.is_connected),
                "authenticated": False,
                "paired": True,
            })
        return out

    try:
        return asyncio.run(_run())
    except Exception:
        return []


# ── merge + device-type resolution ────────────────────────────────────────────

def _merge(*sources):
    """Merge device dicts by MAC, preferring richer/live records."""
    merged = {}
    for records in sources:
        for rec in records:
            mac = rec.get("mac") or ""
            if not _MAC_RE.match(mac):
                continue
            cur = merged.get(mac)
            if cur is None:
                merged[mac] = dict(rec)
                continue
            if not cur.get("name") and rec.get("name"):
                cur["name"] = rec["name"]
            if rec.get("connected"):
                cur["connected"] = True
            if rec.get("authenticated"):
                cur["authenticated"] = True
    return list(merged.values())


def discover_all():
    """Every paired/known Bluetooth device, Bose or not.

    Returns:
        List of dicts with name, mac, connected, paired, authenticated, bose,
        and ``product_id``/``suggested_type`` when they could be resolved.
    """
    product_ids = _setupapi_product_ids()
    devices = _merge(discover_registry(), discover_winrt(), discover_ctypes())

    for d in devices:
        mac = d.get("mac", "")
        pid = product_ids.get(mac)
        d["product_id"] = pid
        d["bose"] = is_bose(d.get("name")) or (
            pid is not None and lookup_device(pid) is not None)
        d["suggested_type"] = device_type_for_product_id(pid) or \
            suggest_device_type(d.get("name"))
    devices.sort(key=lambda x: (not x.get("bose"), not x.get("connected"),
                                x.get("name") or ""))
    return devices


def discover(return_all=False):
    """Discover Bluetooth devices for the GUI picker.

    Args:
        return_all: Return every paired device. Otherwise return only
            Bose-looking devices, falling back to the full list when none
            look like Bose (so the user is never shown an empty list).

    Returns:
        List of device dicts, Bose devices first.
    """
    devices = discover_all()
    if return_all:
        return devices
    bose = [d for d in devices if d.get("bose")]
    return bose or devices


def device_type_for_product_id(product_id):
    """Map a Bose product ID to a config key in :data:`devices.DEVICES`."""
    if not product_id:
        return None
    entry = lookup_device(product_id)
    if entry and entry.config and entry.config in DEVICES:
        return entry.config
    return None


def suggest_device_type(name, product_id=None):
    """Best-effort config key for a device, from product ID then name.

    Returns:
        A key in :data:`devices.DEVICES`, or None when nothing matches.
    """
    found = device_type_for_product_id(product_id)
    if found:
        return found

    n = (name or "").lower().replace("bose", "").strip()
    if not n:
        return None
    if "ultra" in n and "open" in n:
        return "ultra_open"
    if "ultra" in n and "earbud" in n:
        return "qc_ultra2_earbuds"
    if "ultra" in n:
        return "qc_ultra2"
    if "qc45" in n or "quietcomfort 45" in n or "quiet comfort 45" in n:
        return "qc45"
    if "earbud" in n:
        return "qc_earbuds"
    if "35" in n:
        return "qc35"
    if "quietcomfort" in n or "quiet comfort" in n:
        return "qc_prince"
    return None


def find_bmap_device():
    """Auto-detect a paired BMAP-capable device.

    The Windows counterpart to upstream's ``find_bmap_device``: connected
    devices win over merely-paired ones, Bose devices win over others, and
    the device type comes from the PnP product ID when it can be read.

    Returns:
        ``(mac, device_type)``, or ``(None, None)`` when nothing matched.
    """
    devices = [d for d in discover_all() if d.get("bose")]
    if not devices:
        return (None, None)

    for want_connected in (True, False):
        for d in devices:
            if want_connected and not d.get("connected"):
                continue
            return (d["mac"], d.get("suggested_type") or "qc_ultra2")
    return (None, None)


# ── diagnostics ───────────────────────────────────────────────────────────────

def diagnose():
    """Collect an environment report for the GUI/CLI troubleshooting view.

    Returns:
        Dict with booleans and counts describing what Windows can see.
    """
    from .catalog import supported_devices

    registry = discover_registry()
    live = discover_ctypes()
    devices = discover_all()
    present = radio_present()
    return {
        "platform": sys.platform,
        "radio_present": present,
        "radio_connectable": radio_connectable() if present else False,
        "paired_count": len(registry),
        "enumerated_count": len(live),
        "bose_count": len([d for d in devices if d.get("bose")]),
        "product_ids_known": len(_setupapi_product_ids()),
        "winrt_available": _winrt_available(),
        "supported_devices": supported_devices(),
        "devices": devices,
    }


def _winrt_available():
    try:
        import winrt.windows.devices.bluetooth  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


# ── legacy aliases ────────────────────────────────────────────────────────────

#: Kept so older callers (and the GUI's first draft) keep working.
scan = discover
