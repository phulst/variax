"""Send MIDI messages to the James Tyler Variax and print what it sends back.

Usage:
  uv run send.py lester 5              # select a model: bank name + pickup position 1-5
  uv run send.py R-BILLY 3             # bank names as in the Pilot's Guide, any case
  uv run send.py volume 100            # volume 0-127 (CC7)
  uv run send.py spank 1 tone 64       # tone 0-127 (CC79); send it after the model,
                                       # because a model change re-applies the tone knob
  uv run send.py tuning drop-d         # a tuning stored on the tuning knob, by name
  uv run send.py tuning off            # stop using the model's tuning (Workbench's Tuning button)
  uv run send.py strings -2 0 0 0 0 0  # any tuning: semitones per string, low E first
  uv run send.py 12string              # 12-string sound (Parallel Pitch); "12string off" to stop
  uv run send.py "C0 2C"               # a raw MIDI message, as hex bytes
  uv run send.py spank 1 tuning dadgad # several, in order
  uv run send.py --wait 5 lester 5     # listen 5 s after each message (default 0.5)

Bank names: custom1, t-model, spank, lester, special, r-billy, chime, semi,
jazzbox, acoustic, reso, custom2 (hyphens and spaces are optional). Pickup
position 1 is the bridge, 5 the neck.

Tunings are set the way Workbench HD sets them: as the current model's string
offsets, followed by switching the model's tuning on (Workbench's Tuning
button; with it off the offsets are ignored). The guitar plays them when the
tuning knob is on MODEL; any other knob position uses the knob's own tuning.
The 11 factory knob tunings are built in (jtv.KNOB_TUNINGS, also under the
Pilot's Guide names such as "1/2 down"); any other name is looked up among the
tunings stored on the guitar's knob, which takes about half a second.

Does the same handshake as monitor.py first. Only send messages the guitar
itself sends (see README.md); unknown SysEx could write to flash.
"""

import argparse
import sys

import jtv
from link import VariaxLink

MIDI_CHANNEL = 1  # the channel the guitar reports on
CONTROLLERS = {"volume": 7, "tone": 79}


def _number(token):
    try:
        return float(token)
    except ValueError:
        return None


def parse_messages(tokens):
    """Turn command line tokens into a list of MIDI messages and ("tuning", name) lookups."""
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
        if token.lower() == "strings":
            offsets = [_number(t) for t in tokens[:6]]
            if len(offsets) < 6 or None in offsets or any(abs(o) > 12 for o in offsets):
                raise ValueError("strings needs six semitone offsets, low E first, e.g. \"strings -2 0 0 0 0 0\"")
            del tokens[:6]
            messages += [jtv.set_strings_message(offsets), jtv.tuning_enable_message(True)]
            continue
        if token.lower().replace("-", "") in ("12string", "twelvestring"):
            on = True
            if tokens and tokens[0].lower() in ("on", "off"):
                on = tokens.pop(0).lower() == "on"
            messages.extend(jtv.twelve_string_messages(on))
            continue
        if token.lower() == "tuning":
            if not tokens:
                raise ValueError("tuning needs a name, e.g. \"tuning drop-d\"")
            name = tokens.pop(0)
            if name.lower() == "off":
                messages.append(jtv.tuning_enable_message(False))
            else:
                known = jtv.find_knob_tuning(name)
                # Factory knob tunings are built in; other names are looked up on the guitar.
                messages += [jtv.set_strings_message(known[1]) if known else ("tuning", name),
                             jtv.tuning_enable_message(True)]
            continue
        try:
            messages.append(bytes.fromhex(token))
        except ValueError:
            raise ValueError("%r is not a model bank name, volume, tone, strings, tuning, 12string or hex bytes" % token)
    return messages


def read_tunings(link):
    """Read the tunings stored on the tuning knob: {slot: (name, offsets low E first)}."""
    tunings = {}
    for slot in range(1, 12):
        link.send(jtv.WORKBENCH_SYSEX + bytes([jtv.READ_TUNING, slot, 0xF7]), "read tuning %d" % slot)
        for msg in link.listen(1.0, until=lambda m: jtv.parse_tuning_reply(m) is not None):
            reply = jtv.parse_tuning_reply(msg)
            if reply:
                tunings[reply[0]] = (reply[1], reply[2])
    return tunings


def find_tuning(tunings, name):
    wanted = "".join(c for c in name.lower() if c.isalnum())
    for slot, (tuning_name, offsets) in sorted(tunings.items()):
        if "".join(c for c in tuning_name.lower() if c.isalnum()) == wanted:
            return tuning_name, offsets
    known = ", ".join(n for n, _ in (tunings[s] for s in sorted(tunings)))
    sys.exit("No tuning called %r on the guitar. It has: %s" % (name, known))


def main():
    parser = argparse.ArgumentParser(description="Send MIDI messages to the Variax.")
    parser.add_argument("messages", nargs="+",
                        help='a model ("lester 5"), "volume N", "tone N", "tuning NAME", '
                             '"strings E A D G B E" offsets, "12string [on|off]", '
                             'or hex bytes of one MIDI message ("C0 2C")')
    parser.add_argument("--wait", type=float, default=0.5, help="seconds to listen after each message")
    args = parser.parse_args()

    try:
        messages = parse_messages(args.messages)
    except ValueError as e:
        sys.exit(str(e))

    with VariaxLink() as link:
        link.handshake()
        tunings = None
        for msg in messages:
            if isinstance(msg, tuple):
                if tunings is None:
                    tunings = read_tunings(link)
                name, offsets = find_tuning(tunings, msg[1])
                msg = jtv.set_strings_message(offsets)
            link.send(msg)
            link.listen(args.wait)


if __name__ == "__main__":
    main()
