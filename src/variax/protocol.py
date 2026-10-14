"""Variax MIDI messages: building, parsing and describing them.

The Variax USB Interface carries plain MIDI bytes. The guitar uses channel 1:
Program Change selects a model, CC7 and CC79 set volume and tone, and it
reports its knobs with Program Change, CC7, CC79 and CC84 (tuning knob).
Everything else is Line 6 SysEx: F0 00 01 0C (Line 6) 07 (Variax) followed by
an address byte (00 from us, 05 = the guitar, as Workbench HD uses it) and a
command. Data in SysEx comes as 4-bit nibbles; a 24-bit word takes 6 nibbles,
least significant nibble first.
"""

from . import jtv

MIDI_CHANNEL = 1
VOLUME_CC = 7
TONE_CC = 79
TUNING_KNOB_CC = 84  # reported by the guitar only; sending it does nothing

# Handshake (from the Linux kernel driver sound/usb/line6/variax.c).
IDENTITY_REQUEST = bytes.fromhex("F0 7E 7F 06 01 F7")  # MIDI Universal Identity Request
IDENTITY_REPLY_PREFIX = bytes.fromhex("F0 7E 7F 06 02 00 01 0C")
ACTIVATE = bytes.fromhex("F0 00 01 0C 07 00 2A 01 F7")  # makes the guitar report its controls
LINE6_SYSEX_PREFIX = bytes.fromhex("F0 00 01 0C")
VARIAX_SYSEX = bytes.fromhex("F0 00 01 0C 07")

# Messages Workbench HD uses (captured with USBPcap). Command 43 writes words
# into the guitar's working copy of the current model:
#   F0 00 01 0C 07 05 43 <word count> <word address> <words...> F7
# and the guitar answers with ACK. Nothing is saved; a model change reloads the
# stored model.
WORKBENCH_SYSEX = bytes.fromhex("F0 00 01 0C 07 05")
WRITE = 0x43
READ = 0x3C         # F0 00 01 0C 07 00 3C <word count> <word address> F7 -> F0 00 01 0C 07 05 3C <words> F7
READ_TUNING = 0x1B  # F0 00 01 0C 07 05 1B <slot 1-11> F7 -> six offsets + 18-character name
ACK = 0x71          # F0 00 01 0C 07 05 71 F7, the guitar's reply to WRITE
ACK_MESSAGE = WORKBENCH_SYSEX + bytes([ACK, 0xF7])

# Word addresses (per string: high E string first).
STRINGS_ADDRESS = 0x41C         # six pitch offsets, signed, 2**23 = one octave
TUNING_ENABLE_ADDRESS = 0x422   # Workbench's Tuning on/off button: 0 or 1
FLAGS_ADDRESS = 0x001           # on/off flags; Parallel Pitch is bits 0x080010
PARALLEL_PITCH_ADDRESS = 0x2AE  # 78 words of Parallel Pitch settings
STRING_NAMES = ["low E", "A", "D", "G", "B", "high E"]
ADDRESS_NAMES = {
    STRINGS_ADDRESS: "string tuning",
    TUNING_ENABLE_ADDRESS: "tuning on/off",
    FLAGS_ADDRESS: "flags",
    PARALLEL_PITCH_ADDRESS: "parallel pitch settings",
}

# Parallel Pitch as Workbench sends it for a 12-string: pitch +12 +12 +12 +12 0 0
# and cents -5 -5 -5 -7 -3 -4 (low E first), mix 30% on every string. Captured
# verbatim; Workbench turns pitch and cents into what look like per-string filter
# coefficients, so only this exact setting can be replayed. Layout: 6 words
# per string, 60 words (10 per string), 6 dry levels (0.7), 6 wet levels (0.3).
TWELVE_STRING_SETTINGS = [
    0x000174, 0x000174, 0x000174, 0x000151, 0x000151, 0x00014F,
    0x1E2332, 0xC1BC7F, 0x2036A7, 0x1E59D9, 0xC1BC7F, 0x000000,
    0xF621FB, 0x0FFCA7, 0x000000, 0xE61EA2, 0x1F7E8D, 0xC0780E,
    0x201622, 0x1F94AF, 0xC0780E, 0x000000, 0xF40FF7, 0x0F31F0,
    0x000000, 0xE341E7, 0x1B785D, 0xC659FE, 0x1E7EAD, 0x19F70A,
    0xC659FE, 0x000000, 0xF38474, 0x113829, 0x000000, 0xE4BC9D,
    0x1B3300, 0xC7D248, 0x1EA7B8, 0x19DAB9, 0xC7D248, 0x16095A,
    0xCD3375, 0x234F87, 0x1958E0, 0xCD3375, 0x1B2B88, 0xC72CC9,
    0x1DEBB1, 0x19173A, 0xC72CC9, 0x199D54, 0xC6C001, 0x221F2B,
    0x1BBC7E, 0xC6C001, 0x1D725E, 0xC37F67, 0x1F26D0, 0x1C992D,
    0xC37F67, 0x1AA7EC, 0xC44579, 0x224CF7, 0x1CF4E3, 0xC44579,
    0x599999, 0x599999, 0x599999, 0x599999, 0x599999, 0x599999,
    0x266666, 0x266666, 0x266666, 0x266666, 0x266666, 0x266666,
]
FLAGS_PARALLEL_PITCH_ON = 0x090BFF   # as captured; the other bits differ per model
FLAGS_PARALLEL_PITCH_OFF = 0x010BEF
PARALLEL_PITCH_BITS = 0x080010

