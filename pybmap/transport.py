"""RFCOMM Bluetooth transport for BMAP devices — Windows implementation.

Upstream bosectl speaks to the headset through a raw ``AF_BLUETOOTH``
socket on Linux and through IOBluetooth on macOS. Windows has neither: the
Bluetooth stack is reachable only from Winsock, using the ``AF_BTH``
address family and the ``BTHPROTO_RFCOMM`` protocol with ``ws2_32.dll``.

This module therefore re-implements the transport on top of Winsock via
``ctypes`` — no PyBluez, no native build step, nothing to install. It is a
drop-in replacement for ``LinuxRfcommTransport``: the byte-pipe semantics
(send one framed packet, read the reply, discard stale bytes first) are
preserved exactly so the connection layer above needs no changes.

Pieces worth knowing about, all of which exist because Windows differs
from POSIX:

* ``SO_RCVTIMEO``/``SO_SNDTIMEO`` take a millisecond DWORD, not a
  ``struct timeval``.
* A blocking ``connect()`` on RFCOMM can hang for the full Bluetooth
  driver timeout, and the send timeout does not bound it the way it does
  on Linux. The connect is therefore done non-blocking and bounded with
  ``select()``.
* Winsock reports failures as ``WSA*`` codes rather than ``errno``
  values. They are translated to the matching ``errno`` constants so the
  channel-probing logic in :mod:`pybmap` (which looks for EBUSY and
  ECONNREFUSED) behaves the same as it does on Linux.
"""

import ctypes
import errno
import platform
import socket
import sys
import time

from .errors import (
    BmapConnectionError,
    BmapNotFoundError,
    BmapTimeoutError,
)

__all__ = [
    "Transport", "WindowsRfcommTransport", "RfcommTransport",
    "PyBluezTransport", "create_transport", "is_windows",
]

is_windows = sys.platform == "win32"

# ── Winsock / Bluetooth constants ─────────────────────────────────────────────

AF_BTH = 32
SOCK_STREAM = 1
BTHPROTO_RFCOMM = 3
BTH_ADDR_NULL = 0

SOL_SOCKET = 0xFFFF
SO_SNDTIMEO = 0x1005
SO_RCVTIMEO = 0x1006
SO_ERROR = 0x1007

FIONBIO = 0x8004667E
SOCKET_ERROR = -1

WSAEWOULDBLOCK = 10035
WSAEINPROGRESS = 10036
WSAENOTSOCK = 10038
WSAEADDRINUSE = 10048
WSAEADDRNOTAVAIL = 10049
WSAEAUNREACHABLE = 10051
WSAECONNREFUSED = 10061
WSAETIMEDOUT = 10060
WSAENOTCONN = 10057
WSAEBUSY = 10016
WSAEACCES = 10013
WSAENODEV = 10019

#: Winsock error -> Python ``errno``. Only the codes the channel prober
#: cares about are mapped; anything else keeps ``errno=None`` and is
#: reported verbatim, which is more useful in a bug report than a guess.
_WSA_TO_ERRNO = {
    WSAEBUSY: errno.EBUSY,
    WSAEADDRINUSE: errno.EBUSY,      # RFCOMM channel already claimed
    WSAECONNREFUSED: errno.ECONNREFUSED,
    WSAETIMEDOUT: errno.ETIMEDOUT,
    WSAENOTCONN: errno.ENOTCONN,
    WSAEADDRNOTAVAIL: errno.EADDRNOTAVAIL,
    WSAEAUNREACHABLE: errno.EHOSTUNREACH,
    WSAEACCES: errno.EACCES,
    WSAENODEV: errno.ENODEV,
}

#: Human-readable hints for the codes a user can actually act on.
_WSA_HINTS = {
    WSAEBUSY: "另一个程序仍占用该蓝牙通道（通常是刚断开的上一次连接）",
    WSAEADDRINUSE: "该蓝牙通道已被占用，请等待几秒后重试",
    WSAECONNREFUSED: "设备拒绝连接：请确认耳机已与电脑配对、已开机并在范围内",
    WSAETIMEDOUT: "连接超时：请确认蓝牙已开启且耳机处于可连接距离内",
    WSAENOTCONN: "蓝牙链路未连接",
    WSAEADDRNOTAVAIL: "本机没有可用的蓝牙适配器",
    WSAEAUNREACHABLE: "无法访问设备，请确认耳机已开机",
    WSAEACCES: "权限不足：请在“设置 → 蓝牙和其他设备”中重新配对",
    WSAENODEV: "未找到蓝牙设备",
}


