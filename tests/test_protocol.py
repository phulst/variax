"""Protocol tests against captured Workbench HD traffic and published examples (no guitar needed)."""

import json
from pathlib import Path

import pytest

from variax import jtv, protocol

CAPTURES = Path(__file__).parent.parent / "captures"


def captured_messages(name):
    """(direction, message) for every MIDI message in a Wireshark JSON export of a USBPcap capture."""
    path = CAPTURES / name
    if not path.exists():
        pytest.skip("capture %s not available (not included in the source distribution)" % name)
    parsers = {"out": protocol.MidiParser(), "in": protocol.MidiParser()}
    messages = []
    for packet in json.loads(path.read_text()):
        layers = packet["_source"]["layers"]
        data = layers.get("usb.capdata")
        if not data:
            continue
        direction = "in" if int(layers["usb"]["usb.endpoint_address"], 16) & 0x80 else "out"
        for msg in parsers[direction].feed(bytes.fromhex(data.replace(":", ""))):
            messages.append((direction, msg))
    return messages


def all_captured_writes():
    return [msg for name in ("workbench-tunings.json", "workbench-tuning-toggle-parallel-pitch.json")
            for direction, msg in captured_messages(name) if direction == "out" and msg[6] == protocol.WRITE]


def test_every_captured_write_rebuilds_byte_for_byte():
    writes = all_captured_writes()
    assert len(writes) == 17
    for msg in writes:
        address, words = protocol.parse_write(msg)
        assert protocol.write_message(address, words) == msg


def test_tunings_match_workbench():
    writes = all_captured_writes()
    for name in ("STANDARD", "DROP D", "HALF DOWN", "DROP Db", "ONE DOWN", "DADGAD"):
        assert protocol.set_strings_message(jtv.FACTORY_TUNINGS[name]) in writes


def test_tuning_on_off_and_twelve_string_match_workbench():
    writes = all_captured_writes()
    assert protocol.tuning_enable_message(True) in writes
    assert protocol.tuning_enable_message(False) in writes
    for msg in protocol.twelve_string_messages(True) + protocol.twelve_string_messages(False):
        assert msg in writes
    # changing only the Parallel Pitch bits of the captured flags gives Workbench's messages
    assert protocol.twelve_string_messages(True, flags=protocol.FLAGS_PARALLEL_PITCH_OFF) == \
        protocol.twelve_string_messages(True)
    assert protocol.twelve_string_messages(False, flags=protocol.FLAGS_PARALLEL_PITCH_ON) == \
        protocol.twelve_string_messages(False)


def test_twelve_string_keeps_other_flags():
    on = protocol.twelve_string_messages(True, flags=0x011BEF)[1]
    off = protocol.twelve_string_messages(False, flags=0x091BFF)[0]
    assert protocol.parse_write(on) == (protocol.FLAGS_ADDRESS, [0x091BFF])
    assert protocol.parse_write(off) == (protocol.FLAGS_ADDRESS, [0x011BEF])


def test_read_message_is_the_drivers_model_request():
    assert protocol.read_message(0x353, 32) == bytes.fromhex(
        "F0 00 01 0C 07 00 3C 00 02 00 00 00 00 03 05 03 00 00 00 F7")
    assert protocol.read_message(0x373, 32) == bytes.fromhex(
        "F0 00 01 0C 07 00 3C 00 02 00 00 00 00 03 07 03 00 00 00 F7")
    reply = protocol.WORKBENCH_SYSEX + bytes([protocol.READ]) + protocol.encode24(-0x0AAAAB) + b"\xF7"
    assert protocol.parse_read_reply(reply) == [-0x0AAAAB]


def test_knob_tunings_match_the_guitar():
    replies = [protocol.parse_tuning_reply(msg) for direction, msg in captured_messages("workbench-tunings.json")
               if direction == "in" and protocol.parse_tuning_reply(msg)]
    assert [name for _, name, _ in replies] == jtv.KNOB_TUNINGS_JTV59_69
    for slot, name, offsets in replies[:10]:  # factory tunings on the captured guitar
        assert [round(o) for o in offsets] == jtv.FACTORY_TUNINGS[name]


