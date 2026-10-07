"""James Tyler Variax (JTV-59/69) model and tuning names, from the JTV Pilot's Guide.

The guitar reports the model knob and pickup selector together as one Program
Change: program = knob_index * 5 + slot, with knob_index 0..11 (Custom 1 ..
Custom 2) and slot 0..4. The Pilot's Guide numbers pickup positions
1 = bridge .. 5 = neck, and slot 4 is the bridge position, so
position = 5 - slot.
"""

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

# Alternate tuning knob positions, as reported in CC84 (0..11): MODEL plus the
# JTV-59/69 factory tunings in the order of the Pilot's Guide table. Positions
# other than MODEL and STANDARD can be overwritten with custom tunings.
TUNINGS = [
    "MODEL (tuning comes from the model)",
    "STANDARD  E A D G B E",
    "DROP D  D A D G B E",
    "1/2 DOWN  Eb Ab Db Gb Bb Eb",
    "DROP Db  Db Ab Db Gb Bb Eb",
    "1 DOWN  D G C F A D",
    "DADGAD  D A D G A D",
    "OPEN D  D A D F# A D",
    "BLUES G  D G D G B D",
    "RESO G  G B D G B D",
    "OPEN A  E A C# E A E",
    "BARITONE  B E A D F# B",
]


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
    knob_index, position = program_to_position(program)
    if knob_index >= len(BANKS):
        return "unknown program %d" % program
    bank, models = BANKS[knob_index]
    model = models[position - 1] if models else "user model"
    return "%s %d: %s" % (bank, position, model)


def describe_tuning(value):
    if value < len(TUNINGS):
        return TUNINGS[value]
    return "unknown tuning %d" % value
