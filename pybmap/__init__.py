"""pybmap — control Bose headphones over the BMAP protocol (Windows port).

A Windows-native port of the ``pybmap`` library from
`aaronsb/bosectl <https://github.com/aaronsb/bosectl>`_.

Preserved verbatim from upstream: the BMAP packet codec
(:mod:`pybmap.protocol`), constants, error taxonomy, device catalog, every
per-model device configuration (:mod:`pybmap.devices`), and the connection
layer (:mod:`pybmap.connection`). The public API is unchanged — same
functions, same arguments, same return types, same exceptions, so existing
scripts and the ``bosectl`` CLI keep working as documented upstream.

Changed for Windows: the transport and the discovery layer. Windows
exposes Bluetooth only through Winsock, so :mod:`pybmap.transport` is a
dependency-free ``ctypes`` implementation of RFCOMM, and
:mod:`pybmap.discovery` rebuilds paired-device enumeration and the
product-ID lookup that Linux gets from ``bluetoothctl`` Modalias.

Usage::

    import pybmap

    with pybmap.connect() as dev:          # auto-detects a paired Bose device
        print(dev.battery())
        dev.set_cnc(8)
        dev.set_eq(3, 0, -2)
        dev.set_mode("quiet")

    with pybmap.connect(mac="68:F2:1F:XX:XX:XX", device_type="qc_ultra2") as dev:
        ...

    with pybmap.connect(mock=True) as dev:  # no hardware required
        print(dev.status())

Note on messages: exception text is kept byte-for-byte identical to
upstream so callers and tests that match on it keep working. The desktop
GUI and the Windows CLI wrapper translate those messages for users; see
:func:`pybmap.friendly_error`.
"""

import errno
import os
import time

from .catalog import (
    BMAP_UUID,
    BOSE_USB_VID,
    CATALOG,
    BoseDevice,
    is_supported,
    known_devices,
    lookup_device,
    modalias,
    supported_devices,
    usb_ids,
)
from .connection import BmapConnection
from .constants import OP_STATUS
from .devices import DEVICES, PRODUCT_IDS, detect_device_type, get_device
from .discovery import diagnose, discover, find_bmap_device, suggest_device_type
from .errors import (
    BmapAuthError,
    BmapBusyError,
    BmapConnectionError,
    BmapDesyncError,
    BmapDeviceError,
    BmapError,
    BmapInvalidArgError,
    BmapNotFoundError,
    BmapTimeoutError,
)
from .messages import friendly_error
from .mock import MockTransport
from .protocol import (
    bmap_packet,
    fmt_response,
    parse_all_responses,
    parse_response,
)
from .transport import (
    PyBluezTransport,
    RfcommTransport,
    Transport,
    WindowsRfcommTransport,
    create_transport,
    describe_wsa_error,
    is_windows,
)
from .types import (
    BatteryReading,
    BatteryStatus,
    BmapResponse,
    ButtonMapping,
    DeviceStatus,
    EqBand,
    ModeConfig,
)

__version__ = "1.0.0"

#: The upstream release this port tracks. The protocol codec, device
#: configs and CLI in this tree are copied verbatim from that tag, so
#: reporting it alongside the port version makes bug reports unambiguous.
UPSTREAM_VERSION = "0.5.0"

#: Marks this build as the Windows port in banners and bug reports.
PORT_NAME = "bosectl-win"


