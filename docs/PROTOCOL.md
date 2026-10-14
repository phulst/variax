# Variax USB protocol notes

How the `variax` tool talks to a James Tyler Variax, as worked out by
monitoring the guitar, the Linux kernel drivers, captures of Workbench HD's
USB traffic and a community spreadsheet. Tested on a JTV-59 that reports
firmware "0223". The code is in [`src/variax/protocol.py`](../src/variax/protocol.py).

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
   tested whether it survives unplugging the USB interface. According to the
   community spreadsheet, the guitar receives messages without it.

On macOS the interface falls back to alternate setting 0 whenever a program
releases it, so every connection selects setting 1 again. That resets the
host's USB data toggles but not always the interface's, so the first packet
in either direction is sometimes dropped as a duplicate. The identity request
absorbs this: it is retried every 80 ms until answered (replies take 15–40
ms), so the messages that matter come after it.

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
`variax monitor` prints. The names are in
[`src/variax/jtv.py`](../src/variax/jtv.py).

CC7 is volume and CC79 is tone (`VARIAXMIDI_volume` and `VARIAXMIDI_tone` in
the old Linux staging driver, `drivers/staging/line6/control.h` in v2.6.32).
After every program change the guitar re-applies the tone knob's physical
position and reports it as CC79, overriding a tone value sent earlier. (An
early sweep showed 51 and 108 for a few programs; not yet explained.) On
acoustic models the tone knob moves a modeled microphone.

The guitar accepts Program Change on channel 1 to select a model (the old
driver sent it the same way), and CC7 and CC79 to set volume and tone.
Sending CC84 does not change the tuning; CC84 only reports the tuning knob.

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

**Command 3C is a generic read.** The two model data requests are exactly
`F0 00 01 0C 07 00 3C <word count> <word address> F7` (header fields as in
the write below): 32 words at `0x353` and 32 at `0x373`. The reply,
`F0 00 01 0C 07 05 3C <words> F7`, holds just the words. Reads at other
addresses work too (tested at `0x001`, `0x41C`, `0x422`), and they return the
working copy: a tuning written with command 43 reads back straight away.
`variax tunings` uses this to show the current model's tuning. One read
returns up to 256 words (512 gets no answer); `variax read ADDRESS COUNT`
reads any range in chunks of 128 and shows each word as hex, signed integer,
24-bit float and text. The model name is at `0x353`–`0x358`, as text.

**Tunings (from a Workbench HD USB capture on Windows).** Workbench addresses
the guitar as `F0 00 01 0C 07 05` (the guitar's own address; we send `07 00`).

- Set the current model's string tuning (heard when the tuning knob is on
  MODEL; confirmed by ear with `variax send -s '-5 -5 -5 -5 -5 -5'`):
  `F0 00 01 0C 07 05 43 06 00 00 00 00 00 0C 01 04 00 00 00` + six 24-bit
  pitch offsets, **high E string first** + `F7`. The guitar answers
  `F0 00 01 0C 07 05 71 F7`. `protocol.set_strings_message()` rebuilds all
  eight captured messages byte for byte.
- Read tuning knob slot 1–11: `F0 00 01 0C 07 05 1B <slot> F7`. The reply has
  the six offsets (high E first) and an 18-character name. The factory names
  are STANDARD, DROP D, HALF DOWN, DROP Db, ONE DOWN, DADGAD, OPEN D, BLUES,
  RESO, OPEN A and BARITONE.
- A 24-bit value is sent as six 4-bit nibbles, least significant first. A
  pitch offset is signed with 2²³ = one octave, so one semitone is 2²³/12.
  Names use the same 3-bytes-in-6-nibbles packing as the model data.

**Acknowledgements.** Only writes (command 43) are acknowledged, with
`F0 00 01 0C 07 05 71 F7` after about 40 ms. The on-the-fly tuning, the
magnetic/modeling switch, Program Change and CCs get no reply. A one-word
write plus its acknowledgement takes about 40 ms, so about 25 writes per
second get through.

**Writes are not saved.** Command 43 changes the guitar's working copy of
the current model. Switching to another model and back reloads the stored
model, with its stored tuning and Parallel Pitch. So tuning and 12-string
have to be sent after every model change (`variax send` does this in one
command); stored presets are never changed. Workbench's save step (writing to the guitar's storage)
has not been captured.

