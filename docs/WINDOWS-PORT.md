# Windows port notes

What had to change to move bosectl from Linux/macOS to Windows, why, and what
that means for behaviour. Read this before touching `transport.py` or
`discovery.py`.

## Summary

| Concern | Linux / macOS | Windows | Consequence |
| --- | --- | --- | --- |
| RFCOMM socket | `socket.AF_BLUETOOTH` / IOBluetooth | Winsock `AF_BTH` + `BTHPROTO_RFCOMM`, `SOCKADDR_BTH` | transport rewritten in `ctypes` |
| Device enumeration | `bluetoothctl devices Paired` | `BTHPORT` registry + `bluetoothapis.dll` | discovery rewritten |
| Product ID | `Modalias: bluetooth:v05A7p4082` | SetupAPI PnP hardware ID `VID&000205a7_PID&4082` | model auto-detection rebuilt |
| Connect timeout | `setsockopt(SO_SNDTIMEO)` bounds `connect()` | it does **not** | non-blocking connect + `select()` |
| Socket timeout format | `struct timeval` | millisecond `DWORD` | different `setsockopt` payload |
| Error codes | `errno` (EBUSY, ECONNREFUSED) | `WSA*` codes | translation table |
| Console colours | `isatty()` is enough | requires enabling virtual-terminal processing | explicit `SetConsoleMode` call |
| DPI | toolkit handles it | process must opt in before the first window | `resources.enable_dpi_awareness()` |
| Taskbar identity | n/a | needed or the app groups under `python.exe` | `SetCurrentProcessExplicitAppUserModelID` |
| GUI toolkit | Qt6 (bosectl-qt) | CustomTkinter (tkinter ships with Python) | new `gui/` |

## 1. Talking to the headphones

Windows exposes Bluetooth to user-mode code only through Winsock's Bluetooth
extensions. There is no `socket.AF_BLUETOOTH`. A connection is a normal stream
socket in the `AF_BTH` family with a `SOCKADDR_BTH` describing the peer:

```c
struct sockaddr_bth {
    USHORT addressFamily;    /* AF_BTH = 32 */
    /* 6 bytes padding */
    BTH_ADDR btAddr;         /* 64-bit, byte order reversed */
    GUID serviceClassId;     /* zero => address by channel */
    ULONG port;              /* RFCOMM channel */
};
```

Three details bite:

1. **Struct size.** `btAddr` is 8-byte aligned, so the struct is 40 bytes on
   both x86 and x64. `tests/test_transport_windows.py` pins this, because
   getting it wrong passes a bad pointer and fails in a way that looks like
   "device not found".
2. **Address byte order.** Windows stores the address little-endian, so the
   printed MAC is reversed: `68:F2:1F:0D:F5:11` packs to `0x11F50D1FF268`.
3. **`SOCKET` is `UINT_PTR`.** ctypes defaults a function's return type to
   `c_int`, which truncates a 64-bit handle on x64. Every Winsock prototype in
   `transport.py` sets `argtypes`/`restype` explicitly.

There is an optional PyBluez backend for parity, but PyBluez has no wheels for
current Python versions, so the `ctypes` implementation is the default and the
only one required.

### The connect timeout

On Linux, `SO_SNDTIMEO` bounds a blocking `connect()`. On Windows it does not.
A blocking RFCOMM connect to a powered-off headset can sit for the full driver
timeout (tens of seconds), and the app would appear hung.

The port therefore:

1. sets the socket non-blocking (`ioctlsocket(FIONBIO)`);
2. calls `connect()`, expecting `WSAEWOULDBLOCK`;
3. waits for writability with `select()` bounded by the configured timeout;
4. reads the real result from `getsockopt(SO_ERROR)`;
5. restores blocking mode and applies read/write timeouts.

Note that Windows takes read/write timeouts as a millisecond `DWORD`, not a
`struct timeval` — passing a timeval silently gives you a timeout of a few
microseconds' worth of milliseconds.

### Error codes feed the retry logic

