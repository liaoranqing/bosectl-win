# Architecture

## The layers

```
   gui/  ·  cli.py                    presentation
        │
   pybmap.BmapConnection              typed API, per-model dispatch
        │
   pybmap.devices.*                   data: addresses, parsers, builders
        │
   pybmap.transport                   Windows: Winsock AF_BTH RFCOMM
        │
   pybmap.protocol                    BMAP binary codec (no I/O)
        │
   Bluetooth RFCOMM
```

The design is upstream's, and it is worth preserving for one reason: only the
bottom layer is platform-specific. The codec, the device configs and the
connection logic are pure data and pure Python, which is why this port is a
port and not a fork.

### Protocol — `pybmap/protocol.py`

BMAP framing is four bytes plus payload:

```
[fblock_id, function_id, flags, payload_length, ...payload]
```

`flags` packs `(device_id << 6) | (port_num << 4) | (operator & 0x0F)`. The
codec has no device knowledge and no I/O: `bmap_packet()` builds,
`parse_response()` and `parse_all_responses()` decode. A device may answer one
request with several concatenated frames (the "get all modes" START streams one
STATUS per slot), which is why the plural parser exists.

Operators: `SET`(0) requires cloud authentication on most blocks; `GET`(1),
`SETGET`(2), `START`(5) do not. That asymmetry is the whole basis of the
project: it is what makes local control possible without an account.

### Connection — `pybmap/connection.py`

`BmapConnection` composes a transport with a device module and turns
`(fblock, func)` pairs into typed calls:

- `_get(feature)` → `GET`, parse, return;
- `_setget(feature, payload)` → `SETGET`, verify the reply echoes the address;
- `_start(feature, payload=None)` → `START`;
- `_start_drain(feature)` → `START` plus `drain=True` for streaming replies.

Every reply is checked with `_check_reply()`, which raises `BmapDesyncError` if
the response came from a different address than the request. That check is what
catches the classic failure after a reconnect: bytes from before the drop are
still queued, so each read returns the *previous* request's answer and every
subsequent value would be silently wrong.

### Device configs — `pybmap/devices/`

One module per model, pure data:

```python
RFCOMM_CHANNEL = 2
INIT_PACKET = None            # QC35 needs (0, 1) before it answers anything
FEATURES = {
    "cnc":  {"addr": (1, 5), "parser": parsers.parse_cnc, "builder": ...},
    "eq":   {"addr": (1, 7), "parser": parsers.parse_eq,  "builder": ...},
    ...
}
PRESET_MODES = {"quiet": {"idx": 0, "description": "..."}, ...}
MODE_CONFIG_OFFSETS = {...}   # field positions inside the 48-byte mode blob
```

Model differences are expressed as data, not branches. Devices whose payload
layout differs point at different parsers. This is the part that took upstream
the most reverse engineering, and it is carried over verbatim.

### Transport — `pybmap/transport.py`

A thin byte pipe. The contract is small:

```python
connect()
send_recv(packet, drain=False) -> bytes
close()
is_connected
```

`BmapConnection` never touches the OS. On Windows the implementation is a
`ctypes` binding to `ws2_32.dll` using `AF_BTH` / `BTHPROTO_RFCOMM` with a
`SOCKADDR_BTH` carrying the address and the RFCOMM channel. Two Windows
specifics drive the code:

- **Non-blocking connect.** A blocking RFCOMM `connect()` ignores
  `SO_SNDTIMEO`; pointing it at a powered-off headset hangs for the driver
  timeout. The port sets the socket non-blocking, calls `connect()`, waits on
  `select()` for writability bounded by the configured timeout, then reads
  `SO_ERROR`.
- **Error translation.** Winsock reports `WSA*` codes. The channel prober
  above looks for `EBUSY` and `ECONNREFUSED`, so `WSAEBUSY` /
  `WSAEADDRINUSE` map to `EBUSY` and `WSAECONNREFUSED` to `ECONNREFUSED`. One
  mapping table is the entire difference between the Windows and Linux
  retry behaviour.

