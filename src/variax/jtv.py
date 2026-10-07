"""James Tyler Variax (JTV-59/69) model and tuning names, from the JTV Pilot's Guide.

The guitar reports the model knob and pickup selector together as one Program
Change: program = knob_index * 5 + slot, with knob_index 0..11 (Custom 1 ..
Custom 2) and slot 0..4. The Pilot's Guide numbers pickup positions
1 = bridge .. 5 = neck, and slot 4 is the bridge position, so
position = 5 - slot.
"""

import re

# Model knob positions in knob order. Each bank lists the factory model for
# pickup positions 1 (bridge) to 5 (neck). The custom banks are user defined.
BANKS = [
    ("Custom 1", None),
    ("T-Model", [
        "1960 Telecaster Custom, bridge",
        "1960 Telecaster Custom, widerange humbucker bridge",
        "1960 Telecaster Custom, bridge + neck",
        "1960 Telecaster Custom, widerange humbucker neck",
        "1960 Telecaster Custom, neck",
    ]),
    ("Spank", [
        "1959 Stratocaster, bridge",
        "1959 Stratocaster, bridge + middle",
        "1959 Stratocaster, middle",
        "1959 Stratocaster, neck + middle",
        "1959 Stratocaster, neck",
    ]),
    ("Lester", [
        "1959 Les Paul Standard, bridge",
        "1959 Les Paul Standard, P90 bridge",
        "1959 Les Paul Standard, bridge + neck",
        "1959 Les Paul Standard, P90 neck",
        "1959 Les Paul Standard, neck",
    ]),
    ("Special", [
        "1955 Les Paul Special, bridge",
        "1976 Firebird V, bridge",
        "1955 Les Paul Special, bridge + neck",
        "1976 Firebird V, neck",
        "1955 Les Paul Special, neck",
    ]),
    ("R-Billy", [
        "1959 Gretsch 6120, bridge",
        "1959 Gretsch Duo Jet, bridge",
        "1959 Gretsch 6120, bridge + neck",
        "1959 Gretsch Duo Jet, neck",
        "1959 Gretsch 6120, neck",
    ]),
    ("Chime", [
        "1966 Rickenbacker 370, bridge",
        "1966 Rickenbacker 370-12, bridge",
        "1966 Rickenbacker 370, bridge + neck",
        "1966 Rickenbacker 370-12, neck",
        "1966 Rickenbacker 370, neck",
    ]),
    ("Semi", [
        "1961 ES-335, bridge",
        "1964 Epiphone Casino, bridge",
        "1961 ES-335, bridge + neck",
        "1964 Epiphone Casino, neck",
        "1961 ES-335, neck",
    ]),
    ("Jazzbox", [
        "1954 ES-175, bridge",
        "1953 Super 400, bridge",
        "1954 ES-175, bridge + neck",
        "1953 Super 400, neck",
        "1954 ES-175, neck",
    ]),
    ("Acoustic", [
        "1959 Martin D-28",
        "1970 Martin D12-28 (12-string)",
        "1967 Martin O-18",
        "1966 Guild F212 (12-string)",
        "1995 Gibson J-200",
    ]),
    ("Reso", [
        "1935 Dobro Model 32",
        "Coral Sitar",
        "1999 Jerry Jones Shorthorn",
        "Gibson Mastertone banjo",
        "1928 National Tricone",
    ]),
    ("Custom 2", None),
]

