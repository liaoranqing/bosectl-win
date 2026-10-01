# Usage

## Before anything: pair the headphones

1. Windows **设置 → 蓝牙和其他设备 → 添加设备**, pick your Bose headphones, wait
   until Windows shows **已连接**.
2. **Close the Bose app on your phone.** The headset's BMAP channel accepts one
   connection at a time. If a phone holds it, this tool reports "设备正忙" no
   matter how many times you retry.
3. If you have several Bluetooth adapters, make sure the headphones are paired
   to the one you intend to use.

## Desktop application

Double-click `BoseCtl.exe`. First launch shows the **连接** page.

### Connecting

- **演示模式** — drive the full interface against an in-memory simulated
  headset. Nothing is sent to hardware, so every control is safe to explore.
  Use it to see what the UI does before pairing anything.
- **已配对的蓝牙设备** — the app enumerates paired devices, marks Bose ones with
  ★, and shows the detected model. Click 连接 on the row you want.
- **手动连接** — for when detection fails: pick the model from the dropdown and
  type the address. Find it in Windows 设置 → 蓝牙和其他设备 → your headphones,
  or run `bosectl-cli.exe --diagnose`.
- **启动时自动连接** — reconnect to the remembered device on launch.

### The six pages

| Page | What it does |
| --- | --- |
| **连接** | device picking, manual entry, connection timeout, demo mode, pairing help |
| **声音** | CNC level (0 = strongest cancellation), ANC on/off, wind block, spatial audio, three-band EQ |
| **模式** | the four presets, custom profile create/update/delete, all slots listed |
| **设备** | device name, multipoint, auto-pause, auto-answer, voice prompts and language, button mapping |
| **高级** | audio source and routing, pairing mode, power off, mode dump, environment self-check, raw BMAP console, battery detail |
| **关于** | supported models, versions, attribution |

### Keyboard

| Key | Action |
| --- | --- |
| `F5` / `Ctrl+R` | re-read device status |
| `Ctrl+1` … `Ctrl+6` | jump to a page |
| `Ctrl+Q` | quit |

### Two things worth knowing

**Controls that do not apply are disabled, not broken.** The app reads the
connected model's capability map once. A QC35 has no EQ, no spatial audio and no
modes, so those controls are greyed out instead of failing when clicked. The
same applies to the ANC toggle on models whose cancellation is tied to the
selected mode.

**Writes are queued, not raced.** All device I/O runs on one background thread.
Dragging the EQ slider quickly produces a sequence of writes rather than
interleaved requests — interleaving them desynchronises the headset's reply
stream, which is the failure mode `BmapDesyncError` reports.

### Saved settings

`%APPDATA%\bosectl-win\settings.json` — last device, window geometry, theme,
timeout, auto-connect. Delete the file to reset. It is written atomically, so a
crash cannot leave it truncated.

## Command line

Run `bosectl-cli.exe --help` for the localised cheat sheet, or `--help-raw` for
upstream's original English one.

The binary carries a `-cli` suffix because `BoseCtl.exe` and `bosectl.exe`
lower-case to the same file name, and two files that differ only by case cannot
be downloaded into the same folder on Windows or macOS. The command set, output
format and exit codes are unchanged from upstream, and every example below works
verbatim with `bosectl-cli.exe` substituted for `bosectl`.

### Environment variables (upstream-compatible)

| Variable | Effect |
| --- | --- |
| `BOSE_MAC` / `BMAP_MAC` | device address |
| `BMAP_DEVICE` | model key (`qc_ultra2`, `qc35`, …) — required with an explicit address |
| `BMAP_TIMEOUT` | per-channel connect timeout in seconds |
| `BMAP_MOCK` | `1` uses the simulated device |

### Wrapper flags

```
-m, --mac AA:BB:CC:DD:EE:FF     device address
-d, --device <model>            model key
-t, --timeout <seconds>         connect timeout
    --mock / --demo             simulated device
    --diagnose                  Windows Bluetooth environment report
    --version                   version information
-h, --help                      Chinese help
    --help-raw                  upstream English help
```

### Examples

