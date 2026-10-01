"""Simulated BMAP device for hardware-free testing and demo mode.

:class:`MockTransport` behaves like a real Bose headset at the byte level:
it parses incoming BMAP packets and emits valid responses, so the full
connection layer, parsers, and GUI are exercised end-to-end without any
Bluetooth hardware. It models the QuietComfort Ultra Headphones 2nd Gen
(``qc_ultra2``) address map.

This is genuinely useful beyond tests: the GUI's "Demo Mode" runs against
it so users can explore every feature before pairing a real device.
"""

import time

from .constants import OP_GET, OP_SETGET, OP_START, OP_STATUS, OP_RESULT, OP_ERROR
from .protocol import parse_all_responses, bmap_packet
from .transport import Transport

# qc_ultra2 address map (mirrors devices/qc_ultra2.py).
ADDR = {
    "battery": (2, 2),
    "firmware": (0, 5),
    "product_name": (1, 2),
    "voice_prompts": (1, 3),
    "cnc": (1, 5),
    "eq": (1, 7),
    "buttons": (1, 9),
    "multipoint": (1, 10),
    "sidetone": (1, 11),
    "auto_pause": (1, 24),
    "auto_answer": (1, 27),
    "get_all_modes": (31, 1),
    "current_mode": (31, 3),
    "mode_config": (31, 6),
    "audio_settings": (31, 10),
}