# ── ctypes structures ─────────────────────────────────────────────────────────

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SOCKADDR_BTH(ctypes.Structure):
    """Mirror of the Winsock ``SOCKADDR_BTH`` structure.

    ``addressFamily``(2) + 6 bytes of alignment padding + ``btAddr``(8) +
    ``serviceClassId``(16) + ``port``(4) = 40 bytes on both x64 and x86,
    because ``btAddr`` is 8-byte aligned either way.
    """

    _fields_ = [
        ("addressFamily", ctypes.c_ushort),
        ("btAddr", ctypes.c_ulonglong),
        ("serviceClassId", GUID),
        ("port", ctypes.c_ulong),
    ]


class _timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _fd_set(ctypes.Structure):
    """WinSock ``fd_set``: a count followed by a fixed SOCKET array."""

    _fields_ = [
        ("fd_count", ctypes.c_uint),
        ("fd_array", ctypes.c_uint64 * 64),
    ]


# ── Winsock bindings ──────────────────────────────────────────────────────────

def _load_winsock():
    """Return the ``ws2_32`` library with prototypes applied, or None."""
    if not is_windows:
        return None
    try:
        lib = ctypes.WinDLL("ws2_32")
    except OSError:
        return None

    # SOCKET is UINT_PTR: declaring the default c_int restype would
    # truncate a valid 64-bit handle on x64. Be explicit everywhere.
    lib.WSAStartup.argtypes = [ctypes.c_ushort, ctypes.c_void_p]
    lib.WSAStartup.restype = ctypes.c_int
    lib.WSACleanup.argtypes = []
    lib.WSACleanup.restype = ctypes.c_int
    lib.WSAGetLastError.argtypes = []
    lib.WSAGetLastError.restype = ctypes.c_int
    lib.socket.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.socket.restype = ctypes.c_uint64
    lib.connect.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    lib.connect.restype = ctypes.c_int
    lib.send.argtypes = [ctypes.c_uint64, ctypes.c_char_p, ctypes.c_int,
                         ctypes.c_int]
    lib.send.restype = ctypes.c_int
    lib.recv.argtypes = [ctypes.c_uint64, ctypes.c_char_p, ctypes.c_int,
                         ctypes.c_int]
    lib.recv.restype = ctypes.c_int
    lib.closesocket.argtypes = [ctypes.c_uint64]
    lib.closesocket.restype = ctypes.c_int
    lib.setsockopt.argtypes = [ctypes.c_uint64, ctypes.c_int, ctypes.c_int,
                               ctypes.c_char_p, ctypes.c_int]
    lib.setsockopt.restype = ctypes.c_int
    lib.getsockopt.argtypes = [ctypes.c_uint64, ctypes.c_int, ctypes.c_int,
                               ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    lib.getsockopt.restype = ctypes.c_int
    lib.ioctlsocket.argtypes = [ctypes.c_uint64, ctypes.c_ulong,
                                ctypes.POINTER(ctypes.c_ulong)]
    lib.ioctlsocket.restype = ctypes.c_int
    lib.select.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, ctypes.c_void_p]
    lib.select.restype = ctypes.c_int
    return lib


_WSA = _load_winsock()


def describe_wsa_error(code):
    """Return a one-line, user-facing explanation for a Winsock code."""
    hint = _WSA_HINTS.get(code)
    if hint:
        return "%s (WSA %d)" % (hint, code)
    return "蓝牙通信失败 (WSA %d)" % code


# ── Transport interface ───────────────────────────────────────────────────────

class Transport:
    """Abstract byte pipe to a BMAP device.

    Higher layers (``BmapConnection``) never touch the OS: they only call
    :meth:`send_recv` and :meth:`close`. Subclasses implement the
    platform-specific connect/send/recv.
    """

    def connect(self):
        """Open the channel. Raises BmapConnectionError on failure."""
        raise NotImplementedError

    def send_recv(self, packet, drain=False):
        """Send one framed packet and return the device's raw reply bytes.

        Args:
            packet: Raw bytes, already framed by ``protocol.bmap_packet``.
            drain: Keep reading until the device goes quiet. Used for the
                START commands ([31.1]) that stream several STATUS frames.

        Returns:
            Raw reply bytes; may contain multiple BMAP frames when draining.
        """
        raise NotImplementedError

    def close(self):
        """Close the channel."""
        raise NotImplementedError

    @property
    def is_connected(self):
        raise NotImplementedError

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()


