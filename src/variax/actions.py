"""What to send for a model, volume, tone, tuning or 12-string change; shared by `variax send` and
`variax midi`."""

from . import jtv, protocol
from .interface import VariaxError


def tuning_messages(offsets, keep=False):
    """Messages that set a tuning (six semitone offsets, low E first).

    keep=False: the current model's tuning (Workbench's write plus tuning on);
    only heard with the tuning knob on MODEL, reset by a model change.
    keep=True: the on-the-fly tuning SysEx; whole semitones, heard with the
    knob anywhere, kept through model changes until the knob is turned.
    """
    if keep:
        return [protocol.fly_tuning_message(offsets)]
    return [protocol.set_strings_message(offsets), protocol.tuning_enable_message(True)]


def no_tuning_messages(keep=False):
    """Messages for tuning "none": no pitch shift, the strings sound as physically tuned."""
    if keep:
        return [protocol.fly_tuning_message([0] * 6)]
    return [protocol.tuning_enable_message(False)]


def plan_send(program=None, name=None, volume=None, tone=None, tuning=None, strings=None, keep=False,
              twelve_string=None, modeling=None, raw=()):
    """The messages to send, in order: modeling, model, volume, tone, tuning, 12-string, raw.

    twelve_string and modeling are True (on), False (off) or None (leave as it is); modeling off
    means the magnetic pickups.

    Steps that need to read from the guitar first appear as ("tuning", name)
    for a tuning to look up on the knob and ("twelve-string", on) for the
    12-string switch, which changes only its own bits in the model's flags word.
    """
    messages = []
    if modeling is not None:
        messages.append(protocol.MODELING_MESSAGE if modeling else protocol.MAGNETIC_MESSAGE)
    if name is not None:
        program = jtv.parse_model_name(name)
    if program is not None:
        messages.append(protocol.program_change(program))
    if volume is not None:
        messages.append(protocol.control_change(protocol.VOLUME_CC, volume))
    if tone is not None:
        messages.append(protocol.control_change(protocol.TONE_CC, tone))
    if strings is not None:
        messages += tuning_messages(strings, keep)
    elif tuning is not None:
        if tuning.strip().lower() == "none":
            messages += no_tuning_messages(keep)
        else:
            known = jtv.find_factory_tuning(tuning)
            messages += tuning_messages(known[1], keep) if known else [("tuning", tuning)]
    if twelve_string is not None:
        messages.append(("twelve-string", bool(twelve_string)))
    for hex_message in raw:
        try:
            messages.append(bytes.fromhex(hex_message))
        except ValueError:
            raise ValueError("--raw %r is not hex bytes" % hex_message)
    return messages


def patch_arguments(patch):
    """plan_send arguments for a [patch.N] from variax.toml (already validated)."""
    arguments = {}
    if "model" in patch:
        arguments["name"] = patch["model"]
    if "program" in patch:
        arguments["program"] = patch["program"]
    for key in ("volume", "tone", "tuning", "twelve_string", "modeling"):
        if key in patch:
            arguments[key] = patch[key]
    if "strings" in patch:
        arguments["strings"] = jtv.parse_tuning_text(patch["strings"])
    return arguments


def find_tuning(tunings, name):
    """Offsets of the tuning called `name` among {slot: (name, offsets)}, matched loosely."""
    wanted = "".join(c for c in name.lower() if c.isalnum())
    for slot in sorted(tunings):
        tuning_name, offsets = tunings[slot]
        if "".join(c for c in tuning_name.lower() if c.isalnum()) == wanted:
            return offsets
    known = ", ".join(tunings[s][0] for s in sorted(tunings))
    raise VariaxError("No tuning called %r on the guitar. It has: %s" % (name, known))


def resolve(link, step, keep=False, knob_tunings=None):
    """The messages for one planned step, reading from the guitar where needed.

    knob_tunings: {slot: (name, offsets)} if already known; otherwise read from the guitar.
    """
    if step[0] == "tuning":
        offsets = find_tuning(knob_tunings if knob_tunings is not None else link.read_tunings(), step[1])
        return tuning_messages(offsets, keep)
    if step[0] == "twelve-string":
        flags = link.read_words(protocol.FLAGS_ADDRESS, 1)[0]
        return protocol.twelve_string_messages(step[1], flags=flags)
    return [step]
