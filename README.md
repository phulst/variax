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

## What we know

**The interface.** USB `0e41:534d`, vendor-specific class, so macOS never shows
it as a MIDI port and no Line 6 driver is needed; we use libusb directly. After
selecting alternate setting 1 of interface 0 it carries **raw MIDI bytes** over
interrupt endpoints OUT `0x01` and IN `0x82` (32-byte packets). The Linux
kernel driver `sound/usb/line6/variax.c` supports this device and is where the
handshake comes from.

**Handshake.**

1. Send `F0 7E 7F 06 01 F7` (Universal Identity Request) until the guitar
   answers `F0 7E 7F 06 02 00 01 0C 07 00 05 00 30 32 32 33 F7`
   (Line 6, family 7, member 5, firmware "0223").
2. Send `F0 00 01 0C 07 00 2A 01 F7` (activate). Before this the guitar sends
   nothing. The activation survives switching the guitar off and on; not yet
   tested whether it survives unplugging the USB interface.

**What the guitar reports (channel 1), from one capture:**

| Control | Message | Notes |
|---|---|---|
| Model knob | Program Change, steps of 5 (4, 9, … 59 for Custom 1 … Custom 2) | followed by CC79 |
| Pickup selector | Program Change within a group of 5 (40, 42, 44) | followed by CC79 |
| Tuning knob | CC84 = position − 1 (0–11, 12 positions) | |
| Tuning-knob push (white, then blue light) | `FF` (reset), then Program Change and CC79 | on a JTV-59 this toggles the 3-way selector between models 1-3-5 and 2-3-4 |
| Power-on | CC7 (volume) ramping 64 → 127 in ~60 ms | a fade-in, not the volume knob; the same whether the light comes on white or blue (the guitar keeps the last state) |
| Volume, tone | nothing seen | |

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

CC79 follows every program change and its value belongs to the program:
usually 127, but 51 for programs 2 (Custom 1, position 3) and 45 (Acoustic 5,
J-200) and 108 for program 47 (Acoustic 3, O-18). Best guess: the model's
output level, which the Pilot's Guide says depends on the modeled instrument.

Unconfirmed: what CC79 really is, and whether the guitar accepts the same
messages to change model and tuning.

The Helix controls the Variax on its own MIDI channel 16, but that is the
Helix's side; on the VDI/USB side the guitar uses channel 1.

## Caution

Only send messages that we have seen the guitar or Workbench use. Large SysEx
transfers are probably flash or firmware writes.
