# variax

Reverse-engineering the control protocol of a Line 6 James Tyler Variax (JTV),
with the goal of building a custom MIDI controller for models and tunings.
Talks to the guitar through the **Line 6 Variax USB Interface**.

## Setup

```bash
uv sync
```

## Monitor: `monitor.py`

Does the startup handshake, then prints every message the guitar sends with a
decoded description. Turn the guitar's knobs and watch.

```bash
uv run monitor.py                 # handshake, then print until Ctrl-C
uv run monitor.py --raw           # raw USB packets instead of decoded messages
uv run monitor.py --no-handshake  # listen only (the guitar stays silent)
uv run monitor.py --seconds 30    # stop after 30 seconds
```

## Send: `send.py`

Selects a model by name, or sends raw MIDI messages, then prints what comes
back. Only one script can use the interface at a time, so stop `monitor.py`
first.

```bash
uv run send.py lester 5              # bank name (any case, hyphen optional) + pickup position 1-5
uv run send.py R-BILLY 3
uv run send.py "C0 2C"               # raw MIDI message as hex
uv run send.py volume 100            # volume 0-127 (CC7)
uv run send.py spank 1 tone 64       # tone 0-127 (CC79), after the model change
uv run send.py tuning drop-d         # a tuning stored on the tuning knob, by name
uv run send.py strings -2 0 0 0 0 0  # any tuning: semitones per string, low E first
uv run send.py tuning off            # stop using the model's tuning
uv run send.py 12string              # 12-string sound; "12string off" to stop
uv run send.py spank 1 "B0 07 50"    # several in order
```