# From the "Variax MIDI reference" spreadsheet (community reverse engineering).
# Command 52 with our address 00: magnetic pickups (00) or modeling (01), like
# pushing the model knob.
PICKUP_MODE = bytes.fromhex("F0 00 01 0C 07 00 52")
MAGNETIC_MESSAGE = PICKUP_MODE + bytes([0x00, 0xF7])
MODELING_MESSAGE = PICKUP_MODE + bytes([0x01, 0xF7])
# Command 52 04 with the guitar's address 05: an on-the-fly tuning, credited to
# Joe Bear. Six signed whole semitones, high E string first, each as a byte
# split into two nibbles, high nibble first (0F 0E = -2).
FLY_TUNING_HEADER = bytes.fromhex("F0 00 01 0C 07 05 52 04")


def hexs(data):
    return " ".join("%02X" % b for b in data)


def encode24(value):
    value &= 0xFFFFFF
    return bytes((value >> (4 * i)) & 0x0F for i in range(6))


def decode24(nibbles):
    value = sum(n << (4 * i) for i, n in enumerate(nibbles[:6]))
    return value - (1 << 24) if value & 0x800000 else value


def program_change(program):
    if not 0 <= program <= 127:
        raise ValueError("program must be 0-127")
    return bytes([0xC0 | (MIDI_CHANNEL - 1), program])


def control_change(controller, value):
    if not 0 <= value <= 127:
        raise ValueError("value must be 0-127")
    return bytes([0xB0 | (MIDI_CHANNEL - 1), controller, value])


def write_message(address, words):
    """SysEx that writes 24-bit words to the current model, starting at a word address."""
    data = b"".join(encode24(w) for w in words)
    return WORKBENCH_SYSEX + bytes([WRITE]) + encode24(len(words)) + encode24(address) + data + b"\xF7"


def read_message(address, count):
    """SysEx that reads `count` 24-bit words of the current model (the working copy) from a word address."""
    return VARIAX_SYSEX + bytes([0x00, READ]) + encode24(count) + encode24(address) + b"\xF7"


def parse_read_reply(msg):
    """The words in the guitar's reply to a READ, or None."""
    if not msg.startswith(WORKBENCH_SYSEX) or len(msg) < 8 or msg[6] != READ:
        return None
    body = msg[7:-1]
    return [decode24(body[i:i + 6]) for i in range(0, len(body) - 5, 6)]


def parse_write(msg):
    """Decode a WRITE message into (address, words), or None."""
    if not msg.startswith(WORKBENCH_SYSEX) or len(msg) < 8 + 18 or msg[6] != WRITE:
        return None
    body = msg[7:-1]
    words = [decode24(body[i:i + 6]) for i in range(0, len(body) - 5, 6)]
    count, address, data = words[0], words[1], words[2:]
    if count != len(data):
        return None
    return address, data


def set_strings_message(offsets):
    """SysEx that sets the current model's per-string pitch offsets.

    offsets: six semitone offsets from standard tuning, low E string first
    (as tunings are written in the Pilot's Guide). Fractions are allowed; the
    range is -12 to just under +12 (2**23 is one octave). The guitar plays them
    when the tuning knob is on MODEL and the model's tuning is on.
    """
    if len(offsets) != 6:
        raise ValueError("need six string offsets")
    if any(not -12 <= o < 12 for o in offsets):
        raise ValueError("string offsets must be from -12 to below +12 semitones")
    return write_message(STRINGS_ADDRESS, [round(s * (1 << 23) / 12) for s in reversed(offsets)])


def tuning_enable_message(on=True):
    """SysEx for Workbench's Tuning on/off button: whether the model's string tuning is used."""
    return write_message(TUNING_ENABLE_ADDRESS, [1 if on else 0])