Upstream's channel prober (`_open_transport` in `pybmap/__init__.py`) retries
`EBUSY` and, on the configured channel, `ECONNREFUSED`. Those are POSIX values;
Windows reports `WSAEBUSY` (10016), `WSAEADDRINUSE` (10048),
`WSAECONNREFUSED` (10061) and so on. `transport._WSA_TO_ERRNO` maps them, and
`BmapConnectionError.errno` carries the translated value. Because of that one
table, upstream's retry and backoff behaviour works unchanged — which is why
`tests/test_channel_probe.py` (written for Linux) passes on Windows.

## 2. Finding the headphones

Upstream reads `bluetoothctl`, which conveniently reports each device's
`Modalias` — and the product ID in it selects the device config. Windows has no
single equivalent, so the answers are assembled from three sources.

### Paired devices: the registry

`HKLM\SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices` has one
subkey per paired device. The key name is the address with bytes reversed; a
`Name` REG_SZ (or REG_BINARY, on some builds) holds the friendly name. This
needs no elevation, no WinRT, and works inside a frozen EXE — which is why it is
the primary source rather than an optional one.

### Connection state: `bluetoothapis.dll`

`BluetoothFindFirstDevice` / `BluetoothFindNextDevice` walk a
`BLUETOOTH_DEVICE_SEARCH_PARAMS` and fill `BLUETOOTH_DEVICE_INFO`, which adds
`fConnected`, `fAuthenticated` and `fRemembered` — state the registry does not
carry. Two traps: the struct's `Address` is a union whose 64-bit member must be
reversed again, and `szName` is a fixed 248-wide-char array, not a pointer.
Errors return a null handle rather than raising.

### Product ID: SetupAPI

This is the Modalias equivalent and the only reliable way to pick the right
device config. Each Bluetooth PnP device has hardware IDs like:

```
BTHENUM\{0000110b-0000-1000-8000-00805f9b34fb}_VID&000205a7_PID&4082
```

`VID&000205a7` is Bose's USB vendor ID; `PID&4082` is the product ID — the same
number `catalog.py` keys on. The address comes from the device instance ID,
whose tail looks like:

```
...\7&1a2b3c4d&0&68F21F0DF511_C00000000
```

**The GUID trap.** An unanchored search for 12 hex digits finds
`00805f9b34fb` inside the service-class GUID first, which decodes to the
well-formed but completely wrong `00:80:5F:9B:34:FB`. The extraction patterns
are anchored on `&0&` and `Dev_` for exactly this reason, and there is a test
for it.

### Graceful degradation

Sources are merged by address, preferring live state and filling in missing
names. Any source can fail — a locked-down machine may deny registry access, a
non-Windows platform gets nothing — and each is wrapped so failure yields an
empty list instead of an exception. The GUI then falls back to manual address
entry plus an explicit model dropdown, which is always available and always
correct.

### Model auto-detection order

1. product ID → `catalog.lookup_device()` → config key (authoritative);
2. name heuristics (`suggest_device_type`), which handle "QC Ultra 2",
   "QuietComfort 45", "QC35 II", the `LE-` mirror prefix, and so on;
3. manual selection in the UI / `--device` on the CLI.

## 3. Making it feel native

**DPI.** Without an explicit call, Windows bitmap-scales the window on a
125%/150% display and every glyph is blurry. The opt-in must happen before Tk
creates its first window. `resources.enable_dpi_awareness()` defers to
customtkinter's own `ScalingTracker` when available, so the two components do
not disagree about the process DPI mode, and falls back to Win32
(`SetProcessDpiAwareness`/`SetProcessDPIAware`).

Window geometry is stored in the same logical units customtkinter scales, so
`_restore_geometry` divides the physical screen size by the scaling factor
before clamping.

**Taskbar identity.** A frozen EXE otherwise groups under `python.exe` and keeps
a generic Python icon; pinning does not work either.
`SetCurrentProcessExplicitAppUserModelID` fixes both.

**Console colours.** `cli._enable_virtual_terminal()` calls `SetConsoleMode`
with `ENABLE_VIRTUAL_TERMINAL_PROCESSING` on stdout and stderr. Without it a
Windows console reports `isatty() == False` to the upstream CLI and the gradient
banner comes out as escape-code soup.

**Encoding.** The console code page may be cp936; `cli._configure_console()`
reconfigures stdout/stderr to UTF-8 (falling back to wrapping the raw buffer) so
Chinese output is not mangled.

## 4. Communication and error reporting

