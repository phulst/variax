"""Read the current model's settings from the Variax and decode them.

Uses the read-only requests of the old Linux staging driver
(drivers/staging/line6/variax.c in Linux 2.6.32). They only ask the guitar to
send data and change nothing.

Usage:
  uv run dump.py                   # print the current model's settings
  uv run dump.py --save std.json   # also save them
  uv run dump.py --diff std.json   # show which bytes differ from a saved dump
  uv run dump.py --verbose         # also print the raw MIDI traffic
"""

import argparse
import json
import struct
import sys

from link import VariaxLink

REQUEST_MODEL_1 = bytes.fromhex("F0 00 01 0C 07 00 3C 00 02 00 00 00 00 03 05 03 00 00 00 F7")
REQUEST_MODEL_2 = bytes.fromhex("F0 00 01 0C 07 00 3C 00 02 00 00 00 00 03 07 03 00 00 00 F7")
REQUEST_BANK = bytes.fromhex("F0 00 01 0C 07 00 6D F7")
VARIAX_SYSEX = bytes.fromhex("F0 00 01 0C 07")
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
    replies = []
    for request in (REQUEST_MODEL_1, REQUEST_MODEL_2):
        link.send(request, "model data request")
        msgs = link.listen(2.0, until=lambda m: is_reply(m, 0x3C))
        reply = next((m for m in msgs if is_reply(m, 0x3C)), None)
        if reply is None:
            sys.exit("No model data from the guitar. Is it switched on (1/4\" cable plugged in)?")
        replies.append(decode(reply[MODEL_HEADER_LENGTH:-1]))
    link.send(REQUEST_BANK, "bank name request")
    msgs = link.listen(2.0, until=lambda m: is_reply(m, 0x6D))
    bank = next((m for m in msgs if is_reply(m, 0x6D)), None)
    first, second = replies
    return {
        "name": first[:NAME_LENGTH].decode("ascii", "replace").strip(),
        "bank": bank[7:-1].replace(b"\0", b" ").decode("ascii", "replace").strip() if bank else "",
        "control": (first[NAME_LENGTH:NAME_LENGTH + CONTROL_HALF] + second[:CONTROL_HALF]).hex(),
    }


def print_model(model):
    control = bytes.fromhex(model["control"])
    print("model: %s    bank: %s" % (model["name"], model["bank"]))
    print("\nfields (original Variax layout):")
    for name, offset, kind in FIELDS:
        if kind == "float":
            print("  %3d  %-18s %.4g" % (offset, name, float24(control[offset:offset + 3])))
        else:
            print("  %3d  %-18s %d" % (offset, name, control[offset]))
    print("\nall %d bytes:" % len(control))
    for row in range(0, len(control), 16):
        print("  %3d  %s" % (row, control[row:row + 16].hex(" ")))


def print_diff(old, new):
    a, b = bytes.fromhex(old["control"]), bytes.fromhex(new["control"])
    print("\ndiff against %s / %s:" % (old["name"], old["bank"]))
    changed = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    if not changed:
        print("  no differences")
    for i in changed:
        print("  %3d  %02x -> %02x   (%d -> %d)" % (i, a[i], b[i], a[i], b[i]))


def main():
    parser = argparse.ArgumentParser(description="Read and decode the current Variax model's settings.")
    parser.add_argument("--save", metavar="FILE", help="save the dump as JSON")
    parser.add_argument("--diff", metavar="FILE", help="compare with a saved dump")
    parser.add_argument("--verbose", action="store_true", help="print the raw MIDI traffic")
    args = parser.parse_args()

    with VariaxLink(verbose=args.verbose) as link:
        link.handshake()
        model = read_model(link)

    print_model(model)
    if args.diff:
        with open(args.diff) as f:
            print_diff(json.load(f), model)
    if args.save:
        with open(args.save, "w") as f:
            json.dump(model, f, indent=2)
        print("\nsaved to %s" % args.save)


if __name__ == "__main__":
    main()
