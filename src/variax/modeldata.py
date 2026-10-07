"""Read and decode the current model's settings.

Uses the read-only requests of the old Linux staging driver
(drivers/staging/line6/variax.c in Linux 2.6.32), which the JTV still answers:
two reads of the model data (an 18-byte name and 156 bytes of settings, from
the working copy) and one request for the bank name.
"""

import struct

from .interface import VariaxError
from .protocol import VARIAX_SYSEX, read_message

# Two reads of 32 words (the driver's requests are exactly these): words
# 0x353-0x358 hold the name, the rest the settings.
REQUEST_MODEL_1 = read_message(0x353, 32)
REQUEST_MODEL_2 = read_message(0x373, 32)
REQUEST_BANK = bytes.fromhex("F0 00 01 0C 07 00 6D F7")
MODEL_DATA = 0x3C
BANK_NAME = 0x6D
MODEL_HEADER_LENGTH = 7
NAME_LENGTH = 18
CONTROL_HALF = 78

# Field offsets in the model data of the original Variax, from the old driver's
# control.h. The fields up to volume_dump decode sensibly on a JTV; the ones
# after it do not, so the JTV layout differs from there on.
FIELDS = [
    ("body", 3, "byte"), ("pickup1_enable", 4, "byte"), ("pickup1_type", 8, "byte"),
    ("pickup1_position", 9, "float"), ("pickup1_angle", 12, "float"), ("pickup1_level", 15, "float"),
    ("pickup2_enable", 18, "byte"), ("pickup2_type", 22, "byte"), ("pickup2_position", 23, "float"),
    ("pickup2_angle", 26, "float"), ("pickup2_level", 29, "float"), ("pickup_phase", 32, "byte"),
    ("capacitance", 33, "float"), ("tone_resistance", 36, "float"), ("volume_resistance", 39, "float"),
    ("taper", 42, "byte"), ("tone_dump", 43, "float"), ("save_tone", 46, "byte"),
    ("volume_dump", 47, "float"),
]


def is_reply(msg, command):
    return msg.startswith(VARIAX_SYSEX) and len(msg) > 7 and msg[6] == command


def decode(nibbles):
    """Decode the guitar's 4-bit data: each 6 nibbles hold 3 bytes, low nibble first, last byte first."""
    out = bytearray()
    for i in range(0, len(nibbles) - 5, 6):
        n = nibbles[i:i + 6]
        out += bytes([n[4] | n[5] << 4, n[2] | n[3] << 4, n[0] | n[1] << 4])
    return bytes(out)


def float24(data):
    return struct.unpack(">f", data + b"\0")[0]


def read_model(link):
    """Read the current model: {"name", "bank", "control" (hex of the 156 setting bytes)}."""
    replies = []
    for request in (REQUEST_MODEL_1, REQUEST_MODEL_2):
        link.send(request)
        msgs = link.listen(2.0, until=lambda m: is_reply(m, MODEL_DATA))
        reply = next((m for m in msgs if is_reply(m, MODEL_DATA)), None)
        if reply is None:
            raise VariaxError("No model data from the guitar. Is it switched on (1/4\" cable plugged in)?")
        replies.append(decode(reply[MODEL_HEADER_LENGTH:-1]))
    link.send(REQUEST_BANK)
    msgs = link.listen(2.0, until=lambda m: is_reply(m, BANK_NAME))
    bank = next((m for m in msgs if is_reply(m, BANK_NAME)), None)
    first, second = replies
    return {
        "name": first[:NAME_LENGTH].decode("ascii", "replace").strip(),
        "bank": bank[7:-1].replace(b"\0", b" ").decode("ascii", "replace").strip() if bank else "",
        "control": (first[NAME_LENGTH:NAME_LENGTH + CONTROL_HALF] + second[:CONTROL_HALF]).hex(),
    }


def format_model(model):
    control = bytes.fromhex(model["control"])
    lines = ["model: %s    bank: %s" % (model["name"], model["bank"]), "", "fields (original Variax layout):"]
    for name, offset, kind in FIELDS:
        if kind == "float":
            lines.append("  %3d  %-18s %.4g" % (offset, name, float24(control[offset:offset + 3])))
        else:
            lines.append("  %3d  %-18s %d" % (offset, name, control[offset]))
    lines += ["", "all %d bytes:" % len(control)]
    for row in range(0, len(control), 16):
        lines.append("  %3d  %s" % (row, control[row:row + 16].hex(" ")))
    return "\n".join(lines)


def format_diff(old, new):
    a, b = bytes.fromhex(old["control"]), bytes.fromhex(new["control"])
    lines = ["diff against %s / %s:" % (old["name"], old["bank"])]
    changed = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    if not changed:
        lines.append("  no differences")
    for i in changed:
        lines.append("  %3d  %02x -> %02x   (%d -> %d)" % (i, a[i], b[i], a[i], b[i]))
    return "\n".join(lines)
