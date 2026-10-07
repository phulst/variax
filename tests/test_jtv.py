"""Program numbering and name lookup (no guitar needed)."""

import pytest

from variax import jtv


# Program numbers from the "Variax MIDI reference" spreadsheet (JTV & Standard sheet).
@pytest.mark.parametrize("name, program", [
    ("custom 1 5", 0), ("Custom1 1", 4), ("T-Model 5", 5), ("tmodel 1", 9),
    ("Spank 1", 14), ("lester 5", 15), ("Lester-2", 18), ("Rbilly 3", 27), ("R-BILLY 3", 27),
    ("Jazzbox 1", 44), ("acoustic 1", 49), ("Reso 1", 54), ("custom 2 1", 59),
    ("factory spank 5", 60), ("factory Lester 5", 65), ("FACTORY reso 1", 104),
])
def test_parse_model_name(name, program):
    assert jtv.parse_model_name(name) == program


@pytest.mark.parametrize("name", ["strat 1", "lester", "lester 6", "factory t-model 1", ""])
def test_parse_model_name_rejects(name):
    with pytest.raises(ValueError):
        jtv.parse_model_name(name)


def test_program_positions_round_trip():
    for program in range(60):
        assert jtv.position_to_program(*jtv.program_to_position(program)) == program


def test_all_programs():
    programs = list(jtv.all_programs())
    assert [p for p, _, _ in programs] == list(range(105))
    assert programs[44][1:] == ("Jazzbox 1", "1954 ES-175, bridge")
    assert programs[60][1] == "factory Spank 5"


@pytest.mark.parametrize("name, found", [
    ("dadgad", "DADGAD"), ("Drop D", "DROP D"), ("drop-d", "DROP D"), ("1/2 down", "HALF DOWN"),
    ("half down", "HALF DOWN"), ("blues g", "BLUES"), ("reso g", "RESO"), ("my custom", None),
    ("drop c", "DROP C"), ("Drop B", "DROP B"), ("drop bb", "DROP Bb"), ("DROP-Bb", "DROP Bb"),
    ("m3 down", "m3 DOWN"), ("M3 down", "M3 DOWN"), ("m3down", "m3 DOWN"), ("M3-DOWN", "M3 DOWN"),
    ("minor 3rd down", "m3 DOWN"), ("Major Third Down", "M3 DOWN"), ("maj3 down", "M3 DOWN"),
])
def test_find_factory_tuning(name, found):
    result = jtv.find_factory_tuning(name)
    assert (result[0] if result else None) == found


@pytest.mark.parametrize("text, offsets", [
    ("-1 -1 -1 -1 -1 -1", [-1] * 6),
    ("-0.5, 0, 0, 0, 0, 0.25", [-0.5, 0, 0, 0, 0, 0.25]),
    ("E A D G B E", [0] * 6),
    ("E B E G# B E", [0, 2, 2, 1, 0, 0]),                      # open E
    ("Eb Ab Db Gb Bb Eb", [-1] * 6),
    ("E♭ A♭ D♭ G♭ B♭ E♭", [-1] * 6),
    ("d a d f# a d", [-2, 0, 0, -1, -2, -2]),                  # open D, lower case
    ("B E A D F# B", [-5] * 6),                                # baritone: nearest pitch is down
    ("D2 A2 D3 G3 A3 D4", [-2, 0, 0, 0, -2, -2]),              # with octaves
    ("E1 A1 D2 G2 B2 E3", [-12] * 6),                          # an octave down needs octaves
    ("-2 A D G B E", [-2, 0, 0, 0, 0, 0]),                     # mixed
])
def test_parse_tuning_text(text, offsets):
    assert jtv.parse_tuning_text(text) == offsets


@pytest.mark.parametrize("text", ["E A D G B", "E A D G B E E", "E A D G B H", "E A D G B x"])
def test_parse_tuning_text_rejects(text):
    with pytest.raises(ValueError):
        jtv.parse_tuning_text(text)


@pytest.mark.parametrize("offsets, notes", [
    ([0] * 6, "E A D G B E"), ([-1] * 6, "Eb Ab Db Gb Bb Eb"), ([-3, -1, -1, -1, -1, -1], "Db Ab Db Gb Bb Eb"),
    ([-2, 0, 0, -1, -2, -2], "D A D F# A D"), ([0, 2, 2, 1, 0, 0], "E B E G# B E"),
    ([0, 0, -1, -3, -2, 0], "E A C# E A E"), ([-5] * 6, "B E A D F# B"), ([-0.5, 0, 0, 0, 0, 0], None),
])
def test_offsets_to_notes(offsets, notes):
    assert jtv.offsets_to_notes(offsets) == notes


# The Pilot's Guide charts, low to high string (JTV-89 DROP Db as on the JTV-59/69 chart).
PILOTS_GUIDE_TUNINGS = {
    "STANDARD": "E A D G B E", "DROP D": "D A D G B E", "HALF DOWN": "Eb Ab Db Gb Bb Eb",
    "DROP Db": "Db Ab Db Gb Bb Eb", "ONE DOWN": "D G C F A D", "DADGAD": "D A D G A D",
    "OPEN D": "D A D F# A D", "BLUES": "D G D G B D", "RESO": "G B D G B D", "OPEN A": "E A C# E A E",
    "BARITONE": "B E A D F# B", "DROP C": "C G C F A D", "m3 DOWN": "Db Gb B E Ab Db",
    "DROP B": "B Gb B E Ab Db", "M3 DOWN": "C F Bb Eb G C", "DROP Bb": "Bb F Bb Eb G C",
}


def test_factory_tunings_match_the_pilots_guide():
    assert set(jtv.FACTORY_TUNINGS) == set(PILOTS_GUIDE_TUNINGS)
    assert set(jtv.KNOB_TUNINGS_JTV59_69) | set(jtv.KNOB_TUNINGS_JTV89) == set(jtv.FACTORY_TUNINGS)
    for name, notes in PILOTS_GUIDE_TUNINGS.items():
        assert jtv.FACTORY_TUNINGS[name] == jtv.parse_tuning_text(notes), name
        assert jtv.offsets_to_notes(jtv.FACTORY_TUNINGS[name]) == notes, name