```bash
bosectl-cli.exe --diagnose                      # start here when something fails
bosectl-cli.exe --mock status                   # try it with no hardware

bosectl-cli.exe status                          # full state
bosectl-cli.exe battery                         # just the number
bosectl-cli.exe cnc 8                           # 0 = max ANC, 10 = most ambient
bosectl-cli.exe anr high                        # QC35 generation only
bosectl-cli.exe anc on
bosectl-cli.exe wind off
bosectl-cli.exe eq 3 0 -2                       # bass / mid / treble, -10..+10
bosectl-cli.exe eq flat
bosectl-cli.exe spatial head                    # off | room | head
bosectl-cli.exe name "My QC Ultra"

bosectl-cli.exe profiles                        # list every profile
bosectl-cli.exe switch quiet
bosectl-cli.exe profile set 通勤 cnc=8 spatial=off wind=on anc=on
bosectl-cli.exe profile rm 通勤

bosectl-cli.exe multipoint on
bosectl-cli.exe autopause on
bosectl-cli.exe autoanswer off
bosectl-cli.exe prompts on
bosectl-cli.exe sidetone medium

bosectl-cli.exe source                          # where audio is coming from
bosectl-cli.exe route AA:BB:CC:DD:EE:FF         # hand audio to another device
bosectl-cli.exe pair                            # enter pairing mode
bosectl-cli.exe off                             # power the headphones down

bosectl-cli.exe buttons                         # show the mapping
bosectl-cli.exe buttons set ANC                 # remap
bosectl-cli.exe dump                            # every mode slot
bosectl-cli.exe raw 1f 01 05 00                 # raw BMAP frame
```

### Reading errors

The library's messages are upstream's English, deliberately — callers and
upstream's tests match on them. On failure the wrapper prints the original line
and then a Chinese summary, prefixed with `中文提示：`:

```
Connection failed: No BMAP channel found on 68:F2:1F:0D:F5:11 (tried 2, 8, 9): ...
中文提示：
无法与设备建立 BMAP 通信。请确认：蓝牙已开启、耳机已配对并开机，且没有被手机等其他设备占用连接。
原始信息：No BMAP channel found on ...
```

Diagnostics go to stderr, so `bosectl-cli.exe --mock battery` still pipes cleanly as
a number on stdout.

## Python API

The library is importable and unchanged from upstream:

```python
import pybmap

with pybmap.connect() as dev:                  # auto-detects a paired device
    print(dev.battery())
    dev.set_cnc(8)
    dev.set_eq(3, 0, -2)
    dev.set_mode("quiet")
    for idx, mode in sorted(dev.modes().items()):
        print(idx, mode.name, mode.cnc_level, "editable" if mode.editable else "preset")

with pybmap.connect(mac="68:F2:1F:0D:F5:11", device_type="qc_ultra2") as dev:
    print(dev.status())

with pybmap.connect(mock=True) as dev:         # no hardware
    print(dev.status())

# Windows-specific helpers
print(pybmap.diagnose())                       # environment report
print(pybmap.discover(True))                   # paired devices, with product IDs
print(pybmap.suggest_device_type("Bose QC Ultra 2"))
print(pybmap.detect_device_type(0x4082))
```

## Troubleshooting

Start with `bosectl-cli.exe --diagnose`. It reports whether a Bluetooth radio is
present, how many devices are paired, how many are recognised as Bose, and
whether product IDs could be read — which tells you immediately whether the
problem is below or above the protocol layer.

| Symptom | Meaning and fix |
| --- | --- |
| 设备正忙 | The previous link has not been released, or a phone holds the channel. Wait ~5 s; disconnect the headphones from the phone. |
| 设备拒绝连接 | Not paired, powered off, or out of range. Confirm 已连接 in Windows settings. |
| 连接超时 | The headset is asleep. Trigger it once, or raise 连接超时 to 12/20 s. |
| 未找到已配对的 Bose 设备 | Not paired, or the name contains nothing identifying. Use 手动连接. |
| Empty scan list | `--diagnose`. Check the radio and pairing state. |
| Works, then stops after a while | The headset dropped the link (idle timeout or another device took it). Reconnect; `BmapDesyncError` means a reconnect is genuinely required rather than a retry. |
| No EQ / spatial controls | Hardware limitation (e.g. QC35 generation). Controls are disabled by design. |
| 需要 Bose 云端鉴权 | The operation (rename, some button remaps) is gated behind cloud auth in the firmware. Everyday settings work. |
| "设备返回了错误" | The register is not writable on this firmware. Try the equivalent in the Bose app once to confirm it works there, then report it. |

When filing an issue, include `bosectl-cli.exe --diagnose`, your headset model and
firmware version (shown in `status`), and the exact failing command.
