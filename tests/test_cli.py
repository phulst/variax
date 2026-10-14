"""The variax command line, with --dry-run and offline commands (no guitar needed)."""

import click
import pytest
from click.testing import CliRunner

from variax import protocol
from variax import jtv
from variax.cli import format_word, main, plan_send, tunings_json


def run(*args):
    return CliRunner().invoke(main, list(args))


def test_send_order_is_fixed():
    # tone and tuning go after the model change that would reset them, whatever the option order
    messages = plan_send(program=18, tone=64, volume=100, tuning="dadgad", twelve_string=True, modeling=True)
    assert messages[0] == protocol.MODELING_MESSAGE
    assert messages[1] == protocol.program_change(18)
    assert messages[2] == protocol.control_change(protocol.VOLUME_CC, 100)
    assert messages[3] == protocol.control_change(protocol.TONE_CC, 64)
    assert messages[4] == protocol.set_strings_message([-2, 0, 0, 0, -2, -2])
    assert messages[5] == protocol.tuning_enable_message(True)
    assert messages[6:] == [("twelve-string", True)]  # reads the flags word when sending


def test_unknown_tuning_is_looked_up_on_the_guitar():
    assert plan_send(tuning="my custom") == [("tuning", "my custom")]


def test_send_examples_dry_run():
    result = run("send", "-n", "Rbilly 3", "--dry-run")
    assert result.exit_code == 0
    assert "C0 1B" in result.output and "R-Billy 3" in result.output

    result = run("send", "-p", "18", "--volume", "100", "--tone", "64", "--dry-run")
    assert result.exit_code == 0
    assert result.output.splitlines()[0].startswith("C0 12")

    result = run("send", "-s", "E B E G# B E", "--dry-run")
    assert result.exit_code == 0
    assert "+0 +2 +2 +1 +0 +0 (E B E G# B E)" in result.output

    result = run("send", "-s", "-2 0 0 0 0 0", "--keep", "--dry-run")
    assert result.exit_code == 0
    assert "on-the-fly tuning, low E first: -2 +0 +0 +0 +0 +0 (D A D G B E)" in result.output


def test_send_errors():
    assert run("send").exit_code != 0
    assert "not both" in run("send", "-p", "1", "-n", "lester 5").output
    assert "not both" in run("send", "-t", "dadgad", "-s", "0 0 0 0 0 0").output
    assert run("send", "-p", "105").exit_code != 0
    assert "unknown bank" in run("send", "-n", "strat 1", "--dry-run").output


def test_models():
    result = run("models")
    assert result.exit_code == 0
    assert "Jazzbox 1" in result.output and "factory Reso 1" in result.output


def test_format_word():
    assert format_word(0x353, 0x537065).split() == ["0x353", "0x537065", "5468261", "1.0325e+12", "Spe"]
    assert format_word(0x41C, -0x155555).split()[:3] == ["0x41C", "0xEAAAAB", "-1398101"]  # -2 semitones


def test_read_address_errors():
    assert "not an address" in run("read", "zz").output
    assert run("read", "0x1000000").exit_code != 0


KNOB = {1: ("STANDARD", [0] * 6), 2: ("DROP D", [-2, 0, 0, 0, 0, 0]), 6: ("MINE", [-2, 0, 0, -0.5, -2, -2])}


def test_tunings_json():
    assert tunings_json(KNOB) == {"tunings": [
        {"name": "STANDARD", "strings": "E A D G B E"},
        {"name": "DROP D", "strings": "D A D G B E"},
        {"name": "MINE", "strings": "-2 +0 +0 -0.5 -2 -2"},  # names and strings as stored on the guitar
    ]}
    assert jtv.parse_tuning_text(tunings_json(KNOB)["tunings"][2]["strings"]) == [-2, 0, 0, -0.5, -2, -2]


def test_load_tunings_json(tmp_path):
    from variax.cli import load_tunings_json
    assert load_tunings_json(tmp_path / "missing.json") is None
    path = tmp_path / "tunings.json"
    path.write_text('{"tunings": [{"name": "STANDARD", "strings": "E A D G B E"}]}')
    assert load_tunings_json(path) == [{"name": "STANDARD", "strings": "E A D G B E"}]
    path.write_text("not json")
    with pytest.raises(click.ClickException):
        load_tunings_json(path)


def test_monitor_tuning_knob_names():
    knob = tunings_json(KNOB)["tunings"]
    assert protocol.describe(bytes.fromhex("B0 54 02"), knob).endswith("tuning knob: DROP D (D A D G B E)")
    assert protocol.describe(bytes.fromhex("B0 54 03"), knob).endswith("tuning knob: MINE (-2 +0 +0 -0.5 -2 -2)")
    assert protocol.describe(bytes.fromhex("B0 54 00"), knob).endswith("tuning knob: MODEL (the model's own tuning)")
    assert protocol.describe(bytes.fromhex("B0 54 02")).endswith("tuning knob position 2")  # no tunings.json
    assert protocol.describe(bytes.fromhex("B0 54 09"), knob).endswith("tuning knob position 9")  # not in the file


def test_tuning_none():
    assert plan_send(tuning="none") == [protocol.tuning_enable_message(False)]
    assert plan_send(tuning="None") == [protocol.tuning_enable_message(False)]


def test_midi_write_config(tmp_path, monkeypatch):
    from variax import config as configuration
    monkeypatch.chdir(tmp_path)
    result = run("midi", "--write-config")
    assert result.exit_code == 0 and "wrote variax.toml" in result.output
    assert configuration.load("variax.toml", required=True) == configuration.DEFAULTS
    result = run("midi", "--write-config")
    assert result.exit_code != 0 and "already exists" in result.output


def test_on_off_values():
    for value in ("on", "yes", "TRUE", "On"):
        result = run("send", "--modeling", value, "--dry-run")
        assert result.exit_code == 0 and "modeling on" in result.output
    for value in ("off", "no", "false"):
        result = run("send", "--modelling", value, "--twelve-string", value, "--dry-run")
        assert result.exit_code == 0 and "modeling off (magnetic pickups)" in result.output
        assert "12-string off" in result.output
    assert "is not on or off" in run("send", "--modeling", "magnetic").output