**One thread for all device I/O.** The channel carries one request at a time.
`gui/worker.py` serialises operations on a single thread and delivers results
through a queue drained by a main-thread poller — `widget.after` called from a
worker thread can silently never fire, so the queue-plus-poller pattern is the
only portable option.

**Errors stay upstream, text changes one layer up.** Library messages are
byte-for-byte upstream, because `bosectl-qt` and upstream's tests match on
substrings. `pybmap/messages.py` translates for display and always appends the
original line, so a bug report still contains the technical detail (address,
probed channel list, `WSA` code). `tests/test_messages.py` verifies each table
entry against the source tree, so the table cannot rot into unreachable typos.

**Windows-specific diagnostics.** `pybmap.diagnose()` reports the radio, paired
and enumerated counts, how many devices were recognised as Bose, and whether
product IDs could be read. It is surfaced as 高级 → Windows 蓝牙环境自检 in the
GUI and `bosectl-cli.exe --diagnose` on the CLI. When a connection fails below the
protocol layer, this is the fastest way to tell whether the problem is the
radio, the pairing, or the model config.

## 5. A trap that only shows up in CI: case-insensitive paths

Windows and macOS filesystems treat `build/BoseCtl.spec` and
`build/bosectl.spec` as *the same file*. Git can therefore only store one of
them; the other is silently absent from the checkout. On Windows everything
looks fine — the single file answers to both names — while Linux, where the
paths really are distinct, fails to find one.

This repository shipped exactly that bug: the two PyInstaller specs were named
`BoseCtl.spec` and `bosectl.spec`. Both packaging jobs ran the same spec (and
failed together), and the test suite went red on `ubuntu-latest` only, while
Windows and macOS stayed green. The fix was to name them
`BoseCtl-window.spec` and `bosectl-console.spec`, and the class of bug is now
rejected by `tests/test_version.py::test_no_tracked_paths_collide_by_letter_case`.

The wider lesson for a Windows-first repository: anything that compares or
keys on paths must assume case-insensitivity, and any test that asserts a file
exists should be run on Linux once, because that is the only place a
case-collision becomes visible as a missing file.

## 6. Installing and running

**No runtime dependencies for the library.** The BMAP layer needs only the
standard library: `ctypes` reaches both Winsock and `bluetoothapis.dll`. There
is no native build step, no PyBluez, nothing to compile.

**Two executables.** Windows fixes console-vs-windowed at link time, so one
binary cannot serve both cleanly. `BoseCtl.exe` is windowed (no console flash on
launch); `bosectl-cli.exe` is a console binary. Splitting them also lets the CLI
build exclude tkinter/customtkinter/Pillow entirely.

**One-file packaging.** Portable and install-free, at the cost of a 2-3 s
first-launch unpack. `docs/BUILD.md` describes the one-line change to get a
directory build with an instant start instead.

**Unsigned binaries.** SmartScreen will warn on first run. Signing requires a
certificate; the build workflow has a documented insertion point for
`signtool` if you have one.

## 7. Behaviour differences from upstream

| Area | Difference |
| --- | --- |
| Auto-detection channel | Linux reads Modalias; Windows reads PnP hardware IDs. Both are authoritative, but a device that exposes neither falls back to name heuristics. |
| Channel probing | Identical, including the EBUSY retry schedule. Verified by upstream's own `test_channel_probe.py`. |
| QR35 product IDs | Registered in `devices/__init__.py` (upstream left it as a `TODO`); the values come from `catalog.py`, which already had them. |
| `connect()` extras | Optional `backend`, `mock` and `timeout` parameters. Upstream's two-argument form behaves identically. |
| Error message language | GUI and CLI print Chinese summaries; the library text is unchanged. |
| CLI help | `--help` is the Chinese cheat sheet; `--help-raw` is upstream's. |

## 8. Things that are deliberately *not* different

- The BMAP codec, constants, error taxonomy and device configs: copied
  verbatim.
- The channel-probing and EBUSY backoff algorithm.
- `BmapConnection`'s public API and exception types.
- The CLI's command set, output format and exit codes.
- Stale-byte draining before each request.

`NOTICE` lists each of these file by file, and `docs/ARCHITECTURE.md` explains
why paraphrasing hardware behaviour is the one thing you must never do here: a
rewritten device config still looks plausible and still passes unit tests while
failing on every real headset.
