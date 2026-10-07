"""Send MIDI messages to the James Tyler Variax and print what it sends back.

Usage:
  uv run send.py lester 5              # select a model: bank name + pickup position 1-5
  uv run send.py R-BILLY 3             # bank names as in the Pilot's Guide, any case
  uv run send.py "C0 2C"               # a raw MIDI message, as hex bytes
  uv run send.py volume 100            # volume 0-127 (CC7)
  uv run send.py spank 1 tone 64       # tone 0-127 (CC79); send it after the model,
                                       # because a model change re-applies the tone knob
  uv run send.py spank 1 "B0 07 50"    # several, in order
  uv run send.py --wait 5 lester 5     # listen 5 s after each message (default 2)

Bank names: custom1, t-model, spank, lester, special, r-billy, chime, semi,
jazzbox, acoustic, reso, custom2 (hyphens and spaces are optional). Pickup
position 1 is the bridge, 5 the neck.

Does the same handshake as monitor.py first. Only send messages the guitar
itself sends (see README.md); unknown SysEx could write to flash.
"""

import argparse
import sys

import jtv
from link import VariaxLink

MIDI_CHANNEL = 1  # the channel the guitar reports on
CONTROLLERS = {"volume": 7, "tone": 79}


def parse_messages(tokens):
    """Turn command line tokens into MIDI messages: "<bank> <position>" pairs or hex messages."""
    messages = []
    tokens = list(tokens)
    while tokens:
        token = tokens.pop(0)
        knob_index = jtv.bank_index(token)
        if knob_index is not None:
            if not tokens or not tokens[0].isdigit() or not 1 <= int(tokens[0]) <= 5:
                raise ValueError("%s needs a pickup position 1-5, e.g. \"%s 3\"" % (token, token))
            program = jtv.position_to_program(knob_index, int(tokens.pop(0)))
            messages.append(bytes([0xC0 | (MIDI_CHANNEL - 1), program]))
            continue
        cc = CONTROLLERS.get(token.lower())
        if cc is not None:
            if not tokens or not tokens[0].isdigit() or not 0 <= int(tokens[0]) <= 127:
                raise ValueError("%s needs a value 0-127, e.g. \"%s 64\"" % (token, token))
            messages.append(bytes([0xB0 | (MIDI_CHANNEL - 1), cc, int(tokens.pop(0))]))
            continue
        try:
            messages.append(bytes.fromhex(token))
        except ValueError:
            raise ValueError("%r is not a model bank name, volume, tone or hex bytes" % token)
    return messages


def main():
    parser = argparse.ArgumentParser(description="Send MIDI messages to the Variax.")
    parser.add_argument("messages", nargs="+",
                        help='a model ("lester 5"), "volume N", "tone N" or hex bytes of one MIDI message ("C0 2C")')
    parser.add_argument("--wait", type=float, default=2.0, help="seconds to listen after each message")
    args = parser.parse_args()

    try:
        messages = parse_messages(args.messages)
    except ValueError as e:
        sys.exit(str(e))

    with VariaxLink() as link:
        link.handshake()
        for msg in messages:
            link.send(msg)
            link.listen(args.wait)


if __name__ == "__main__":
    main()