def twelve_string_messages(on=True, flags=None):
    """Messages that turn the 12-string Parallel Pitch on (settings, then flag) or off.

    flags: the model's current flags word (read it first), so that only the
    Parallel Pitch bits change. Without it, the flags captured from Workbench
    are written, which may also change other on/off settings of the model.
    """
    if flags is None:
        new_flags = FLAGS_PARALLEL_PITCH_ON if on else FLAGS_PARALLEL_PITCH_OFF
    else:
        flags &= 0xFFFFFF
        new_flags = flags | PARALLEL_PITCH_BITS if on else flags & ~PARALLEL_PITCH_BITS
    flag_message = write_message(FLAGS_ADDRESS, [new_flags])
    return [write_message(PARALLEL_PITCH_ADDRESS, TWELVE_STRING_SETTINGS), flag_message] if on else [flag_message]


def read_tuning_message(slot):
    return WORKBENCH_SYSEX + bytes([READ_TUNING, slot, 0xF7])


def parse_tuning_reply(msg):
    """Decode a READ_TUNING reply into (slot, name, offsets low E first), or None."""
    if not msg.startswith(WORKBENCH_SYSEX) or len(msg) < 8 + 36 + 1 or msg[6] != READ_TUNING:
        return None
    body = msg[8:-1]
    offsets = [decode24(body[i:i + 6]) * 12 / (1 << 23) for i in range(0, 36, 6)]
    name = bytearray()
    for i in range(36, len(body) - 5, 6):
        n = body[i:i + 6]
        name += bytes([n[4] | n[5] << 4, n[2] | n[3] << 4, n[0] | n[1] << 4])
    return msg[7], name.decode("ascii", "replace").strip(), list(reversed(offsets))


def fly_tuning_message(offsets):
    """On-the-fly tuning SysEx; offsets are whole semitones, low E string first."""
    if len(offsets) != 6:
        raise ValueError("need six string offsets")
    if any(abs(o - round(o)) > 0.01 or not -64 <= o <= 63 for o in offsets):
        raise ValueError("on-the-fly tunings take whole semitones")
    data = bytearray()
    for o in reversed(offsets):
        byte = round(o) & 0xFF
        data += bytes([byte >> 4, byte & 0x0F])
    return FLY_TUNING_HEADER + bytes(data) + b"\xF7"


def parse_fly_tuning(msg):
    """Offsets (low E first) of an on-the-fly tuning SysEx, or None."""
    if not msg.startswith(FLY_TUNING_HEADER) or len(msg) != len(FLY_TUNING_HEADER) + 13:
        return None
    body = msg[len(FLY_TUNING_HEADER):-1]
    values = []
    for i in range(0, 12, 2):
        byte = body[i] << 4 | body[i + 1]
        values.append(byte - 256 if byte & 0x80 else byte)
    return list(reversed(values))


class MidiParser:
    """Splits a raw byte stream into complete MIDI messages (handles running status)."""

    def __init__(self):
        self.buf = bytearray()
        self.running_status = None

    def feed(self, data):
        messages = []
        for b in data:
            if b >= 0xF8:  # real-time bytes can appear anywhere, even inside SysEx
                messages.append(bytes([b]))
            elif b == 0xF0:
                self.buf = bytearray([b])
                self.running_status = None
            elif self.buf and self.buf[0] == 0xF0:
                self.buf.append(b)
                if b == 0xF7:
                    messages.append(bytes(self.buf))
                    self.buf = bytearray()
            elif b == 0xF7:  # end of a SysEx whose start we never saw, e.g. left over from a previous run
                self.buf = bytearray()
            elif b & 0x80:
                self.buf = bytearray([b])
                self.running_status = b if b < 0xF0 else None
                if self._complete():
                    messages.append(self._take())
            else:
                if not self.buf and self.running_status is not None:
                    self.buf = bytearray([self.running_status])
                if self.buf:
                    self.buf.append(b)
                    if self._complete():
                        messages.append(self._take())
        return messages

    def _complete(self):
        status = self.buf[0]
        if status < 0xF0:
            data_len = 1 if (status & 0xF0) in (0xC0, 0xD0) else 2
        else:
            data_len = {0xF1: 1, 0xF2: 2, 0xF3: 1}.get(status, 0)
        return len(self.buf) == 1 + data_len

    def _take(self):
        msg = bytes(self.buf)
        self.buf = bytearray()
        return msg


def _format_offsets(offsets):
    """ "-2 +0 +0 +0 -2 -2 (D A D G A D)": semitone offsets, with the notes when they are whole."""
    text = " ".join("%+.2g" % o for o in offsets)
    notes = jtv.offsets_to_notes(offsets)
    return "%s (%s)" % (text, notes) if notes else text


