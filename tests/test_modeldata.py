"""Formatting of `variax dump` output (no guitar needed)."""

from variax.modeldata import format_diff, format_model

MODEL = {"name": "JazzBox-4", "bank": "U-JAZZBOX", "control": "00" * 156,
         "tuning": [-2, 0, 0, 0, -2, -2], "tuning_on": True, "twelve_string": False, "flags": "0x001BEF"}


def test_format_model_shows_tuning_and_twelve_string():
    text = format_model(MODEL)
    assert "tuning: on, -2 +0 +0 +0 -2 -2  (D A D G A D)" in text
    assert "12-string: off    flags: 0x001BEF" in text


def test_format_model_without_tuning_fields():
    # dumps saved before the tuning fields were added still format
    old = {k: MODEL[k] for k in ("name", "bank", "control")}
    assert "tuning:" not in format_model(old)


def test_format_diff_shows_tuning_changes():
    changed = dict(MODEL, tuning=[0] * 6, twelve_string=True, flags="0x091BFF")
    text = format_diff(MODEL, changed)
    assert "tuning: [-2, 0, 0, 0, -2, -2] -> [0, 0, 0, 0, 0, 0]" in text
    assert "twelve_string: False -> True" in text
    assert "no differences" in format_diff(MODEL, MODEL)