def _env_timeout():
    """Read ``BMAP_TIMEOUT`` (seconds), or None when unset/invalid."""
    raw = os.environ.get("BMAP_TIMEOUT")
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def connect(mac=None, device_type=None, backend="auto", mock=False,
            timeout=None):
    """Connect to a BMAP device.

    Args:
        mac: Bluetooth address, e.g. ``"68:F2:1F:0D:F5:11"``. Auto-detected
            from paired devices when omitted or empty.
        device_type: A key from :data:`pybmap.devices.DEVICES`, such as
            ``"qc_ultra2"`` or ``"qc35"``. Auto-detected when ``mac`` is
            auto-detected too; otherwise required.
        backend: Transport backend — ``"auto"`` (default), ``"windows"``,
            ``"pybluez"`` or ``"mock"``.
        mock: Drive the in-memory simulated device instead of real hardware.
            Equivalent to setting ``BMAP_MOCK=1``. Useful for demos, tests
            and trying the GUI before pairing anything.
        timeout: Per-channel connect timeout in seconds. Defaults to the
            transport's own default.

    Returns:
        A connected :class:`BmapConnection`, usable as a context manager.

    Raises:
        BmapNotFoundError: No paired device could be found.
        BmapBusyError: The headset is still closing its previous link.
        BmapConnectionError: The connection failed.
        BmapInvalidArgError: Arguments were missing or contradictory.
    """
    if mock or os.environ.get("BMAP_MOCK"):
        device_type = device_type or "qc_ultra2"
        device = get_device(device_type)
        transport = create_transport(mac or "00:00:00:00:00:01", channel=2,
                                     backend="mock")
        transport.connect()
        return BmapConnection(transport, device)

    mac = mac or None
    device_type = device_type or None
    if timeout is None:
        # BMAP_TIMEOUT lets the CLI wrapper pass --timeout through without
        # touching upstream's connect() call site.
        timeout = _env_timeout()

    if mac is None:
        detected_mac, detected_type = find_bmap_device()
        if detected_mac is None:
            raise BmapNotFoundError(
                "No connected BMAP device found. Pair and connect "
                "via bluetoothctl, or pass mac= explicitly."
            )
        mac = detected_mac
        if device_type is None:
            device_type = detected_type
    elif device_type is None:
        raise BmapInvalidArgError("device_type is required when mac is specified")

    device = get_device(device_type)
    channel = getattr(device, "RFCOMM_CHANNEL", 2)
    transport = _open_transport(mac, channel, device, backend=backend,
                                timeout=timeout)
    return BmapConnection(transport, device)


# RFCOMM channels BMAP has been observed on. The channel a unit exposes can
# vary with firmware and with which profiles the stack has already claimed,
# so the device's configured channel is a first guess rather than a fact.
FALLBACK_CHANNELS = (2, 8, 9)

# Connect errors that mean "not right now" rather than "not here": the
# headset is still tearing down the previous RFCOMM link (EBUSY) or has not
# yet re-listened on the channel (ECONNREFUSED). The same channel is retried
# after each delay before the probe moves on. ECONNREFUSED is retried only on
# the configured channel: a fallback that refuses is usually just not a BMAP
# channel.
#
# Upstream restricts ECONNREFUSED retries to Linux because the macOS
# transport's errors carry no errno. The Windows transport does set errno —
# it maps WSAEBUSY/WSAEADDRINUSE to EBUSY and WSAECONNREFUSED to
# ECONNREFUSED — so the Linux behaviour is reproduced exactly here.
RETRYABLE_ERRNOS = frozenset({errno.EBUSY, errno.ECONNREFUSED})
FALLBACK_RETRYABLE_ERRNOS = frozenset({errno.EBUSY})
RETRY_DELAYS = (0.5, 1.0, 2.0)

# Indirection so tests can replace the backoff without actually sleeping.
_sleep = time.sleep

BUSY_MESSAGE = ("Headphones busy (another connection is still closing); "
                "try again in a few seconds")


def _build_transport(mac, channel, backend, timeout):
    """Instantiate a transport, honouring the requested backend.

    ``auto`` and ``windows`` go through the module-level ``RfcommTransport``
    name so tests (and callers) can substitute it, exactly as upstream does.
    """
    if backend in ("auto", "windows", None):
        if timeout is None:
            return RfcommTransport(mac, channel=channel)
        return RfcommTransport(mac, channel=channel, timeout=timeout)
    if backend == "mock":
        return MockTransport(mac=mac, channel=channel)
    if timeout is None:
        return create_transport(mac, channel=channel, backend=backend)
    return create_transport(mac, channel=channel, backend=backend,
                            timeout=timeout)