# ── Windows RFCOMM over Winsock ───────────────────────────────────────────────

class WindowsRfcommTransport(Transport):
    """RFCOMM transport on Windows, dependency-free.

    Mirrors ``LinuxRfcommTransport`` in upstream bosectl: same constructor
    signature, same stale-byte handling, same error types. Only the syscalls
    underneath differ.
    """

    # Upper bound on chunks discarded before a send, so a device that
    # streams notifications cannot stall a request. (Same cap as upstream.)
    _MAX_STALE_CHUNKS = 64

    def __init__(self, mac, channel=2, timeout=8.0):
        """
        Args:
            mac: Device address, e.g. ``"AA:BB:CC:DD:EE:FF"``. Any common
                separator (colon, dash, dot, none) is accepted.
            channel: RFCOMM server channel. Bose uses 2 on current models
                and 8 on the QC35 generation.
            timeout: Connect and read timeout, in seconds.
        """
        self.mac = self._normalize_mac(mac)
        self.channel = int(channel)
        self.timeout = float(timeout)
        self._sock = None
        self._wsa = None

    # ── address helpers ──

    @staticmethod
    def _normalize_mac(mac):
        """Accept any common MAC spelling and return colon-hex uppercase."""
        digits = "".join(c for c in str(mac) if c.isalnum()).upper()
        if len(digits) != 12 or any(c not in "0123456789ABCDEF" for c in digits):
            raise BmapConnectionError(
                "蓝牙地址无效：%r（正确格式 AA:BB:CC:DD:EE:FF）" % (mac,)
            )
        return ":".join(digits[i:i + 2] for i in range(0, 12, 2))

    @staticmethod
    def _mac_to_btaddr(mac):
        """Pack a MAC into the 64-bit BTH_ADDR Windows expects.

        Winsock stores the address little-endian, so the byte order of the
        printed MAC is reversed.
        """
        parts = mac.split(":")
        return int("".join(reversed(parts)), 16)

    # ── socket plumbing ──

    def _ensure_wsa(self):
        if self._wsa is None:
            if _WSA is None:
                raise BmapConnectionError(
                    "无法加载 Windows 蓝牙组件 ws2_32.dll（仅支持 Windows）"
                )
            self._wsa = _WSA
            # WSAStartup(MAKEWORD(2,2), &wsaData). The stack must be up
            # before socket() is called, and it is ref-counted per call.
            wsa_data = ctypes.create_string_buffer(408)
            rc = self._wsa.WSAStartup(0x0202, wsa_data)
            if rc != 0:
                self._wsa = None
                raise BmapConnectionError(
                    "无法初始化 Windows 蓝牙协议栈 (WSAStartup=%d)" % rc
                )
        return self._wsa

    def _last_error(self):
        return self._wsa.WSAGetLastError()

    def _set_bytes_timeouts(self, sock, seconds):
        """Apply read/write timeouts. Windows takes a millisecond DWORD."""
        ms = ctypes.c_int(max(1, int(seconds * 1000)))
        self._wsa.setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
                             ctypes.cast(ctypes.byref(ms), ctypes.c_char_p), 4)
        self._wsa.setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO,
                             ctypes.cast(ctypes.byref(ms), ctypes.c_char_p), 4)

    def _set_blocking(self, sock, blocking):
        mode = ctypes.c_ulong(0 if blocking else 1)
        self._wsa.ioctlsocket(sock, FIONBIO, ctypes.byref(mode))

    def _wait_writable(self, sock, seconds):
        """Block until ``sock`` is writable (or errored). True on activity."""
        wset = _fd_set()
        wset.fd_count = 1
        wset.fd_array[0] = sock
        tv = _timeval(int(seconds), int((seconds - int(seconds)) * 1_000_000))
        rc = self._wsa.select(0, None, ctypes.byref(wset), None, ctypes.byref(tv))
        return rc > 0

    def _so_error(self, sock):
        val = ctypes.c_int(0)
        size = ctypes.c_int(ctypes.sizeof(val))
        self._wsa.getsockopt(sock, SOL_SOCKET, SO_ERROR,
                             ctypes.cast(ctypes.byref(val), ctypes.c_char_p),
                             ctypes.byref(size))
        return val.value

    # ── Transport API ──

    def connect(self):
        wsa = self._ensure_wsa()

        sock = wsa.socket(AF_BTH, SOCK_STREAM, BTHPROTO_RFCOMM)
        if sock == 0 or sock == ctypes.c_uint64(-1).value:
            code = self._last_error()
            self._raise_connect_error(code)
        self._sock = sock

        try:
            self._set_bytes_timeouts(sock, self.timeout)

            addr = SOCKADDR_BTH()
            addr.addressFamily = AF_BTH
            addr.btAddr = self._mac_to_btaddr(self.mac)
            # A zero service GUID means "connect by RFCOMM channel number".
            ctypes.memset(ctypes.byref(addr.serviceClassId), 0, ctypes.sizeof(GUID))
            addr.port = self.channel

            # Non-blocking connect, bounded by select(): a blocking RFCOMM
            # connect ignores SO_SNDTIMEO and can hang for ~30s on a
            # powered-off headset.
            self._set_blocking(sock, False)
            rc = wsa.connect(sock, ctypes.byref(addr),
                             ctypes.sizeof(SOCKADDR_BTH))
            if rc == SOCKET_ERROR:
                code = self._last_error()
                if code not in (WSAEWOULDBLOCK, WSAEINPROGRESS):
                    self._raise_connect_error(code)
                if not self._wait_writable(sock, self.timeout):
                    self._raise_connect_error(WSAETIMEDOUT)
                code = self._so_error(sock)
                if code != 0:
                    self._raise_connect_error(code)
            self._set_blocking(sock, True)
        except BmapConnectionError:
            self.close()
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self.close()
            raise BmapConnectionError("蓝牙连接失败：%s" % exc) from exc

        return self

    def _raise_connect_error(self, code):
        """Translate a Winsock code into a typed, actionable exception."""
        err = _WSA_TO_ERRNO.get(code)
        if err == errno.EBUSY:
            # BmapBusyError is what the channel prober treats as "device is
            # there, wait a moment" rather than "wrong channel".
            raise BmapConnectionError(
                "%s（通道 %d）" % (describe_wsa_error(code), self.channel),
                errno=errno.EBUSY,
            )
        raise BmapConnectionError(
            "连接 %s 通道 %d 失败：%s" % (self.mac, self.channel,
                                        describe_wsa_error(code)),
            errno=err,
        )

    def _discard_pending(self):
        """Drop bytes already waiting before a new request.

        Late replies and unsolicited STATUS notifications would otherwise be
        read as the answer to the next request. Mirrors upstream.
        """
        if self._sock is None:
            return
        try:
            self._set_blocking(self._sock, False)
            buf = ctypes.create_string_buffer(4096)
            for _ in range(self._MAX_STALE_CHUNKS):
                n = self._wsa.recv(self._sock, buf, 4096, 0)
                if n <= 0:
                    break
        except Exception:
            pass  # a dead socket fails the send with a clear error
        finally:
            try:
                self._set_blocking(self._sock, True)
            except Exception:
                pass

    def send_recv(self, packet, drain=False):
        if not self.is_connected:
            raise BmapConnectionError("尚未连接到设备")
        wsa = self._ensure_wsa()
        sock = self._sock

        self._discard_pending()

        sent = wsa.send(sock, bytes(packet), len(packet), 0)
        if sent <= 0:
            code = self._last_error()
            raise BmapConnectionError(
                "向设备发送数据失败：%s" % describe_wsa_error(code),
                errno=_WSA_TO_ERRNO.get(code),
            )

        # Bose firmware ignores a request that arrives before it has
        # finished booting its RFCOMM listener; a short settle keeps the
        # first read from racing the reply. (Matches upstream's 0.2s.)
        time.sleep(0.2)

        buf = ctypes.create_string_buffer(4096)
        n = wsa.recv(sock, buf, 4096, 0)
        if n == SOCKET_ERROR:
            code = self._last_error()
            if code == WSAETIMEDOUT:
                raise BmapTimeoutError("设备无响应（超时）")
            raise BmapConnectionError(
                "读取设备数据失败：%s" % describe_wsa_error(code),
                errno=_WSA_TO_ERRNO.get(code),
            )
        if n == 0:
            raise BmapConnectionError("连接已被设备关闭")
        data = buf.raw[:n]

        if drain:
            # 0.5s of silence marks the end of a START stream.
            self._set_bytes_timeouts(sock, 0.5)
            try:
                while True:
                    n = wsa.recv(sock, buf, 4096, 0)
                    if n <= 0:
                        break
                    data += buf.raw[:n]
            except Exception:
                pass
            finally:
                self._set_bytes_timeouts(sock, self.timeout)

        return data

    def close(self):
        if self._sock is not None:
            try:
                self._ensure_wsa().closesocket(self._sock)
            except Exception:
                pass
            self._sock = None
        if self._wsa is not None:
            try:
                self._wsa.WSACleanup()
            except Exception:
                pass
            self._wsa = None

    @property
    def is_connected(self):
        return self._sock is not None