def describe(msg, knob_tunings=None):
    """One-line description of a MIDI message to or from the Variax.

    knob_tunings: the tuning knob's tunings as [{"name", "strings"}, ...] for
    positions 1-11 (from tunings.json); without them, knob changes are shown
    as positions.
    """
    status = msg[0]
    if status == 0xF0:
        return _describe_sysex(msg)
    if status == 0xFF:
        return "reset (guitar resends its state; tuning knob push, which on a JTV-59 toggles the selector between models 1-3-5 and 2-3-4)"
    if status >= 0xF0:
        return "system message"
    kind = status & 0xF0
    channel = (status & 0x0F) + 1
    if kind == 0xC0:
        return "program change ch%d %d  ->  %s" % (channel, msg[1], jtv.describe_program(msg[1]))
    if kind == 0xB0:
        cc, value = msg[1], msg[2]
        if cc == TUNING_KNOB_CC:
            return "control change ch%d CC84 = %d  ->  %s" % (channel, value, _describe_knob(value, knob_tunings))
        name = {VOLUME_CC: "volume", TONE_CC: "tone"}.get(cc, "")
        return "control change ch%d CC%d = %d%s" % (channel, cc, value, "  (%s)" % name if name else "")
    names = {0x80: "note off", 0x90: "note on", 0xA0: "poly pressure", 0xD0: "channel pressure", 0xE0: "pitch bend"}
    return "%s ch%d" % (names[kind], channel)


def _describe_knob(position, knob_tunings):
    if position == 0:
        return "tuning knob: MODEL (the model's own tuning)"
    if knob_tunings and position <= len(knob_tunings):
        tuning = knob_tunings[position - 1]
        return "tuning knob: %s (%s)" % (tuning["name"], tuning["strings"])
    return "tuning knob position %d" % position


def _describe_sysex(msg):
    if msg.startswith(IDENTITY_REPLY_PREFIX) and len(msg) >= 17:
        family = msg[8] | msg[9] << 7
        member = msg[10] | msg[11] << 7
        version = bytes(msg[12:16]).decode("ascii", "replace")
        return "identity reply: Line 6 family %d, member %d, firmware %s" % (family, member, version)
    if msg == IDENTITY_REQUEST:
        return "identity request"
    if msg == ACTIVATE:
        return "activate"
    write = parse_write(msg)
    if write:
        address, words = write
        if address == STRINGS_ADDRESS and len(words) == 6:
            offsets = [w * 12 / (1 << 23) for w in reversed(words)]
            return "set string tuning, low E first: %s" % _format_offsets(offsets)
        if STRINGS_ADDRESS <= address < STRINGS_ADDRESS + 6 and len(words) == 1:
            string = STRING_NAMES[5 - (address - STRINGS_ADDRESS)]
            return "set %s string: %+.2f semitones" % (string, words[0] * 12 / (1 << 23))
        if address == TUNING_ENABLE_ADDRESS and len(words) == 1:
            if words[0]:
                return "model tuning on (the string tuning above is used)"
            return "tuning none (model tuning off: the strings sound as physically tuned)"
        if address == FLAGS_ADDRESS and len(words) == 1:
            flags = words[0] & 0xFFFFFF
            return "write flags 0x%06X, parallel pitch %s" % (flags, "on" if flags & PARALLEL_PITCH_BITS else "off")
        name = ADDRESS_NAMES.get(address, "")
        values = " ".join("0x%06X" % (w & 0xFFFFFF) for w in words[:6]) + (" ..." if len(words) > 6 else "")
        return "write %d words at 0x%03X%s: %s" % (len(words), address, " (%s)" % name if name else "", values)
    if msg in (MAGNETIC_MESSAGE, MODELING_MESSAGE):
        return "modeling off (magnetic pickups)" if msg == MAGNETIC_MESSAGE else "modeling on"
    fly = parse_fly_tuning(msg)
    if fly:
        return "on-the-fly tuning, low E first: %s" % _format_offsets(fly)
    tuning = parse_tuning_reply(msg)
    if tuning:
        slot, name, offsets = tuning
        return "tuning %d: %s  %s" % (slot, name, _format_offsets(offsets))
    if msg.startswith(VARIAX_SYSEX + bytes([0x00, READ])) and len(msg) == 20:
        return "read %d words at 0x%03X" % (decode24(msg[7:13]), decode24(msg[13:19]))
    words = parse_read_reply(msg)
    if words is not None:
        return "%d words: %s" % (len(words), " ".join("0x%06X" % (w & 0xFFFFFF) for w in words[:6]) +
                                 (" ..." if len(words) > 6 else ""))
    if msg.startswith(WORKBENCH_SYSEX) and len(msg) == 9 and msg[6] == READ_TUNING:
        return "read tuning %d" % msg[7]
    if msg == ACK_MESSAGE:
        return "acknowledged"
    if msg.startswith(LINE6_SYSEX_PREFIX):
        return "Line 6 SysEx"
    return "SysEx"