Banks: custom1, t-model, spank, lester, special, r-billy, chime, semi,
jazzbox, acoustic, reso, custom2. Pickup position 1 is the bridge, 5 the neck.
Tunings are set the way Workbench HD does it, as the current model's string
offsets plus switching the model's tuning on (address `0x422`; while it is
off, written offsets are ignored), and are heard **only with the tuning knob on MODEL** (any other knob
position plays the knob's own tuning). The 11 factory knob tunings are built
in (`jtv.KNOB_TUNINGS`, also under the Pilot's Guide names such as "1/2 down");
other names are looked up among the tunings stored on the guitar's knob.
Everything else is sent on channel 1. A model change re-applies the tone knob's
physical position, so send the tone after the model.

## Dump: `dump.py`

Reads the current model's settings from the guitar (read-only requests from
the old Linux staging driver) and decodes them. Save one dump and diff another
against it to find which bytes a setting lives in.

```bash
uv run dump.py                   # model name, bank, decoded fields, all 156 bytes
uv run dump.py --save std.json   # save the dump
uv run dump.py --diff std.json   # show bytes that differ from the saved dump
```

## What we know

**The interface.** USB `0e41:534d`, vendor-specific class, so macOS never shows
it as a MIDI port and no Line 6 driver is needed; we use libusb directly. After
selecting alternate setting 1 of interface 0 it carries **raw MIDI bytes** over
interrupt endpoints OUT `0x01` and IN `0x82` (32-byte packets). The Linux
kernel driver `sound/usb/line6/variax.c` supports this device and is where the
handshake comes from.

**Handshake.**

1. Send `F0 7E 7F 06 01 F7` (Universal Identity Request) until it answers
   `F0 7E 7F 06 02 00 01 0C 07 00 05 00 30 32 32 33 F7`
   (Line 6, family 7, member 5, firmware "0223"). The interface answers this
   itself, even with the guitar switched off.
2. Send `F0 00 01 0C 07 00 2A 01 F7` (activate). Before this the guitar sends
   nothing. The activation survives switching the guitar off and on; not yet
   tested whether it survives unplugging the USB interface.

**What the guitar reports (channel 1), from one capture:**

| Control | Message | Notes |
|---|---|---|
| Model knob | Program Change, steps of 5 (4, 9, … 59 for Custom 1 … Custom 2) | followed by CC79 (tone) |
| Pickup selector | Program Change within a group of 5 (40, 42, 44) | followed by CC79 (tone) |
| Tuning knob | CC84 = position − 1 (0–11, 12 positions) | |
| Tuning-knob push (white, then blue light) | `FF` (reset), then Program Change and CC79 | on a JTV-59 this toggles the 3-way selector between models 1-3-5 and 2-3-4 |
| Volume knob | CC7 = 0–127 | one message per step while turning |
| Tone knob | CC79 = 0–127 | one message per step while turning; also sent after every program change |
| Power-on | CC7 (volume) ramping 64 → 127 in ~60 ms | a fade-in; the same whether the light comes on white or blue (the guitar keeps the last state) |

Every combination of model knob and pickup selector is its own program (the
Pilot's Guide calls them the 60 Guitar Model preset locations), and the guitar
reports it as a single Program Change:

    program = knob_index × 5 + (5 − pickup_position)

- `knob_index` 0–11: Custom 1, T-Model, Spank, Lester, Special, R-Billy,
  Chime, Semi, Jazzbox, Acoustic, Reso, Custom 2.
- `pickup_position` 1–5 as in the Pilot's Guide, 1 = bridge, 5 = neck. The
  bridge (down) position gives the highest number in each group of five.
- On a JTV-59 the 3-way selector reaches positions 1-3-5, or 2-3-4 after
  pushing the tuning knob.

The tuning knob sends CC84 = 0–11: MODEL, then STANDARD and the ten factory
alternate tunings in the Pilot's Guide table order.

All model and tuning names were checked by ear on a JTV-59 against what
`monitor.py` prints.

[jtv.py](jtv.py) has the model and tuning names; `monitor.py` prints them.

CC7 is volume and CC79 is tone (`VARIAXMIDI_volume` and `VARIAXMIDI_tone` in
the old Linux staging driver, `drivers/staging/line6/control.h` in v2.6.32).
After every program change the guitar re-applies the tone knob's physical
position and reports it as CC79, overriding a tone value sent earlier. (An
early sweep showed 51 and 108 for a few programs; not yet explained.) On
acoustic models the tone knob moves a modeled microphone.

The guitar accepts Program Change on channel 1 to select a model (the old
driver sent it the same way), and CC7 and CC79 to set volume and tone. Sending CC84 does not change the tuning; CC84
only reports the tuning knob.

The Helix controls the Variax on its own MIDI channel 16, but that is the
Helix's side; on the VDI/USB side the guitar uses channel 1.

**Model data.** The old staging driver (`drivers/staging/line6/variax.c` in
Linux 2.6.32) reads a model's settings with two SysEx requests,
`F0 00 01 0C 07 00 3C 00 02 00 00 00 00 03 05 03 00 00 00 F7` and the same
with `07` in place of the second `05`, and the bank name with
`F0 00 01 0C 07 00 6D F7`. The JTV answers all three (replies start
`F0 00 01 0C 07 05 3C` / `… 6D`). The data comes as 4-bit nibbles, six
nibbles per three bytes: an 18-byte name ("Spank-2") and 156 bytes of
settings. The bank reply is plain ASCII ("U-SPANK"). Under the original
Variax layout the fields up to `volume_dump` decode sensibly on the JTV (for
Spank: capacitance 0.022, tone and volume pots 250); the tuning fields after
them do not, so the JTV layout differs from byte 50 on.

**Tunings (from a Workbench HD USB capture on Windows).** Workbench addresses
the guitar as `F0 00 01 0C 07 05` (the guitar's own address; we send `07 00`).

- Set the current model's string tuning (heard when the tuning knob is on
  MODEL; confirmed by ear with `strings -5 -5 -5 -5 -5 -5`):
  `F0 00 01 0C 07 05 43 06 00 00 00 00 00 0C 01 04 00 00 00` + six 24-bit
  pitch offsets, **high E string first** + `F7`. The guitar answers
  `F0 00 01 0C 07 05 71 F7`. `jtv.set_strings_message()` rebuilds all eight
  captured messages byte for byte.
- Read tuning knob slot 1–11: `F0 00 01 0C 07 05 1B <slot> F7`. The reply has
  the six offsets (high E first) and an 18-character name. Slots on this
  guitar: STANDARD, DROP D, HALF DOWN, DROP Db, ONE DOWN, DADGAD, OPEN D,
  BLUES, RESO, OPEN A, BARITONE (BARITONE holds −4 −2 −2 −2 −2 −2, not the
  manual's −5 on every string).
- A 24-bit value is sent as six 4-bit nibbles, least significant first. A
  pitch offset is signed with 2²³ = one octave, so one semitone is 2²³/12.
  Names use the same 3-bytes-in-6-nibbles packing as the model data.

**Writes are not saved.** Command 43 changes the guitar's working copy of
the current model. Switching to another model and back reloads the stored
model, with its stored tuning and Parallel Pitch. So send tuning and 12string
after every model change (`send.py lester 5 tuning dadgad`); stored presets
are never changed. Workbench's save step (writing to the guitar's storage)
has not been captured.

**Command 43 is a generic write** (from a second capture, toggling Tuning
and Parallel Pitch in Workbench):
`F0 00 01 0C 07 05 43 <word count> <word address> <words> F7`, each of the
two header fields a 24-bit word like the data. Addresses seen so far (words;
per-string values high E first):

| Address | Words | Contents |
|---|---|---|
| `0x001` | 1 | flags; Parallel Pitch on = `0x090BFF`, off = `0x010BEF` (bits `0x080010`) |
| `0x2AE` | 78 | Parallel Pitch: 6 small values per string, 60 values (10 per string) that look like filter coefficients, 6 dry levels (0.7), 6 wet levels (0.3 = mix 30%) |
| `0x41C` | 6 | string tuning offsets |
| `0x422` | 1 | Tuning on/off (Workbench's power button), 0 or 1 |

Workbench sends the 78 Parallel Pitch words, then the flag, to turn it on, and
only the flag to turn it off. The Parallel Pitch pitch (+12 +12 +12 +12 0 0)
and cents (−5 −5 −5 −7 −3 −4) settings don't appear as plain numbers; Workbench
seems to compute the filter-like values from them. So `send.py 12string`
replays this one captured setting verbatim. The flags word also holds other
bits, captured on one model; writing it may reset other on/off settings.

The `5E` tuning on/off SysEx from a Helix thread (for the Variax Acoustic 700)
does nothing on the JTV.

**Captures** (Wireshark JSON exports of USBPcap captures on Windows, in
`captures/`):

- `workbench-tunings.json`: Workbench reading the 11 knob tunings (`1B`) and
  setting STANDARD, DROP D, HALF DOWN, DROP Db, ONE DOWN and DADGAD (`43`).
- `workbench-tuning-toggle-parallel-pitch.json`: Tuning on/off three times,
  then Parallel Pitch on/off twice with the settings in
  `workbench-parallel-pitch-12string.png`.

## Powering the guitar

With the Variax USB Interface (unlike a Helix or POD HD) the guitar runs on
its battery, and the electronics only switch on with a 1/4" cable plugged into
the guitar's output jack. Without that, the interface still answers the
handshake but messages sent to the guitar do nothing.

## Caution

Only send messages that we have seen the guitar or Workbench use. Large SysEx
transfers are probably flash or firmware writes.