# ── Optional PyBluez backend ──────────────────────────────────────────────────

class PyBluezTransport(Transport):
    """RFCOMM transport on top of the ``pybluez`` package, when present.

    Kept for parity with upstream and as an escape hatch: PyBluez has no
    wheels for current Python versions, so the ctypes transport above is the
    default on Windows. Install with ``pip install pybluez`` only if you
    already have a working build environment.
    """

    def __init__(self, mac, channel=2, timeout=8.0):
        self.mac = mac
        self.channel = int(channel)
        self.timeout = float(timeout)
        self._sock = None

    @staticmethod
    def _import_bluetooth():
        try:
            import bluetooth  # type: ignore
            return bluetooth
        except ImportError as exc:
            raise BmapConnectionError(
                "未安装 pybluez。Windows 版默认使用内置蓝牙实现，"
                "无需安装该库；如需使用请先 pip install pybluez。"
            ) from exc

    def connect(self):
        bluetooth = self._import_bluetooth()
        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.mac, self.channel))
        except Exception as exc:
            raise BmapConnectionError(
                "pybluez 连接 %s 失败：%s" % (self.mac, exc),
                errno=getattr(exc, "errno", None),
            ) from exc
        self._sock = sock
        return self

    def send_recv(self, packet, drain=False):
        if not self.is_connected:
            raise BmapConnectionError("尚未连接到设备")
        self._sock.settimeout(self.timeout)
        self._sock.send(bytes(packet))
        time.sleep(0.2)
        try:
            data = self._sock.recv(4096)
        except socket.timeout:
            raise BmapTimeoutError("设备无响应（超时）")
        if not data:
            raise BmapConnectionError("连接已被设备关闭")
        if drain:
            self._sock.settimeout(0.5)
            try:
                while True:
                    more = self._sock.recv(4096)
                    if not more:
                        break
                    data += more
            except (socket.timeout, BlockingIOError):
                pass
            finally:
                self._sock.settimeout(self.timeout)
        return data

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    @property
    def is_connected(self):
        return self._sock is not None