`send_recv` also drains stale bytes before every request, mirroring upstream.

### Discovery — `pybmap/discovery.py`

Upstream shells out to `bluetoothctl` and reads each device's `Modalias`, which
carries the USB-style VID/PID — i.e. the Bose product ID that selects the right
device config. Windows has no equivalent single source, so three are merged:

| Source | Gives | Why |
| --- | --- | --- |
| `HKLM\...\BTHPORT\Parameters\Devices` | name + address of every paired device | no elevation, works in a frozen EXE |
| `bluetoothapis.dll` (`BluetoothFindFirstDevice`) | live connected / authenticated state | the registry does not carry it |
| SetupAPI (`SetupDiGetClassDevs`) | PnP hardware ID → `VID&000205a7_PID&4082` | the Modalias equivalent; drives model selection |

A fourth, optional source uses the WinRT projections when installed. Each is
wrapped so a failure degrades to the next, and the GUI always offers manual
address entry plus an explicit model dropdown as the final fallback.

Address decoding is the subtle part. `BTHPORT` keys hold the address with its
bytes reversed (`11F50D1FF268` is `68:F2:1F:0D:F5:11`), and a device instance
ID contains a service-class GUID whose own 12-hex run decodes to a
perfectly well-formed but bogus address. The extraction patterns are therefore
anchored (`&0&<addr>`, `Dev_<addr>`), not plain searches.

### Presentation

`gui/` is the desktop app; `cli.py` + `pybmap/cli.py` are the command line.

The GUI's structure is worth noting because it is what makes the app feel
native:

- **One worker thread.** Every BMAP call is a blocking round-trip. `gui/worker.py`
  serialises all device I/O onto a single thread and delivers results through a
  queue drained by a main-thread poller. Three rules follow: never block the UI,
  never overlap requests (overlapping them desynchronises the reply stream),
  never touch Tk from a worker thread (`widget.after` called off-thread can
  silently never fire).
- **Capabilities, not guesses.** `views/base.Capabilities` probes the connected
  device's feature map once. A control the firmware would reject is disabled
  with an explanation instead of failing on click. This is what keeps a QC35
  (ANR only, no EQ, no modes) and an Ultra Open (EQ but no noise control)
  usable through the same UI.
- **Theming through tokens.** `theme.get_theme()` returns a palette of
  `("light", "dark")` tuples, which customtkinter resolves automatically. The
  appearance toggle rebuilds the widget tree in place, keeping the connection.
- **Error text one layer up.** Library messages stay upstream English (callers
  and upstream's tests match on them); `pybmap/messages.py` translates for
  display and always keeps the original line.

## Why the device modules are verbatim

Restoring them was the single most important fix in this port. An earlier draft
had rewritten them as simplified stubs, which produced a QC35 config with
`RFCOMM_CHANNEL = 2` (upstream: 8), no `INIT_PACKET`, and a fraction of the
feature map. That config still *looks* plausible and still passes unit tests,
but on real hardware it connects to the wrong channel or gets no answer at all.

The general lesson: anything that encodes hardware behaviour must be copied,
not paraphrased. `NOTICE` lists every file where that rule applies.

## Testing strategy

| Layer | How it is covered |
| --- | --- |
| Codec, parsers, device configs | upstream's test suite, run unmodified |
| Connection logic, channel probing, retry | upstream's tests, including scripted connect failures |
| Transport | address handling, `SOCKADDR_BTH` layout (pinned to 40 bytes), error mapping, backend selection |
| Discovery | address decoding incl. the GUID trap, product-ID mapping, name heuristics, "never raises" contracts |
| Localisation | every table entry is checked against the source tree, so a pattern cannot rot into a typo |
| Packaging | specs exist, version numbers agree everywhere, workflow files present |
| Application | `tests/test_gui_smoke.py` builds the real window, connects the mock device, visits every page, toggles themes, and round-trips a write |
| Hardware | `pytest --integration` with a paired headset |

The claim being protected is narrow and worth stating: **the layer below the UI
is upstream's code running on upstream's tests, and the UI is exercised against
a real window on every push.**