# Factory tunings of all JTV models (Pilot's Guide), by the names the guitar
# stores for them: semitones per string, low E first. The JTV-89's DROP Db is
# printed as "Db Ab Eb Gb Bb Eb" in the Pilot's Guide, which looks like a
# misprint for the JTV-59/69's Db Ab Db Gb Bb Eb.
FACTORY_TUNINGS = {
    "STANDARD": [0, 0, 0, 0, 0, 0],             # E A D G B E
    "DROP D": [-2, 0, 0, 0, 0, 0],              # D A D G B E
    "HALF DOWN": [-1, -1, -1, -1, -1, -1],      # Eb Ab Db Gb Bb Eb
    "DROP Db": [-3, -1, -1, -1, -1, -1],        # Db Ab Db Gb Bb Eb
    "ONE DOWN": [-2, -2, -2, -2, -2, -2],       # D G C F A D
    "DADGAD": [-2, 0, 0, 0, -2, -2],            # D A D G A D
    "OPEN D": [-2, 0, 0, -1, -2, -2],           # D A D F# A D
    "BLUES": [-2, -2, 0, 0, 0, -2],             # D G D G B D
    "RESO": [3, 2, 0, 0, 0, -2],                # G B D G B D
    "OPEN A": [0, 0, -1, -3, -2, 0],            # E A C# E A E
    "BARITONE": [-5, -5, -5, -5, -5, -5],       # B E A D F# B
    "DROP C": [-4, -2, -2, -2, -2, -2],         # C G C F A D
    "m3 DOWN": [-3, -3, -3, -3, -3, -3],        # Db Gb B E Ab Db
    "DROP B": [-5, -3, -3, -3, -3, -3],         # B Gb B E Ab Db
    "M3 DOWN": [-4, -4, -4, -4, -4, -4],        # C F Bb Eb G C
    "DROP Bb": [-6, -4, -4, -4, -4, -4],        # Bb F Bb Eb G C
}
# The factory tunings on the tuning knob, slots 1-11.
KNOB_TUNINGS_JTV59_69 = ["STANDARD", "DROP D", "HALF DOWN", "DROP Db", "ONE DOWN", "DADGAD", "OPEN D",
                         "BLUES", "RESO", "OPEN A", "BARITONE"]
KNOB_TUNINGS_JTV89 = ["STANDARD", "DROP D", "HALF DOWN", "DROP Db", "ONE DOWN", "DROP C", "m3 DOWN",
                      "DROP B", "M3 DOWN", "DROP Bb", "BARITONE"]
def format_strings(offsets):
    """A tuning as notes ("D A D G A D"), or as semitones ("-0.5 +0 +0 +0 +0 +0") if not whole."""
    return offsets_to_notes(offsets) or " ".join("%+g" % round(o, 2) for o in offsets)


# Other names for the same tunings (the Pilot's Guide's, and spelled-out ones).
TUNING_ALIASES = {
    "1/2 DOWN": "HALF DOWN", "1 DOWN": "ONE DOWN", "BLUES G": "BLUES", "RESO G": "RESO",
    "MINOR 3RD DOWN": "m3 DOWN", "MINOR THIRD DOWN": "m3 DOWN", "MIN3 DOWN": "m3 DOWN",
    "MAJOR 3RD DOWN": "M3 DOWN", "MAJOR THIRD DOWN": "M3 DOWN", "MAJ3 DOWN": "M3 DOWN",
}


def find_factory_tuning(name):
    """(name, offsets low E first) of a factory tuning, matched loosely; None if unknown.

    Case doesn't matter, except that "m3 down" (minor third) and "M3 down"
    (major third) are told apart by the case of the m.
    """
    key = _normalize(name)
    if key == "m3down":
        found = "M3 DOWN" if name.strip()[:1] == "M" else "m3 DOWN"
        return found, FACTORY_TUNINGS[found]
    names = {_normalize(n): n for n in FACTORY_TUNINGS if _normalize(n) != "m3down"}
    names.update({_normalize(alias): n for alias, n in TUNING_ALIASES.items()})
    found = names.get(key)
    return (found, FACTORY_TUNINGS[found]) if found else None


# Programs 60-104 select the factory version of a model, whatever is stored on
# the knob: Spank to Reso, 5 per bank, position 5 (neck) first like the knob.
FACTORY_FIRST_PROGRAM = 60
FACTORY_BANKS = ["Spank", "Lester", "Special", "R-Billy", "Chime", "Semi", "Jazzbox", "Acoustic", "Reso"]


def factory_program(bank, pickup_position):
    """Program number of a factory model, or None if the bank has no factory programs."""
    names = [_normalize(b) for b in FACTORY_BANKS]
    if _normalize(bank) not in names:
        return None
    return FACTORY_FIRST_PROGRAM + names.index(_normalize(bank)) * 5 + (5 - pickup_position)


def program_to_position(program):
    """Return (knob_index 0..11, pickup position 1..5) for a program number."""
    return program // 5, 5 - program % 5


def position_to_program(knob_index, pickup_position):
    return knob_index * 5 + (5 - pickup_position)


def _normalize(name):
    return "".join(c for c in name.lower() if c.isalnum())


def bank_index(name):
    """Knob index for a bank name ("Lester", "r-billy", "TMODEL", "custom1"), or None."""
    wanted = _normalize(name)
    for index, (bank, _) in enumerate(BANKS):
        if _normalize(bank) == wanted:
            return index
    return None