class MockTransport(Transport):
    """In-memory BMAP device simulator. No I/O performed."""

    def __init__(self, mac="00:00:00:00:00:01", channel=2):
        self._mac = mac
        self._channel = channel
        self.connected = False
        # ── Device state ──
        self._battery = 87
        self._name = "QC Ultra Mock"
        self._firmware = "8.2.20+g34cf029"
        self._prompts_enabled = True
        self._prompts_lang = 1  # US English
        self._cnc = 2            # 0=max ANC .. 10=most ambient
        self._spatial = 0        # 0 off, 1 room, 2 head
        self._wind = True
        self._anc = True
        self._auto_cnc = False
        self._sidetone = 0
        self._multipoint = True
        self._auto_pause = True
        self._auto_answer = False
        self._eq = {0: 0, 1: 0, 2: 0}  # band -> current
        self._current_mode = 0
        # Preset + editable mode slots (idx -> config dict).
        self._modes = {
            0: self._mk_mode(0, "Quiet", cnc=0, spatial=0, wind=False, anc=True, editable=False),
            1: self._mk_mode(1, "Aware", cnc=10, spatial=0, wind=False, anc=True, editable=False),
            2: self._mk_mode(2, "Immersion", cnc=0, spatial=2, wind=False, anc=True, editable=False),
            3: self._mk_mode(3, "Cinema", cnc=0, spatial=1, wind=False, anc=True, editable=False),
            4: self._mk_mode(4, "None", cnc=0, spatial=0, wind=False, anc=True, configured=False, editable=True),
            5: self._mk_mode(5, "None", cnc=0, spatial=0, wind=False, anc=True, configured=False, editable=True),
            6: self._mk_mode(6, "None", cnc=0, spatial=0, wind=False, anc=True, configured=False, editable=True),
            7: self._mk_mode(7, "None", cnc=0, spatial=0, wind=False, anc=True, configured=False, editable=True),
            8: self._mk_mode(8, "None", cnc=0, spatial=0, wind=False, anc=True, configured=False, editable=True),
            9: self._mk_mode(9, "None", cnc=0, spatial=0, wind=False, anc=True, configured=False, editable=True),
            10: self._mk_mode(10, "Jog", cnc=3, spatial=0, wind=True, anc=True, editable=True),
        }
        self._button = {"id": 128, "event": 4, "action": 2}

    @staticmethod
    def _mk_mode(idx, name, cnc=0, spatial=0, wind=False, anc=True,
                 configured=True, editable=True):
        return {
            "idx": idx, "name": name, "cnc": cnc, "spatial": spatial,
            "wind": wind, "anc": anc, "auto_cnc": False,
            "configured": configured, "editable": editable,
            "prompt_b1": 0, "prompt_b2": 0,
        }

    # ── Transport interface ──
    def connect(self):
        time.sleep(0.05)  # mimic a brief handshake
        self.connected = True

    def close(self):
        self.connected = False

    @property
    def is_connected(self):
        return self.connected

    def send_recv(self, data, drain=False, timeout=5.0):
        if not self.connected:
            raise RuntimeError("MockTransport not connected")
        responses = []
        for req in parse_all_responses(data):
            resp = self._handle(req)
            if resp is not None:
                responses.append(resp)
        # Bundle responses into a single byte stream as a device would.
        return b"".join(responses)

    # ── BMAP handling ──
    def _handle(self, req):
        fb, fn, op, payload = req.fblock, req.func, req.op, req.payload
        # Dispatch by (fblock, func)
        key = (fb, fn)
        if key == ADDR["battery"]:
            return self._get(fb, fn, bytes([self._battery]))
        if key == ADDR["firmware"]:
            return self._get(fb, fn, self._firmware.encode("ascii"))
        if key == ADDR["product_name"]:
            return self._get(fb, fn, b"\x00" + self._name.encode("utf-8"))
        if key == ADDR["voice_prompts"]:
            b0 = ((1 if self._prompts_enabled else 0) << 5) | (self._prompts_lang & 0x1F)
            if op == OP_SETGET:
                self._prompts_enabled = bool((payload[0] >> 5) & 1)
                self._prompts_lang = payload[0] & 0x1F
                return self._get(fb, fn, bytes([b0]))
            return self._get(fb, fn, bytes([b0]))
        if key == ADDR["cnc"]:
            # Real devices answer with [max+1, current, auto_cnc]; parse_cnc
            # needs all three bytes, so a short reply would read as 0/10.
            if op == OP_SETGET:
                # Direct [1.5] CNC path used by QC Earbuds: payload [level, on].
                self._cnc = payload[0] & 0x0F
                return self._get(fb, fn, bytes([11, self._cnc,
                                               1 if self._auto_cnc else 0]))
            return self._get(fb, fn, bytes([11, self._cnc,
                                           1 if self._auto_cnc else 0]))
        if key == ADDR["eq"]:
            if op == OP_SETGET:
                # payload [value, band]
                val = payload[0] if payload[0] < 128 else payload[0] - 256
                self._eq[payload[1]] = val
                return self._get(fb, fn, self._eq_payload())
            return self._get(fb, fn, self._eq_payload())
        if key == ADDR["buttons"]:
            return self._get(fb, fn, bytes([self._button["id"], self._button["event"], self._button["action"]]))
        if key == ADDR["multipoint"]:
            b = 0x02 if self._multipoint else 0x00
            if op == OP_SETGET:
                self._multipoint = bool(payload[0] & 0x02)
                return self._get(fb, fn, bytes([b]))
            return self._get(fb, fn, bytes([b]))
        if key == ADDR["sidetone"]:
            if op == OP_SETGET:
                self._sidetone = payload[1] if len(payload) > 1 else payload[0]
                return self._get(fb, fn, bytes([1, self._sidetone]))
            return self._get(fb, fn, bytes([1, self._sidetone]))
        if key == ADDR["auto_pause"]:
            if op == OP_SETGET:
                self._auto_pause = bool(payload[0])
                return self._get(fb, fn, bytes([1 if self._auto_pause else 0]))
            return self._get(fb, fn, bytes([1 if self._auto_pause else 0]))
        if key == ADDR["auto_answer"]:
            if op == OP_SETGET:
                self._auto_answer = bool(payload[0])
                return self._get(fb, fn, bytes([1 if self._auto_answer else 0]))
            return self._get(fb, fn, bytes([1 if self._auto_answer else 0]))
        if key == ADDR["get_all_modes"]:
            # START -> stream all mode configs as STATUS frames.
            out = bytearray()
            for idx in sorted(self._modes):
                out += self._mode_config_status(idx)
            return bytes(out)
        if key == ADDR["current_mode"]:
            if op == OP_GET:
                return self._get(fb, fn, bytes([self._current_mode, 0]))
            if op == OP_START:
                self._current_mode = payload[0]
                return self._status(fb, fn, OP_RESULT, b"")
            return None
        if key == ADDR["mode_config"]:
            if op == OP_GET:
                return self._status(fb, fn, OP_STATUS, self._mode_config_48(self._current_mode))
            if op == OP_SETGET:
                self._apply_mode_config(payload)
                return self._status(fb, fn, OP_STATUS, self._mode_config_48(payload[0]))
            return None
        if key == ADDR["audio_settings"]:
            if op == OP_SETGET:
                self._cnc = payload[0]
                self._auto_cnc = payload[1] != 0
                self._spatial = payload[2]
                self._wind = payload[3] != 0
                self._anc = payload[4] != 0
                return self._status(fb, fn, OP_STATUS, self._audio_settings_payload())
            return self._status(fb, fn, OP_STATUS, self._audio_settings_payload())
        # Unknown address: return a polite error frame.
        return self._status(fb, fn, OP_ERROR, bytes([4]))

    # ── Builders ──
    def _get(self, fb, fn, payload):
        return bmap_packet(fb, fn, OP_GET, payload)

    def _status(self, fb, fn, op, payload):
        return bmap_packet(fb, fn, op, payload)

    def _eq_payload(self):
        out = bytearray()
        for band in (0, 1, 2):
            out += bytes([-10 & 0xFF, 10 & 0xFF, self._eq[band] & 0xFF, band])
        return bytes(out)

    def _audio_settings_payload(self):
        return bytes([
            self._cnc,
            1 if self._auto_cnc else 0,
            self._spatial,
            1 if self._wind else 0,
            1 if self._anc else 0,
        ])

    def _mode_config_48(self, idx):
        m = self._modes[idx]
        buf = bytearray(48)
        buf[0] = idx
        buf[1] = m["prompt_b1"]
        buf[2] = m["prompt_b2"]
        buf[3] = 1 if m["editable"] else 0
        buf[4] = 1 if m["configured"] else 0
        buf[5] = 0
        name = m["name"].encode("utf-8")[:31]
        buf[6:6 + len(name)] = name
        buf[42] = m["cnc"]
        buf[43] = 1 if m["auto_cnc"] else 0
        buf[44] = m["spatial"]
        buf[45] = 1 if m["wind"] else 0
        buf[47] = 1 if m["anc"] else 0
        return bytes(buf)

    def _mode_config_status(self, idx):
        return bmap_packet(31, 6, OP_STATUS, self._mode_config_48(idx))

    def _apply_mode_config(self, payload):
        if len(payload) < 40:
            return
        idx = payload[0]
        name = payload[3:35].split(b"\x00", 1)[0].decode("utf-8", "replace")
        m = self._modes.setdefault(idx, self._mk_mode(idx, name))
        m["name"] = name
        m["cnc"] = payload[35]
        m["auto_cnc"] = bool(payload[36])
        m["spatial"] = payload[37]
        m["wind"] = bool(payload[38])
        m["anc"] = bool(payload[39])
        m["configured"] = True
        m["editable"] = True
