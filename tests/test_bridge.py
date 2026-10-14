"""The MIDI bridge's translation rules, with a fake guitar connection (no guitar or MIDI needed)."""

import pytest

from variax import config as configuration
from variax import jtv, protocol
from variax.bridge import Bridge

KNOB = {1: ("STANDARD", [0] * 6), 2: ("DROP D", [-2, 0, 0, 0, 0, 0]), 6: ("DADGAD", [-2, 0, 0, 0, -2, -2])}


class FakeLink:
    def __init__(self, flags=0x011BEF):
        self.sent = []
        self.flags = flags

    def send_and_wait_ack(self, msg):
        self.sent.append(bytes(msg))
        return True

    def read_words(self, address, count):
        assert address == protocol.FLAGS_ADDRESS
        return [self.flags]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make(settings=None, flags=0x011BEF):
    config = configuration.validate(settings or {})
    link, to_app, clock = FakeLink(flags), [], Clock()
    bridge = Bridge(config, link, to_app.append, KNOB, clock=clock)
    return bridge, link, to_app, clock


def pc(n, channel=1):
    return bytes([0xC0 | (channel - 1), n])


def cc(number, value, channel=1):
    return bytes([0xB0 | (channel - 1), number, value])


def strings(*offsets):
    return protocol.set_strings_message(list(offsets))


ON = protocol.tuning_enable_message(True)
OFF = protocol.tuning_enable_message(False)


def test_models_mode_program_change_volume_tone():
    bridge, link, _, _ = make()
    bridge.handle_app([pc(44), cc(7, 100), cc(79, 64)])
    assert link.sent == [protocol.program_change(44), protocol.control_change(7, 100), protocol.control_change(79, 64)]


def test_other_channels_are_ignored_and_line6_sysex_passes_through():
    bridge, link, _, _ = make({"midi": {"channel": 3}})
    sysex = bytes.fromhex("F0 00 01 0C 07 00 52 01 F7")
    mackie_probe = bytes.fromhex("F0 00 00 66 14 00 F7")       # Logic Pro looking for control surfaces
    bridge.handle_app([pc(44, channel=1), cc(7, 100, channel=1), pc(5, channel=3), mackie_probe, sysex])
    assert link.sent == [protocol.program_change(5), sysex]


def test_program_changes_above_104_are_ignored_in_models_mode():
    bridge, link, _, _ = make()
    bridge.handle_app([pc(105)])
    assert link.sent == []


def test_tuning_cc():
    bridge, link, _, _ = make()
    bridge.handle_app([cc(84, 6)])                            # knob tuning 6
    assert link.sent == [strings(-2, 0, 0, 0, -2, -2), ON]
    link.sent.clear()
    bridge.handle_app([cc(84, 0)])                            # none
    assert link.sent == [OFF]
    link.sent.clear()
    bridge.handle_app([cc(84, 9), cc(84, 12)])                # unknown knob slot, nothing in [tunings]
    assert link.sent == []


def test_tuning_cc_from_tunings_table():
    bridge, link, _, _ = make({"tunings": {"12": "E B E G# B E"}})
    bridge.handle_app([cc(84, 12)])
    assert link.sent == [strings(0, 2, 2, 1, 0, 0), ON]


def test_keep_tuning_method():
    bridge, link, _, _ = make({"behavior": {"tuning_method": "keep"}})
    bridge.handle_app([cc(84, 2)])
    assert link.sent == [protocol.fly_tuning_message([-2, 0, 0, 0, 0, 0])]
    link.sent.clear()
    bridge.handle_app([pc(15)])                               # a kept tuning needs no reapplying
    assert link.sent == [protocol.program_change(15)]
    link.sent.clear()
    bridge.handle_app([cc(20, 62), cc(26, 30)])               # cents are ignored with "keep"
    assert link.sent == [protocol.fly_tuning_message([-2, 0, 0, 0, 0, 0])]
    link.sent.clear()
    bridge.handle_app([cc(84, 0)])
    assert link.sent == [protocol.fly_tuning_message([0] * 6)]


def test_reapply_tuning_after_model():
    bridge, link, _, _ = make()
    bridge.handle_app([cc(84, 2)])
    link.sent.clear()
    bridge.handle_app([pc(15)])
    assert link.sent == [protocol.program_change(15), strings(-2, 0, 0, 0, 0, 0), ON]

    bridge, link, _, _ = make({"behavior": {"reapply_tuning_after_model": False}})
    bridge.handle_app([cc(84, 2), pc(15)])
    assert link.sent[-1] == protocol.program_change(15)

    bridge, link, _, _ = make()
    bridge.handle_app([cc(84, 0), pc(15)])                    # nothing to reapply after "none"
    assert link.sent[-1] == protocol.program_change(15)


def test_string_ccs():
    bridge, link, _, _ = make()
    bridge.handle_app([cc(20, 62)])                           # low E -2: first write sets all six, tuning on
    assert link.sent == [strings(-2, 0, 0, 0, 0, 0), ON]
    link.sent.clear()
    bridge.handle_app([cc(26, 54)])                           # low E -10 cents: a one-word write
    word = round(-2.1 * (1 << 23) / 12)
    assert link.sent == [protocol.write_message(protocol.STRINGS_ADDRESS + 5, [word])]
    link.sent.clear()
    bridge.handle_app([cc(25, 65), cc(24, 63)])               # two strings at once: one write of all six
    assert link.sent == [strings(-2.1, 0, 0, 0, -1, 1), ON]