def describe_program(program):
    if FACTORY_FIRST_PROGRAM <= program < FACTORY_FIRST_PROGRAM + 5 * len(FACTORY_BANKS):
        index, position = program_to_position(program - FACTORY_FIRST_PROGRAM)
        bank = FACTORY_BANKS[index]
        models = dict(BANKS)[bank]
        return "factory %s %d: %s" % (bank, position, models[position - 1])
    knob_index, position = program_to_position(program)
    if knob_index >= len(BANKS):
        return "unknown program %d" % program
    bank, models = BANKS[knob_index]
    model = models[position - 1] if models else "user model"
    return "%s %d: %s" % (bank, position, model)


_MODEL_NAME = re.compile(r"^\s*(factory\s+)?(.+?)[\s-]*([1-5])\s*$", re.IGNORECASE)


def parse_model_name(text):
    """Program number for a model name like "Rbilly 3", "R-Billy-3", "custom 1 3" or "factory spank 5"."""
    match = _MODEL_NAME.match(text)
    if not match:
        raise ValueError("%r is not a model name; use a bank and a pickup position 1-5, e.g. \"lester 5\"" % text)
    factory, bank, position = match.group(1), match.group(2), int(match.group(3))
    if factory:
        program = factory_program(bank, position)
        if program is None:
            raise ValueError("no factory programs for %r; banks: %s" % (bank, ", ".join(FACTORY_BANKS)))
        return program
    index = bank_index(bank)
    if index is None:
        raise ValueError("unknown bank %r; banks: %s" % (bank, ", ".join(name for name, _ in BANKS)))
    return position_to_program(index, position)


def all_programs():
    """(program, label, model description) for every program: the 60 knob positions, then the factory ones."""
    for program in range(len(BANKS) * 5):
        knob_index, position = program_to_position(program)
        bank, models = BANKS[knob_index]
        yield program, "%s %d" % (bank, position), models[position - 1] if models else "user model"
    for i, bank in enumerate(FACTORY_BANKS):
        models = dict(BANKS)[bank]
        for position in range(5, 0, -1):
            yield (FACTORY_FIRST_PROGRAM + i * 5 + 5 - position, "factory %s %d" % (bank, position),
                   models[position - 1])


# Standard tuning, low E string first, as MIDI note numbers (E2 A2 D3 G3 B3 E4).
STANDARD_NOTES = [40, 45, 50, 55, 59, 64]
NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_PITCH_CLASSES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE = re.compile(r"^([A-Ga-g])([#b♯♭]{0,2})(-?\d)?$")
_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")


def parse_tuning_text(text):
    """Semitone offsets per string (low E first) from text such as "-2 0 0 0 -2 -2",
    "D A D G A D", "Eb Ab Db Gb Bb Eb" or "D2 A2 D3 G3 A3 D4".

    A note without an octave is taken as the nearest pitch to the standard
    string, at most a tritone up or down (so B on the low E string is -5); add
    the octave for anything further. Numbers and notes can be mixed.
    """
    tokens = [t for t in re.split(r"[\s,]+", text.strip()) if t]
    if len(tokens) != 6:
        raise ValueError("give six strings, low E first, e.g. 'D A D G A D' or '-2 0 0 0 -2 -2'")
    offsets = []
    for token, standard in zip(tokens, STANDARD_NOTES):
        if _NUMBER.match(token):
            offsets.append(float(token))
            continue
        match = _NOTE.match(token)
        if not match:
            raise ValueError("%r is neither a number of semitones nor a note like 'Eb' or 'G#3'" % token)
        letter, accidentals, octave = match.groups()
        pitch = _PITCH_CLASSES[letter.upper()]
        pitch += sum(1 if a in "#♯" else -1 for a in accidentals)
        if octave is not None:
            offsets.append((int(octave) + 1) * 12 + pitch - standard)
        else:
            offsets.append((pitch - standard + 6) % 12 - 6)
    return offsets


def offsets_to_notes(offsets):
    """Note names for whole-semitone offsets ("D A D G A D"), or None if any offset is fractional."""
    if any(abs(o - round(o)) > 0.01 for o in offsets):
        return None
    steps = [round(o) for o in offsets]
    names = NOTE_NAMES
    if all(o <= -1 for o in steps) and -3 <= steps[5] <= -1:  # tuned down to Eb, D or Db: flats
        names = FLAT_NAMES
    elif any(steps) and all(o >= 0 for o in steps):  # only strings tuned up: open E
        names = SHARP_NAMES
    return " ".join(names[(standard + o) % 12] for o, standard in zip(steps, STANDARD_NOTES))