**Command 43 is a generic write** (from a second capture, toggling Tuning
and Parallel Pitch in Workbench):
`F0 00 01 0C 07 05 43 <word count> <word address> <words> F7`, each of the
two header fields a 24-bit word like the data. Addresses seen so far (words;
per-string values high E first):

| Address | Words | Contents |
|---|---|---|
| `0x001` | 1 | flags; Parallel Pitch is bits `0x080010` (captured: on `0x090BFF`, off `0x010BEF`) |
| `0x2AE` | 78 | Parallel Pitch: 6 small values per string, 60 values (10 per string) that look like filter coefficients, 6 dry levels (0.7), 6 wet levels (0.3 = mix 30%) |
| `0x41C` | 6 | string tuning offsets |
| `0x422` | 1 | Tuning on/off (Workbench's power button), 0 or 1 |

Workbench sends the 78 Parallel Pitch words, then the flag, to turn it on, and
only the flag to turn it off. The Parallel Pitch pitch (+12 +12 +12 +12 0 0)
and cents (−5 −5 −5 −7 −3 −4) settings don't appear as plain numbers; Workbench
seems to compute the filter-like values from them. So
`variax send --twelve-string on` replays this one captured setting verbatim;
on and off work on the guitar (tested by ear). The flags word holds other
per-model bits too (`0x010BEF` in the capture, `0x011BEF` on another model),
so `variax` reads it first and only sets or clears `0x080010` (tested: `0x011BEF`
→ `0x091BFF` → `0x011BEF`).

The `5E` tuning on/off SysEx from a Helix thread (for the Variax Acoustic 700)
does nothing on the JTV.

**Captures** (Wireshark JSON exports of USBPcap captures on Windows, in
[`captures/`](../captures/); the tests in `tests/` check the encoding against
them):

- `workbench-tunings.json`: Workbench reading the 11 knob tunings (`1B`) and
  setting STANDARD, DROP D, HALF DOWN, DROP Db, ONE DOWN and DADGAD (`43`).
- `workbench-tuning-toggle-parallel-pitch.json`: Tuning on/off three times,
  then Parallel Pitch on/off twice with the settings in
  `workbench-parallel-pitch-12string.png`.

**Community reference.** A spreadsheet, "Variax MIDI reference" (reverse
engineered from VDI traffic; on-the-fly tuning credited to Joe Bear; the
message `variax send --keep` uses), agrees
with the findings above: channel 1, CC7/CC79, the program numbering, CC84 as
send-only, the activate message ("SendModus", `F0 00 01 0C 07 00 2A F7`) and
the tuning on/off write. It adds, all implemented in `variax send`:

- Magnetic pickups `F0 00 01 0C 07 00 52 00 F7`, modeling `… 52 01 F7` (not
  yet tested on a JTV-59).
- On-the-fly tuning `F0 00 01 0C 07 05 52 04` + six signed bytes, high E
  first, each as two nibbles high nibble first (`0F 0E` = −2) + `F7`. Whole
  semitones only. **Tested on a JTV-59: it works with the tuning knob in any
  position**, unlike Workbench's write, which is only heard on MODEL. It
  writes the same six words at `0x41C` (DROP D read back as −2 on the low E
  word, `0x421`), and the model's tuning switch at `0x422` read back as on
  afterwards. It is a guitar-wide override: it stays through model changes
  (unlike Workbench's write, which a model change reloads), until the tuning
  knob is turned, which loads that position's stored tuning again. The string order is confirmed by ear and by that read:
  of the spreadsheet's examples, "Blues G" is right and "Open D" is mislabeled.
- Programs 60–104: factory versions of Spank … Reso, 5 per bank (not yet
  tested on a JTV-59).

It labels the Parallel Pitch flag values the other way round ("tentative");
the capture shows bits `0x080010` set means on (Workbench sends the settings
block just before it). Its flag values also differ in other bits, as expected
for a per-model word.

## Caution

Only send messages that have been seen from the guitar or Workbench. Large
SysEx transfers are probably flash or firmware writes.