# ── Factory ───────────────────────────────────────────────────────────────────

#: Backends accepted by :func:`create_transport`.
TRANSPORT_BACKENDS = ("auto", "windows", "pybluez", "mock")


def create_transport(mac, channel=2, backend="auto", timeout=8.0):
    """Build the best available transport for this machine.

    Args:
        mac: Device Bluetooth MAC address.
        channel: RFCOMM channel.
        backend: ``"auto"`` (default), ``"windows"``, ``"pybluez"`` or
            ``"mock"``.
        timeout: Connect/read timeout in seconds.

    Returns:
        A :class:`Transport` instance, not yet connected.
    """
    if backend == "mock":
        from .mock import MockTransport
        return MockTransport(mac=mac, channel=channel)

    if backend == "pybluez":
        return PyBluezTransport(mac, channel, timeout)

    if backend in ("auto", "windows"):
        if not is_windows:
            raise BmapNotFoundError(
                "本构建仅支持 Windows 蓝牙栈；当前平台为 %s。"
                "在 Linux/macOS 上请使用上游 bosectl。" % platform.system()
            )
        return WindowsRfcommTransport(mac, channel, timeout)

    raise BmapNotFoundError(
        "未知的蓝牙后端 %r，可选：%s" % (backend, ", ".join(TRANSPORT_BACKENDS))
    )


# ``RfcommTransport`` is the name the rest of the library (and upstream)
# uses; on Windows it resolves to the Winsock implementation.
RfcommTransport = WindowsRfcommTransport if is_windows else PyBluezTransport