def test_guitar_acknowledges_writes():
    messages = captured_messages("workbench-tunings.json")
    assert ("in", protocol.ACK_MESSAGE) in messages


@pytest.mark.parametrize("offsets", [[0] * 6, [-2, 0, 0, 0, 0, 0], [-0.5, 1.25, 0, 0, 0, 11.9], [-12] * 6])
def test_string_offsets_round_trip(offsets):
    address, words = protocol.parse_write(protocol.set_strings_message(offsets))
    assert address == protocol.STRINGS_ADDRESS
    decoded = [w * 12 / (1 << 23) for w in reversed(words)]
    assert decoded == pytest.approx(offsets, abs=1e-5)


def test_string_offsets_out_of_range():
    with pytest.raises(ValueError):
        protocol.set_strings_message([12, 0, 0, 0, 0, 0])  # 2**23 would wrap around to -12
    with pytest.raises(ValueError):
        protocol.set_strings_message([0] * 5)


# Examples from the "Variax MIDI reference" spreadsheet (on-the-fly tuning by Joe Bear).
@pytest.mark.parametrize("hex_message, offsets", [
    ("F0 00 01 0C 07 05 52 04 00 00 00 00 00 00 00 00 00 00 00 00 F7", [0, 0, 0, 0, 0, 0]),
    ("F0 00 01 0C 07 05 52 04 0F 04 0F 04 0F 04 0F 04 0F 04 0F 04 F7", [-12] * 6),
    ("F0 00 01 0C 07 05 52 04 0F 0E 00 00 00 00 00 00 0F 0E 0F 0E F7", [-2, -2, 0, 0, 0, -2]),  # Blues G
    ("F0 00 01 0C 07 05 52 04 0F 0E 00 00 00 00 00 00 00 00 0F 0E F7", [-2, 0, 0, 0, 0, -2]),   # DADGBD
    ("F0 00 01 0C 07 05 52 04 0F 0F 0F 0F 0F 0F 0F 0F 0F 0F 0F 0F F7", [-1] * 6),
    ("F0 00 01 0C 07 05 52 04 00 07 00 07 00 07 00 07 00 07 00 07 F7", [7] * 6),
])
def test_fly_tuning_spreadsheet_examples(hex_message, offsets):
    msg = bytes.fromhex(hex_message)
    assert protocol.parse_fly_tuning(msg) == offsets
    assert protocol.fly_tuning_message(offsets) == msg


def test_fly_tuning_needs_whole_semitones():
    with pytest.raises(ValueError):
        protocol.fly_tuning_message([-0.5, 0, 0, 0, 0, 0])


def test_midi_parser():
    parser = protocol.MidiParser()
    # a stray F7 left from a previous connection, SysEx split over packets, running status, real-time
    assert parser.feed(bytes.fromhex("F7 F0 7E 7F 06")) == []
    assert parser.feed(bytes.fromhex("02 00 01 0C 07 00 05 00 30 32 32 33 F7 C0 05 B0 4F 7F")) == [
        bytes.fromhex("F0 7E 7F 06 02 00 01 0C 07 00 05 00 30 32 32 33 F7"),
        bytes.fromhex("C0 05"), bytes.fromhex("B0 4F 7F")]
    assert parser.feed(bytes.fromhex("4F 10 FF")) == [bytes.fromhex("B0 4F 10"), bytes.fromhex("FF")]


def test_describe():
    assert protocol.describe(bytes.fromhex("C0 2C")).endswith("Jazzbox 1: 1954 ES-175, bridge")
    assert "firmware 0223" in protocol.describe(bytes.fromhex("F0 7E 7F 06 02 00 01 0C 07 00 05 00 30 32 32 33 F7"))
    assert protocol.describe(protocol.ACK_MESSAGE) == "acknowledged"
    assert protocol.describe(protocol.MAGNETIC_MESSAGE) == "modeling off (magnetic pickups)"
