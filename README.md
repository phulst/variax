# variax

Command line control for Line 6 James Tyler Variax (JTV) guitars through the
Line 6 Variax USB Interface: select models, set volume, tone and any tuning,
switch on a 12-string sound, and watch what the guitar's knobs send.

**It also works as a MIDI bridge.** Together with the Variax USB Interface,
`variax midi` lets any MIDI device or app (a guitar effects processor, a MIDI
foot controller, MainStage or a DAW) change the guitar's model and tuning,
for example on every patch change. Until now that needed a Line 6 Helix, POD
HD or another device with a VDI jack; now a Mac or Linux computer (even a
Raspberry Pi) running `variax` and the USB interface the guitar came with are
enough. See
[Control from MainStage, a DAW or a MIDI controller](#control-from-mainstage-a-daw-or-a-midi-controller).

Line 6 has retired the Variax line, including the USB interface and its
software. This is an unofficial community project to keep these guitars
useful. It is not affiliated with or endorsed by Line 6 or Yamaha.

## Requirements

- **macOS or Linux** (tested on a Raspberry Pi with Raspberry Pi OS 13).
  Linux needs a few extra steps; see [Linux and Raspberry Pi](#linux-and-raspberry-pi).
  Windows is not supported yet; see [Contributing](#contributing).
- Python 3.11 or newer.
- A Line 6 **Variax USB Interface**, connected to the guitar's VDI jack.
- The guitar switched on: with the USB interface the guitar runs on its
  battery, and only switches on with a 1/4" cable plugged into its output jack.
- No other program using the interface: close Line 6 Central and Workbench HD.

Tested on a JTV-59. Other JTV models and the Variax Standard use the same
interface and probably work; the model names in the output come from the
JTV-59/69 Pilot's Guide.

## Install

```bash
pip install variax
```

or with [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):
`uv tool install variax`, `pipx install variax`.

From a clone of this repository, install it as a command that runs the code
in the clone, so your changes take effect straight away:

```bash
uv tool install --editable .
```

### Linux and Raspberry Pi

1. Install the packages needed to build the MIDI library, and libusb:

   ```bash
   sudo apt install build-essential python3-dev pkg-config libasound2-dev libjack-jackd2-dev libusb-1.0-0
   ```

2. Install `variax`. Recent Debian-based systems, including Raspberry Pi OS,
   don't allow `pip install` outside a virtual environment, so use pipx
   (`sudo apt install pipx`, then `pipx install variax`) or a virtual
   environment:

   ```bash
   python3 -m venv ~/variax-venv
   ~/variax-venv/bin/pip install variax
   ```

   The command is then `~/variax-venv/bin/variax`, or just `variax` after
   `source ~/variax-venv/bin/activate`.

3. Let your user access the interface without `sudo`, with a udev rule:

   ```bash
   echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0e41", ATTRS{idProduct}=="534d", MODE="0660", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/50-variax.rules
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```

   Your user has to be in the `plugdev` group (check with `groups`; add it
   with `sudo usermod -aG plugdev $USER` and log in again). Then unplug and
   replug the interface.

Some Linux kernels include a driver for the Variax USB Interface
(`snd-usb-variax`); `variax` detaches it automatically while it uses the
interface. On Linux, `variax midi`'s port appears in the ALSA MIDI system as
"Variax" (`aconnect -l` lists it).

## Usage

```bash
variax send -n 'lester 5'                   # select a model: bank + pickup position (1 = bridge, 5 = neck)
variax send -n 'Rbilly 3'                   # names are case-insensitive, hyphens optional
variax send -p 18                           # or by program number (0-59 knob positions, 60-104 factory models)
variax send -n 'factory spank 5'            # the factory version of a model
variax send -p 18 --volume 100 --tone 64    # volume and tone, 0-127
variax send -n 'lester 5' --tuning dadgad   # a tuning by name; without --keep, the tuning knob
                                            # must be on MODEL
variax send --tuning dadgad --keep          # works with the tuning knob anywhere and stays through
                                            # model changes until you turn the knob; whole semitones
variax send -s 'E B E G# B E'               # any tuning, low E first, as notes...
variax send -s '-1 -1 -1 -1 -1 -1'          # ...or semitones from standard (fractions allowed)
variax send --tuning none                   # no pitch shift: strings sound as physically tuned
variax send --twelve-string on              # 12-string sound; "off" to stop
variax send --modeling off                  # the magnetic pickups; "on" to switch modeling back on
variax send --patch 1                       # apply [patch.1] from variax.toml, as the MIDI bridge would
variax send -n 'semi 1' --dry-run           # show the MIDI messages without sending them
```

**Tunings and the tuning knob.** Without `--keep`, a tuning becomes the
current model's own tuning: the guitar only plays it with the tuning knob on
**MODEL**, and a model change resets it. With `--keep`, the tuning plays with
the knob in any position and stays through model changes, until you turn the
knob; it only takes whole semitones.

On/off options take `on`/`off`, `yes`/`no` or `true`/`false`. `--modelling`
works too.

`send` always sends in the same order (modeling, model, volume, tone, tuning,
12-string), so tone and tuning follow the model change in one command. They
have to: a model change reloads the stored model, with its own tone and
tuning (only a `--keep` tuning stays). Nothing is ever saved to the guitar, so
your presets stay untouched.

`--strings` takes six notes or numbers, low E string first, separated by
spaces or commas: `'D A D G A D'`, `'Eb Ab Db Gb Bb Eb'` (or `♭`/`♯`),
`'-2 0 0 0 -2 -2'`, or a mix. A note means the nearest pitch to the standard
string, at most a tritone up or down, so `B` on the low string is a baritone
B; add the octave for anything further, e.g. `'E1 A1 D2 G2 B2 E3'` for an
octave down (standard is E2 A2 D3 G3 B3 E4).

`--tuning` knows the factory tunings of all JTV models by name:

| Name | Tuning, low to high string | Also recognized |
|---|---|---|
| `standard` | E A D G B E |  |
| `drop d` | D A D G B E |  |
| `half down` | Eb Ab Db Gb Bb Eb | `1/2 down` |
| `drop Db` | Db Ab Db Gb Bb Eb |  |
| `one down` | D G C F A D | `1 down` |
| `dadgad` | D A D G A D |  |
| `open d` | D A D F# A D |  |
| `blues` | D G D G B D | `blues g` |
| `reso` | G B D G B D | `reso g` |
| `open a` | E A C# E A E |  |
| `baritone` | B E A D F# B |  |
| `drop c` | C G C F A D |  |
| `m3 down` | Db Gb B E Ab Db | `minor 3rd down`, `minor third down`, `min3 down` |
| `drop b` | B Gb B E Ab Db |  |
| `M3 down` | C F Bb Eb G C | `major 3rd down`, `major third down`, `maj3 down` |
| `drop Bb` | Bb F Bb Eb G C |  |

Case, spaces and hyphens don't matter (`Drop-D`, `dropd`), except that `m3`
(minor third) and `M3` (major third) are told apart by the case of the `m`.
Other names are looked up among the tunings stored on your guitar's tuning
knob, so your own custom tunings work by name too.

Other commands:

```bash
variax monitor     # print what the guitar sends as you turn its knobs; run
                   # 'variax tunings --save' first to see tuning knob names
variax tunings     # the tunings on the tuning knob, and the current model's tuning
variax tunings --save   # also save the knob's tunings to tunings.json
variax midi        # a virtual MIDI port for MainStage and other apps (see below)
variax models      # list all program numbers and model names
variax dump        # the current model's settings, including its tuning and 12-string state
variax read 0x41C 6   # read words of the current model (for exploring; see docs/PROTOCOL.md)
variax --help      # all commands; variax send --help for all send options
```

`variax tunings --save` writes the tunings stored on the guitar's knob to
`tunings.json` in the current directory, with the names and strings as the
guitar reports them (which may differ from the factory tunings). `variax
monitor` and `variax midi` use this file, when it is in the current
directory, for the tuning knob's names and tunings; without it, `monitor`
shows the knob's positions as numbers.

The file looks like this:

```json
{
  "tunings": [
    {"name": "STANDARD", "strings": "E A D G B E"},
    {"name": "DROP D", "strings": "D A D G B E"}
  ]
}
```

## Control from MainStage, a DAW or a MIDI controller

`variax midi` creates a virtual MIDI port called **Variax** that other apps
can send to, and translates what they send into changes on the guitar. The
guitar's own knob changes come back out of the same port. It runs until you
press Ctrl-C.

### Your settings file

The bridge reads its settings from `variax.toml` and your tuning knob's
tunings from `tunings.json`, both in the directory you start it from. To set
up your own:

1. Make a folder for your setup and go there:

   ```bash
   mkdir -p ~/variax && cd ~/variax
   ```

2. Create `variax.toml`, with every setting, its default and what it does:

   ```bash
   variax midi --write-config
   ```

3. Edit `variax.toml` to suit your setup. Every setting is optional: you can
   delete the ones you don't change. The bridge checks the file when it starts
   and names any mistake.

4. Save your guitar's tuning knob tunings to `tunings.json` (guitar connected
   and switched on):

   ```bash
   variax tunings --save
   ```

5. Start the bridge from that folder:

   ```bash
   cd ~/variax && variax midi
   ```

Without a `variax.toml` the bridge uses the defaults, and without a
`tunings.json` it reads the knob's tunings from the guitar when it starts. To
browse all settings without installing anything, see
[src/variax/default.toml](src/variax/default.toml), the file `--write-config`
writes.

### Sending to the bridge

In MainStage (or any app), choose **Variax** as a MIDI output and have your
patches send these on channel 1 (the defaults; all of it can be changed in
`variax.toml`):

| Send | Does |
|---|---|
| Program Change 0–104 | selects that model (as `variax models` lists them) |
| CC 7 / CC 79 | volume / tone, 0–127 |
| CC 84 | tuning: 0 = none, 1–11 = the tuning knob's tunings, 12+ = your own `[tunings]` |
| CC 85 | 12-string: 0–63 off, 64–127 on |
| CC 86 | modeling: 0–63 off (the magnetic pickups), 64–127 on |
| `program` CC (off by default) | works like a Program Change with the CC's value, for devices that can't send Program Changes |
| CC 20–25 | each string's tuning, low E first: 64 = standard, 52–76 = −12 to +12 semitones |
| CC 26–31 | each string's fine tuning in cents, low E first: 64 = 0 |
| Line 6 SysEx | passed to the guitar unchanged (other SysEx, such as the probes Logic Pro sends to every new port, is ignored) |

Volume, tone and tuning use the same CC numbers the guitar uses to report its
own knobs, so a MainStage control on CC 7 both sets the guitar's volume and
follows its volume knob. MIDI monitors show CC 84 as "Portamento Control", its
name in the MIDI standard; the guitar simply uses that number for its tuning
knob. If an instrument receives this port and reacts to it, set another
`tuning` number in `variax.toml`.

With `program_change = "patches"` in `variax.toml`, a Program Change applies a
whole `[patch.N]` instead: model, volume, tone, tuning, 12-string and modeling
in one go, for controllers that can only send one Program Change per patch.
Some devices, like the Hotone Ampero II, can send CCs but no Program Change
when you select a patch. For those, set `program = 102` (or another unused CC)
in the `[cc]` section, and program each device patch to send that CC with the
number of the `[patch.N]` (or model) it should select.

`variax.toml` documents every setting, including patches. To try a patch
without a MIDI device, use `variax send --patch N`: it applies `[patch.N]`
exactly as the bridge would, and other `send` options override parts of it
(`variax send --patch 1 --tone 40`).

Tunings work as with `variax send`: by default (`tuning_method = "model"`) the
tuning knob has to be on MODEL; with `tuning_method = "keep"` it works with
the knob anywhere, in whole semitones. The bridge sends up to about 25 tuning
changes per second; when an app sends faster, it skips to the newest value.

## How it works

The Variax USB Interface doesn't show up as a MIDI device: it uses its own USB
protocol, so `variax` talks to it directly with libusb. Underneath, it carries
plain MIDI messages plus Line 6 SysEx. The protocol notes, with every message
and how it was found, are in [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Contributing

Help with **Windows support** is very welcome, as are reports from other
Variax models and other Linux systems. What is known about Windows so far:
libusb needs the WinUSB driver on the interface (e.g. installed with Zadig),
which replaces Line 6's driver while it is installed.

The tests run without a guitar:

```bash
uv sync
uv run pytest
```

## Credits

Reverse engineered by Peter Hulst, by monitoring the guitar and capturing the
USB traffic of Line 6 Workbench HD. With thanks to:

- Joe Bear, for the tuning SysEx behind `--keep`, and the authors of the
  community "Variax MIDI reference" spreadsheet, for the magnetic/modeling
  switch and the factory program numbers.
- Markus Grabner and the Linux kernel Line 6 driver
  ([`sound/usb/line6/variax.c`](https://github.com/torvalds/linux/blob/master/sound/usb/line6/variax.c),
  and the older [staging driver](https://github.com/torvalds/linux/tree/v2.6.32/drivers/staging/line6)),
  for the handshake and the model data requests.
- The [VGuitar Forums](https://www.vguitarforums.com/smf/index.php?topic=13484.0)
  and [Line 6 Community](https://line6.com/support/topic/60167-controlling-jtv-guitar-models-and-settings-via-midi/)
  discussions of the Variax and its VDI interface.

## License

MIT. Line 6, Variax, James Tyler and the guitar names used for the models are
trademarks of their respective owners.
