# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

The release workflow extracts the section matching the pushed tag to build
the GitHub Release notes, so each released version needs a `## [x.y.z]`
heading here.

## [1.0.0] - 2026-10-01

First Windows release. Based on upstream bosectl 0.5.0.

### Added

- **Windows RFCOMM transport** (`pybmap/transport.py`). A dependency-free
  `ctypes` binding to Winsock's Bluetooth extensions (`AF_BTH`,
  `BTHPROTO_RFCOMM`). No PyBluez, no native extension, no build step.
  - Non-blocking connect bounded by `select()`, because a blocking RFCOMM
    connect ignores `SO_SNDTIMEO` and can hang for ~30 s on a powered-off
    headset.
  - Winsock `WSA*` codes are translated to the matching `errno` values, so
    the channel-probing and busy-retry logic above it behaves exactly as it
    does on Linux.
  - Pre-request drain of stale bytes, mirroring upstream, so a late reply
    cannot be read as the answer to the next request.
- **Windows device discovery** (`pybmap/discovery.py`). Replaces
  `bluetoothctl`:
  - paired devices from `HKLM\SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices`
    (no elevation needed, works inside a frozen EXE);
  - live connected/authenticated state from `bluetoothapis.dll`;
  - the Bose product ID from SetupAPI PnP hardware IDs — the Windows
    equivalent of Linux's Modalias, and what makes model auto-detection
    work;
  - optional WinRT enumeration when the projections are installed.
- **Desktop application** (`gui/`). CustomTkinter front end with a Windows 11
  layout: in-window header, navigation rail, status bar, per-monitor DPI
  awareness, taskbar identity, light/dark following the Windows setting, and
  a persisted window geometry. Six pages: 连接, 声音, 模式, 设备, 高级, 关于.
- **Demo mode.** An in-memory simulated headset drives the entire UI, so the
  app is explorable with no hardware and CI can exercise it end to end.
- **All device I/O on one background thread** (`gui/worker.py`). The Tk loop
  never blocks and requests are serialised, so dragging a slider cannot
  corrupt the reply to a concurrent read.
- **Windows console entry point** (`cli.py`): enables ANSI colours (which
  Windows consoles need an explicit opt-in for), localised `--help`,
  `--diagnose`, `--mac/--device/--timeout` flags mapped onto the environment
  variables upstream already reads, and Chinese summaries for failures.
- **Chinese error localisation** (`pybmap/messages.py`). The library's
  exception text stays byte-for-byte upstream English; translation happens
  one layer up, and the original line is always preserved underneath.
- **Packaging** (`build/`): PyInstaller specs for a windowed `BoseCtl.exe`
  and a console `bosectl-cli.exe`, generated icon, Windows version resource, and
  a version-consistency checker.
- **CI/CD** (`.github/workflows/`): test matrix (Windows 3.9-3.13, plus
  Linux and macOS for the library half), a build workflow that packages and
  smoke-tests both executables, and a release workflow triggered by a tag
  that validates the version, builds, verifies, and publishes.
- **Tests**: upstream's suite runs unmodified, plus suites for the
  transport, discovery, message localisation, packaging layout, and a full
  GUI smoke test that builds the real window against the mock device.

### Changed

- `pybmap/__init__.py` keeps upstream's `connect()` contract and its
  channel-probing logic, with the transport factory and auto-detection
  swapped to the Windows implementations. `connect()` additionally accepts
  `backend`, `mock` and `timeout`, and reads `BMAP_TIMEOUT`.
- The per-model device configurations (`pybmap/devices/`) were restored to
  upstream verbatim. An earlier draft of this port had simplified them,
  which broke the QC35 generation in particular (wrong RFCOMM channel, no
  init packet, missing features).
- One addition to `pybmap/devices/__init__.py`: the two QC35 product IDs
  are registered so the legacy generation is auto-detected. Upstream left
  this as a `TODO`.

### Fixed

- **`WSAEADDRNOTAVAIL` no longer claims the PC has no Bluetooth.** The hint
  for Winsock 10049 read "no Bluetooth adapter available", which sent users to
  check the one thing that was not wrong. It was reported from a laptop with a
  working, connectable radio whose only paired device was a Bluetooth Low
  Energy peripheral — an address that cannot host a classic RFCOMM channel at
  all. The text now names the real causes (powered off, out of range, or only
  paired in LE mode), and a connection error carrying it gets a hint pointing
  at pairing rather than at the radio.
- **`WSAEAUNREACHABLE` was not a Winsock name.** Code 10051 is
  `WSAENETUNREACH`; 10065 (`WSAEHOSTUNREACH`) was missing. The hint for 10051
  now blames the stack, not the device.
- **Devices that are not Bose headphones are labelled as such before you try
  to connect.** The connect page marks the row and says why, and clicking
  connect warns first instead of failing with a message about BMAP
  communication.
- **Case-colliding artefact names.** `BoseCtl.exe` and `bosectl.exe`
  lower-case to the same string, so on Windows and macOS they are one file.
  The checksum-verification job merges both CI artefacts into a single
  directory, so one silently overwrote the other and the sums could not match;
  a user downloading both from the Releases page into one folder would hit the
  same thing. The console build is now `bosectl-cli.exe`. The command set,
  output format and exit codes are unchanged.
- **Case-colliding build spec names.** The two PyInstaller specs were named
  `build/BoseCtl.spec` and `build/bosectl.spec`. Windows and macOS
  filesystems are case-insensitive, so those are the same file: git stored
  one and silently dropped the other. Both packaging jobs therefore ran the
  same spec (and failed together) while `ubuntu-latest` — where the paths
  really are distinct — failed to find the missing one. Renamed to
  `BoseCtl-window.spec` and `bosectl-console.spec`, and
  `tests/test_version.py` now rejects any case-only path collision.
- **Lint gate made deterministic.** Ruff 0.16 reports ~475 findings against
  its default rule set, which has grown between releases. `pyproject.toml`
  now selects an explicit set, and excludes the files vendored verbatim from
  upstream, which are not ours to lint (see `NOTICE`).
- **Specs are now syntax-checked by the test suite.** Nothing else compiles a
  `.spec` file — `compileall` only reads `.py`, and no module imports one — so
  a malformed spec previously survived every local check and only surfaced
  when the packaging job ran.
- **PyInstaller's intermediate files are no longer committed.** The work
  directory follows the spec *file* name, so renaming the specs moved it and
  the `.gitignore` patterns stopped matching. Both jobs now pass
  `--workpath build/work --distpath dist`, leaving one directory to ignore.

### Known limitations

- The QC35 generation has no EQ, no spatial audio and no modes; the UI greys
  out those controls rather than failing on click.
- Operations the firmware gates behind cloud authentication (renaming,
  button remapping on some models) are reported as unsupported. This is
  upstream's constraint, not a port regression: `SETGET` and `START` remain
  unauthenticated and cover the user-facing settings.
- The executables are unsigned, so Windows SmartScreen shows a warning on
  first run.

[1.0.0]: https://github.com/liaoranqing/bosectl-win/releases/tag/v1.0.0