def test_string_ccs_start_from_the_current_tuning_and_clamp():
    bridge, link, _, _ = make()
    bridge.handle_app([cc(84, 6), cc(21, 66)])                # DADGAD, then A string +2: one word
    assert link.sent == [strings(-2, 0, 0, 0, -2, -2), ON,
                         protocol.write_message(protocol.STRINGS_ADDRESS + 4, [round(2 * (1 << 23) / 12)])]
    link.sent.clear()
    bridge.handle_app([cc(22, 127), cc(23, 0)])               # clamped to +12 (just under) and -12
    assert protocol.parse_write(link.sent[0])[1][2:4] == [-(1 << 23), (1 << 23) - 1]


def test_only_the_last_value_of_a_cc_in_a_batch_is_sent():
    bridge, link, _, _ = make()
    bridge.handle_app([cc(7, 10), cc(7, 20), cc(7, 30), cc(79, 5)])
    assert link.sent == [protocol.control_change(7, 30), protocol.control_change(79, 5)]


def test_twelve_string_and_modeling():
    bridge, link, _, _ = make(flags=0x011BEF)
    bridge.handle_app([cc(85, 127)])
    assert link.sent == protocol.twelve_string_messages(True, flags=0x011BEF)
    link.sent.clear()
    bridge.handle_app([cc(86, 0), cc(86, 127)])
    assert link.sent == [protocol.MODELING_MESSAGE]           # last value wins: modeling
    link.sent.clear()
    bridge.handle_app([cc(86, 10)])
    assert link.sent == [protocol.MAGNETIC_MESSAGE]


def test_disabled_ccs_are_ignored():
    bridge, link, _, _ = make({"cc": {"tone": False, "string_cents": False}})
    bridge.handle_app([cc(79, 64), cc(26, 50)])
    assert link.sent == []


PATCHES = {
    "midi": {"program_change": "patches"},
    "patch": {
        "1": {"model": "lester 5", "tuning": "dadgad", "tone": 90},
        "2": {"program": 60, "strings": "E B E G# B E", "twelve_string": True, "modeling": True},
        "3": {"tuning": "none"},
        "4": {"tuning": "drop d"},
    },
}


def test_patches():
    bridge, link, _, _ = make(PATCHES)
    bridge.handle_app([pc(1)])
    assert link.sent == [protocol.program_change(15), protocol.control_change(79, 90), strings(-2, 0, 0, 0, -2, -2), ON]
    link.sent.clear()
    bridge.handle_app([pc(2)])
    assert link.sent == ([protocol.MODELING_MESSAGE, protocol.program_change(60), strings(0, 2, 2, 1, 0, 0), ON]
                         + protocol.twelve_string_messages(True, flags=0x011BEF))
    link.sent.clear()
    bridge.handle_app([pc(3), pc(4)])
    assert link.sent == [OFF, strings(-2, 0, 0, 0, 0, 0), ON]


def test_patch_fallback():
    bridge, link, _, _ = make(PATCHES)
    bridge.handle_app([pc(44)])                               # no patch 44, no fallback: ignored
    assert link.sent == []
    settings = dict(PATCHES, midi={"program_change": "patches", "patch_fallback": True})
    bridge, link, _, _ = make(settings)
    bridge.handle_app([cc(84, 2), pc(44)])                    # model only, no tuning reapplied
    assert link.sent[-1] == protocol.program_change(44)
    assert link.sent.count(protocol.program_change(44)) == 1 and len(link.sent) == 3


def test_guitar_changes_go_to_the_app_on_the_bridge_channel():
    bridge, link, to_app, _ = make({"midi": {"channel": 2}, "cc": {"volume": 11, "tuning": 3}})
    for msg in (pc(44), cc(7, 90), cc(79, 64), cc(84, 2), bytes([0xFF])):
        bridge.handle_guitar(msg)
    assert to_app == [[0xC1, 44], [0xB1, 11, 90], [0xB1, 79, 64], [0xB1, 3, 2]]


def test_echoes_from_the_app_are_ignored():
    bridge, link, to_app, clock = make()
    bridge.handle_guitar(cc(7, 90))
    bridge.handle_guitar(pc(44))
    bridge.handle_app([cc(7, 90), pc(44)])                    # echoed straight back: ignored
    assert link.sent == []
    clock.now += 1
    bridge.handle_app([cc(7, 90)])                            # later, the same value is a real change
    assert link.sent == [protocol.control_change(7, 90)]


def test_no_forwarding():
    bridge, link, to_app, _ = make({"midi": {"forward_from_guitar": False}})
    bridge.handle_guitar(cc(7, 90))
    assert to_app == []


def test_default_config_file_matches_the_defaults():
    import tomllib
    assert configuration.validate(tomllib.loads(configuration.default_config_text())) == configuration.DEFAULTS


@pytest.mark.parametrize("settings, message", [
    ({"midi": {"channel": 17}}, "channel"),
    ({"cc": {"tone": 7}}, "used for both"),
    ({"midi": {"chanel": 2}}, "unknown setting"),
    ({"tunings": {"11": "E A D G B E"}}, "12-127"),
    ({"patch": {"1": {"model": "strat 1"}}}, "unknown bank"),
    ({"patch": {"1": {"model": "lester 5", "program": 5}}}, "not both"),
    ({"behavior": {"tuning_method": "keep"}, "tunings": {"12": "-0.5 0 0 0 0 0"}}, "whole semitones"),
])
def test_config_errors(settings, message):
    with pytest.raises(configuration.ConfigError, match=message):
        configuration.validate(settings)
