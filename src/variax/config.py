"""Settings for `variax midi`, read from variax.toml.

Every setting is optional; default.toml (shipped with the package, and what
`variax midi --write-config` writes) documents them all with their defaults.
"""

import copy
import tomllib
from importlib import resources

from . import jtv

CONFIG_FILE = "variax.toml"

DEFAULTS = {
    "midi": {
        "port": "Variax",
        "channel": 1,
        "forward_from_guitar": True,
        "program_change": "models",
        "patch_fallback": False,
    },
    "cc": {
        "volume": 7,
        "tone": 79,
        "tuning": 84,
        "twelve_string": 85,
        "modeling": 86,
        "string_semitones": [20, 21, 22, 23, 24, 25],
        "string_cents": [26, 27, 28, 29, 30, 31],
    },
    "behavior": {
        "tuning_method": "model",
        "reapply_tuning_after_model": True,
    },
    "tunings": {},
    "patch": {},
}

PATCH_FIELDS = {"model", "program", "volume", "tone", "tuning", "strings", "twelve_string", "modeling"}


class ConfigError(ValueError):
    pass


def default_config_text():
    return resources.files("variax").joinpath("default.toml").read_text()


def tuning_offsets(text):
    """Offsets for a tuning given by factory name ("dadgad") or as notes / semitones."""
    known = jtv.find_factory_tuning(text)
    return known[1] if known else jtv.parse_tuning_text(text)


def load(path=CONFIG_FILE, required=False):
    """The settings from a variax.toml merged over the defaults; the defaults if the file is missing
    (unless required). Raises ConfigError with a readable message for anything invalid."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        if required:
            raise ConfigError("%s not found" % path)
        data = {}
    except tomllib.TOMLDecodeError as e:
        raise ConfigError("%s: %s" % (path, e))
    try:
        return validate(data)
    except ConfigError as e:
        raise ConfigError("%s: %s" % (path, e))


def validate(data):
    """Merge `data` over the defaults and check every setting."""
    unknown = set(data) - set(DEFAULTS)
    if unknown:
        raise ConfigError("unknown section %s; sections are %s" % (_names(unknown), _names(DEFAULTS)))
    config = copy.deepcopy(DEFAULTS)
    for section in ("midi", "cc", "behavior"):
        values = data.get(section, {})
        unknown = set(values) - set(DEFAULTS[section])
        if unknown:
            raise ConfigError("unknown setting %s in [%s]; settings are %s"
                              % (_names(unknown), section, _names(DEFAULTS[section])))
        config[section].update(values)

    midi = config["midi"]
    _check(isinstance(midi["port"], str) and midi["port"].strip(), "[midi] port must be a name")
    _check(_is_int(midi["channel"]) and 1 <= midi["channel"] <= 16, "[midi] channel must be 1-16")
    _check(isinstance(midi["forward_from_guitar"], bool), "[midi] forward_from_guitar must be true or false")
    _check(midi["program_change"] in ("models", "patches"), '[midi] program_change must be "models" or "patches"')
    _check(isinstance(midi["patch_fallback"], bool), "[midi] patch_fallback must be true or false")

    cc = config["cc"]
    used = {}
    for name, value in cc.items():
        numbers = value if name.startswith("string_") else [value]
        if value is False:
            continue
        if name.startswith("string_"):
            _check(isinstance(value, list) and len(value) == 6,
                   "[cc] %s must be six CC numbers (low E string first) or false" % name)
        for number in numbers:
            _check(_is_int(number) and 0 <= number <= 127, "[cc] %s must be a CC number 0-127 or false" % name)
            _check(number not in used, "[cc] CC %d is used for both %s and %s" % (number, used.get(number), name))
            used[number] = name

    behavior = config["behavior"]
    _check(behavior["tuning_method"] in ("model", "keep"), '[behavior] tuning_method must be "model" or "keep"')
    _check(isinstance(behavior["reapply_tuning_after_model"], bool),
           "[behavior] reapply_tuning_after_model must be true or false")
    keep = behavior["tuning_method"] == "keep"

    for key, text in data.get("tunings", {}).items():
        _check(key.isdigit() and 12 <= int(key) <= 127, "[tunings] keys must be tuning CC values 12-127, not %r" % key)
        _check(isinstance(text, str), "[tunings] %s must be a tuning name, notes or semitones" % key)
        try:
            offsets = tuning_offsets(text)
        except ValueError as e:
            raise ConfigError("[tunings] %s: %s" % (key, e))
        _check_offsets(offsets, keep, "[tunings] %s" % key)
        config["tunings"][int(key)] = offsets

    for key, patch in data.get("patch", {}).items():
        _check(key.isdigit() and 0 <= int(key) <= 127, "[patch.%s]: patch numbers are program changes 0-127" % key)
        config["patch"][int(key)] = _validate_patch(key, patch, keep)
    return config


def _validate_patch(key, patch, keep):
    where = "[patch.%s]" % key
    _check(isinstance(patch, dict), "%s must be a table of settings" % where)
    unknown = set(patch) - PATCH_FIELDS
    _check(not unknown, "%s: unknown setting %s; settings are %s" % (where, _names(unknown), _names(PATCH_FIELDS)))
    _check(not ("model" in patch and "program" in patch), "%s: use either model or program, not both" % where)
    _check(not ("tuning" in patch and "strings" in patch), "%s: use either tuning or strings, not both" % where)
    try:
        if "model" in patch:
            _check(isinstance(patch["model"], str), "%s: model must be a name like \"lester 5\"" % where)
            jtv.parse_model_name(patch["model"])
        if "program" in patch:
            _check(_is_int(patch["program"]) and 0 <= patch["program"] <= 104, "%s: program must be 0-104" % where)
        for name in ("volume", "tone"):
            if name in patch:
                _check(_is_int(patch[name]) and 0 <= patch[name] <= 127, "%s: %s must be 0-127" % (where, name))
        if "strings" in patch:
            _check(isinstance(patch["strings"], str), "%s: strings must be text like \"D A D G A D\"" % where)
            _check_offsets(jtv.parse_tuning_text(patch["strings"]), keep, where)
        if "tuning" in patch:
            _check(isinstance(patch["tuning"], str), "%s: tuning must be a name" % where)
            known = jtv.find_factory_tuning(patch["tuning"])
            if known:
                _check_offsets(known[1], keep, where)
        if "twelve_string" in patch:
            _check(isinstance(patch["twelve_string"], bool), "%s: twelve_string must be true or false" % where)
        if "modeling" in patch:
            _check(isinstance(patch["modeling"], bool),
                   "%s: modeling must be true or false (false: the magnetic pickups)" % where)
    except ValueError as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError("%s: %s" % (where, e))
    return dict(patch)


def _check_offsets(offsets, keep, where):
    _check(all(-12 <= o <= 12 for o in offsets), "%s: string offsets must be within -12 to +12 semitones" % where)
    if keep:
        _check(all(abs(o - round(o)) < 0.01 for o in offsets),
               '%s: tuning_method = "keep" takes whole semitones only' % where)


def _check(condition, message):
    if not condition:
        raise ConfigError(message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _names(names):
    return ", ".join(sorted(names))