def _connect_with_retry(mac, ch, retryable, backend="auto", timeout=None):
    """Open ``ch``, retrying errnos in ``retryable`` with backoff.

    Returns the connected transport; raises the last BmapConnectionError.
    """
    for delay in RETRY_DELAYS + (None,):
        transport = _build_transport(mac, ch, backend, timeout)
        try:
            transport.connect()
            return transport
        except BmapConnectionError as e:
            if delay is None or getattr(e, "errno", None) not in retryable:
                raise
        _sleep(delay)


def _open_transport(mac, channel, device, backend="auto", timeout=None):
    """Connect on the configured channel, then probe fallbacks.

    A socket that accepts the connection is not proof of BMAP — several
    channels accept and stay silent — so each candidate is confirmed with a
    firmware GET [0.5] before it is returned. The configured channel is
    trusted without a probe because the per-model config was written for it
    (a QC35 answers on channel 8, not 2).

    Each channel is retried on EBUSY (the configured one also on
    ECONNREFUSED, see RETRY_DELAYS) before the probe moves on. A configured
    channel still busy after its retries raises BmapBusyError at once: the
    headset is there, so probing other channels would only add delay. A
    fallback still busy at the end is reported the same way rather than
    "no channel found".
    """
    init = getattr(device, "INIT_PACKET", None)
    candidates = [channel] + [c for c in FALLBACK_CHANNELS if c != channel]
    first_error = None
    busy_error = None
    tried = []
    for i, ch in enumerate(candidates):
        tried.append(str(ch))
        try:
            transport = _connect_with_retry(
                mac, ch,
                RETRYABLE_ERRNOS if i == 0 else FALLBACK_RETRYABLE_ERRNOS,
                backend=backend, timeout=timeout)
        except BmapConnectionError as e:
            first_error = first_error or e
            if busy_error is None and getattr(e, "errno", None) == errno.EBUSY:
                busy_error = e
                if i == 0:
                    break
            continue
        if i == 0:
            # Configured channel connected: trust it, send init if needed.
            if init:
                fblock, func = init
                transport.send_recv(bmap_packet(fblock, func, 1))  # GET
            return transport
        if _speaks_bmap(transport, init):
            return transport
        transport.close()
    tried = ", ".join(tried)
    if busy_error is not None:
        raise BmapBusyError(
            "%s (%s, tried %s): %s" % (BUSY_MESSAGE, mac, tried, busy_error),
            errno=errno.EBUSY,
        )
    raise BmapConnectionError(
        "No BMAP channel found on %s (tried %s): %s"
        % (mac, tried, first_error)
    )


def _speaks_bmap(transport, init):
    """Send a firmware GET and return True on any parseable BMAP reply."""
    try:
        if init:
            fblock, func = init
            transport.send_recv(bmap_packet(fblock, func, 1))
        data = transport.send_recv(bmap_packet(0, 5, 1))  # GET firmware
    except BmapError:
        return False
    resp = parse_response(data)
    # Any 4+ byte reply parses; a real BMAP peer echoes the address we asked.
    return (resp is not None and resp.fblock == 0 and resp.func == 5
            and resp.op == OP_STATUS)


__all__ = [
    "__version__", "UPSTREAM_VERSION", "PORT_NAME", "connect", "friendly_error",
    # transport
    "Transport", "RfcommTransport", "WindowsRfcommTransport",
    "PyBluezTransport", "MockTransport", "create_transport",
    "describe_wsa_error", "is_windows",
    # discovery
    "discover", "find_bmap_device", "suggest_device_type", "diagnose",
    # devices + catalog
    "DEVICES", "PRODUCT_IDS", "get_device", "detect_device_type",
    "BOSE_USB_VID", "BMAP_UUID", "BoseDevice", "CATALOG",
    "lookup_device", "known_devices", "supported_devices", "is_supported",
    "usb_ids", "modalias",
    # protocol + types
    "bmap_packet", "parse_response", "parse_all_responses", "fmt_response",
    "BatteryReading", "BatteryStatus", "BmapResponse", "ButtonMapping",
    "DeviceStatus", "EqBand", "ModeConfig", "BmapConnection",
    # errors
    "BmapError", "BmapConnectionError", "BmapBusyError", "BmapAuthError",
    "BmapDeviceError", "BmapInvalidArgError", "BmapTimeoutError",
    "BmapNotFoundError", "BmapDesyncError",
]
