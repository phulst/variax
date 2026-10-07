"""The variax command line."""

import json
import os
import re
import signal
import time

import click
import usb.core

from . import __version__, jtv, protocol
from . import config as configuration
from .actions import plan_send, resolve
from .interface import VariaxError, VariaxLink
from .modeldata import float24, format_diff, format_model, read_model


def _run(func):
    """Run a function that talks to the guitar, turning errors into clean messages."""
    try:
        return func()
    except VariaxError as e:
        raise click.ClickException(str(e)) from e
    except usb.core.USBError as e:
        raise click.ClickException("USB error: %s" % e) from e
    except ValueError as e:
        raise click.ClickException(str(e)) from e


def _traffic_logger(raw=False, knob_tunings=None):
    """Print each message with a timestamp and description (raw incoming USB packets undescribed)."""
    start = time.time()

    def log(direction, msg):
        description = "" if raw and direction == "<<" else protocol.describe(msg, knob_tunings)
        click.echo("%8.2f  %s %-28s %s" % (time.time() - start, direction, protocol.hexs(msg), description))
    return log


def parse_strings(ctx, param, text):
    """Click callback: six strings, low E first, as semitone offsets or notes (see jtv.parse_tuning_text)."""
    if text is None:
        return None
    try:
        return jtv.parse_tuning_text(text)
    except ValueError as e:
        raise click.BadParameter(str(e))


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="variax")
def main():
    """Control a Line 6 James Tyler Variax through the Variax USB Interface.

    Unofficial; not affiliated with Line 6. Close Line 6 Central and Workbench
    first: only one program can use the interface at a time.
    """


@main.command()
@click.option("-p", "--program", type=click.IntRange(0, 104), help="Program number: 0-59 knob positions, 60-104 factory models.")
@click.option("-n", "--name", help="Model by name: 'lester 5', 'R-Billy-3', 'custom 1 2', 'factory spank 5'.")
@click.option("--volume", type=click.IntRange(0, 127), help="Volume 0-127.")
@click.option("--tone", type=click.IntRange(0, 127), help="Tone 0-127.")
@click.option("-t", "--tuning", help="A factory tuning by name ('dadgad', 'drop d', '1/2 down', 'm3 down'), a custom one "
                                     "on the knob, or 'none': no pitch shift, the strings sound as physically tuned.")
@click.option("-s", "--strings", callback=parse_strings,
              help="Any tuning, low E string first: notes ('D A D G A D', 'Eb Ab Db Gb Bb Eb', 'D2 A2 D3 G3 A3 D4') "
                   "or semitones from standard ('-2 0 0 0 -2 -2', fractions allowed).")
@click.option("--keep", is_flag=True,
              help="Keep the tuning through model changes, until the tuning knob is turned. Works with the "
                   "tuning knob in any position, but whole semitones only (uses the on-the-fly tuning SysEx).")
@click.option("--twelve-string", type=click.Choice(["on", "off"]), help="12-string sound (Parallel Pitch).")
@click.option("--pickups", type=click.Choice(["magnetic", "modeling"]), help="Magnetic pickups or modeling.")
@click.option("--raw", multiple=True, metavar="HEX", help="A raw MIDI message as hex, e.g. 'C0 2C'. Repeatable; sent last.")
@click.option("--wait", type=float, default=0.0, show_default=True, help="Seconds to keep listening at the end.")
@click.option("--dry-run", is_flag=True, help="Print the messages without sending them.")
@click.option("-v", "--verbose", is_flag=True, help="Print all MIDI traffic.")
def send(program, name, volume, tone, tuning, strings, keep, twelve_string, pickups, raw, wait, dry_run,
         verbose):
    """Select a model and set volume, tone, tuning and 12-string.

    Messages go out in a fixed order (pickups, model, volume, tone, tuning,
    12-string, raw), so tone and tuning always follow the model change that
    would otherwise reset them. Nothing is saved to the guitar.

    Tunings: without --keep, a tuning becomes the current model's tuning,
    which the guitar only plays with the tuning knob on MODEL, and a model
    change resets it. With --keep, it plays with the knob in any position and
    stays through model changes until the knob is turned (whole semitones only).

    \b
    Examples:
      variax send -p 18
      variax send -n 'Rbilly 3'
      variax send -p 18 --volume 100 --tone 64
      variax send -n 'lester 5' --tuning dadgad
      variax send -s 'D A D G A D'
      variax send -s '-2 0 0 0 0 0'

    A note without an octave means the nearest pitch to the standard string
    (at most a tritone away); add the octave (D2) for anything further.
    """
    if program is not None and name is not None:
        raise click.UsageError("use either --program or --name, not both")
    if tuning is not None and strings is not None:
        raise click.UsageError("use either --tuning or --strings, not both")
    try:
        messages = plan_send(program, name, volume, tone, tuning, strings, keep, twelve_string, pickups, raw)
    except ValueError as e:
        raise click.UsageError(str(e))
    if not messages:
        raise click.UsageError("nothing to send; see variax send --help")

    if dry_run:
        for msg in messages:
            if msg[0] == "tuning":
                click.echo("(tuning %r: looked up among the tunings on the guitar's knob)" % msg[1])
            elif msg[0] == "twelve-string":
                click.echo("(12-string %s: reads the model's flags word, then %s Parallel Pitch bits 0x%06X)"
                           % ("on" if msg[1] else "off", "writes the 12-string settings and sets" if msg[1]
                              else "clears", protocol.PARALLEL_PITCH_BITS))
            else:
                shown = protocol.hexs(msg) if len(msg) <= 30 else "%s ... (%d bytes)" % (protocol.hexs(msg[:12]), len(msg))
                click.echo("%-28s %s" % (shown, protocol.describe(msg)))
        return

    def run():
        with VariaxLink(log=_traffic_logger() if verbose else None) as link:
            link.handshake()
            for msg in messages:
                for step in resolve(link, msg, keep):
                    _send_one(link, step, verbose)
            if wait:
                link.listen(wait)
    _run(run)


def _send_one(link, msg, verbose):
    acknowledged = link.send_and_wait_ack(msg)
    if not verbose:
        status = {True: "", False: "  (no acknowledgement)", None: ""}[acknowledged]
        click.echo(protocol.describe(msg) + status)


@main.command()
@click.option("--raw", is_flag=True, help="Print raw USB packets instead of decoded messages.")
@click.option("--no-handshake", is_flag=True, help="Only listen (the guitar stays silent until activated).")
@click.option("--seconds", type=float, help="Stop after this many seconds (default: until Ctrl-C).")
def monitor(raw, no_handshake, seconds):
    """Print what the guitar sends: knobs, pickup selector, volume, tone.

    Run 'variax tunings --save' first, in the same directory: it saves the
    tuning knob's tunings to tunings.json, which monitor uses to show the
    knob's positions by name and tuning. Without it, they show as numbers.
    """

    knob_tunings = load_tunings_json()
    if knob_tunings:
        click.echo("using tuning names and values from %s" % TUNINGS_FILE)
    else:
        click.echo("%s not found, so tuning knob changes are shown as positions. To show their names and "
                   "tunings, first run 'variax tunings --save' in this directory." % TUNINGS_FILE)

    def run():
        start = time.time()
        with VariaxLink(log=_traffic_logger(raw, knob_tunings), raw=raw) as link:
            if not no_handshake:
                link.handshake()
            click.echo("listening, Ctrl-C to stop")
            try:
                while seconds is None or time.time() - start < seconds:
                    link.listen(0.5)
            except KeyboardInterrupt:
                pass
    _run(run)


@main.command()
@click.option("--save", type=click.Path(dir_okay=False, writable=True), help="Save the dump as JSON.")
@click.option("--diff", type=click.Path(exists=True, dir_okay=False), help="Show the bytes that differ from a saved dump.")
@click.option("-v", "--verbose", is_flag=True, help="Print all MIDI traffic.")
def dump(save, diff, verbose):
    """Read and decode the current model's settings (read-only)."""

    def run():
        with VariaxLink(log=_traffic_logger() if verbose else None) as link:
            link.handshake()
            return read_model(link)
    model = _run(run)
    click.echo(format_model(model))
    if diff:
        with open(diff) as f:
            click.echo("\n" + format_diff(json.load(f), model))
    if save:
        with open(save, "w") as f:
            json.dump(model, f, indent=2)
        click.echo("\nsaved to %s" % save)


TUNINGS_FILE = "tunings.json"


def load_tunings_json(path=TUNINGS_FILE):
    """The knob tunings from a tunings.json written by `variax tunings --save`, or None if there is none."""
    try:
        with open(path) as f:
            tunings = json.load(f)["tunings"]
        return [{"name": str(t["name"]), "strings": str(t["strings"])} for t in tunings]
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError) as e:
        raise click.ClickException("%s is not a valid tunings file (%s); recreate it with "
                                   "'variax tunings --save'" % (path, e))


def tunings_json(found):
    """{"tunings": [{"name", "strings"}, ...]}: the knob's tunings with their names, as read from the guitar."""
    return {"tunings": [{"name": found[slot][0], "strings": jtv.format_strings(found[slot][1])}
                        for slot in sorted(found)]}


@main.command()
@click.option("--save", is_flag=True,
              help="Save the knob's tunings to tunings.json in the current directory (used by variax monitor).")
@click.option("-v", "--verbose", is_flag=True, help="Print all MIDI traffic.")
def tunings(save, verbose):
    """List the tunings on the tuning knob and the current model's tuning (read-only)."""

    def run():
        with VariaxLink(log=_traffic_logger() if verbose else None) as link:
            link.handshake()
            words = link.read_words(protocol.STRINGS_ADDRESS, 6)
            enabled = link.read_words(protocol.TUNING_ENABLE_ADDRESS, 1)[0]
            return link.read_tunings(), [w * 12 / (1 << 23) for w in reversed(words)], enabled
    found, current, enabled = _run(run)

    def line(label, name, offsets):
        notes = jtv.offsets_to_notes(offsets) or ""
        return "%-5s %-11s %-23s %s" % (label, name, " ".join("%+.2g" % o for o in offsets), notes)
    click.echo("knob  name        semitones, low E first  notes")
    for slot in sorted(found):
        click.echo(line(str(slot).rjust(4), *found[slot]))
    click.echo()
    click.echo(line("model", "on" if enabled else "off", current))
    click.echo("(the current model's own tuning, used with the tuning knob on MODEL when on)")
    if save:
        with open(TUNINGS_FILE, "w") as f:
            json.dump(tunings_json(found), f, indent=2)
            f.write("\n")
        click.echo("\nsaved %d tunings to %s" % (len(found), TUNINGS_FILE))


class _Address(click.ParamType):
    name = "address"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        try:
            address = int(value, 0)
        except ValueError:
            self.fail("%r is not an address; use hex (0x41C) or decimal" % value, param, ctx)
        if not 0 <= address <= 0xFFFFFF:
            self.fail("address must be 0x000000-0xFFFFFF", param, ctx)
        return address


READ_CHUNK = 128  # words per read; 256 still works, 512 gets no answer
READ_COLUMNS = "%-7s  %-8s  %9s  %11s  %s"


def format_word(address, word):
    """ "0x41C  0xEAAAAB   -1398101  -1.234e+26  '...'": a word as hex, signed, 24-bit float and text."""
    raw = (word & 0xFFFFFF).to_bytes(3, "big")
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
    return READ_COLUMNS % ("0x%03X" % address, "0x%06X" % (word & 0xFFFFFF), word, "%.5g" % float24(raw), text)


@main.command()
@click.argument("address", type=_Address())
@click.argument("count", type=click.IntRange(1, 0x10000), default=1)
@click.option("-v", "--verbose", is_flag=True, help="Print all MIDI traffic.")
def read(address, count, verbose):
    """Read COUNT 24-bit words of the current model from ADDRESS (read-only).

    Shows each word as hex, signed integer, 24-bit float (the format of values
    like pot resistances) and 3 characters of text. Reads return the working
    copy, so they include changes made with `variax send`.

    \b
    Examples:
      variax read 0x41C 6     the model's string tuning (high E first)
      variax read 0x353 6     the model's name
      variax read 0x001       the flags word
    """

    def run():
        with VariaxLink(log=_traffic_logger() if verbose else None) as link:
            link.handshake()
            words = []
            for start in range(address, address + count, READ_CHUNK):
                words += link.read_words(start, min(READ_CHUNK, address + count - start))
            return words
    words = _run(run)
    click.echo(READ_COLUMNS % ("address", "hex", "signed", "float24", "text"))
    for i, word in enumerate(words):
        click.echo(format_word(address + i, word))


def _knob_tunings_from_json(tunings):
    """{slot: (name, offsets)} from the entries of a tunings.json."""
    result = {}
    for slot, entry in enumerate(tunings, 1):
        try:
            result[slot] = (entry["name"], jtv.parse_tuning_text(entry["strings"]))
        except ValueError as e:
            raise click.ClickException("%s, tuning %d (%s): %s" % (TUNINGS_FILE, slot, entry["name"], e))
    return result


@main.command()
@click.option("-c", "--config", "config_path", type=click.Path(dir_okay=False),
              help="Settings file (default: variax.toml in the current directory, if there is one).")
@click.option("--write-config", is_flag=True, help="Write variax.toml with all settings and their defaults, then exit.")
@click.option("-v", "--verbose", is_flag=True, help="Also print all traffic with the guitar.")
def midi(config_path, write_config, verbose):
    """Create a virtual MIDI port that controls the guitar from other apps.

    Apps like MainStage or a DAW send Program Changes and CCs to the port
    "Variax"; the bridge turns them into model, volume, tone, tuning,
    12-string and pickup changes. The guitar's own knob changes come back out
    of the port. Settings are in variax.toml (create one with --write-config);
    run 'variax tunings --save' first so tuning CC values 1-11 use the names
    and tunings stored on your guitar's tuning knob. Runs until Ctrl-C.
    """
    if write_config:
        target = config_path or configuration.CONFIG_FILE
        try:
            with open(target, "x") as f:
                f.write(configuration.default_config_text())
        except FileExistsError:
            raise click.ClickException("%s already exists; not overwriting it" % target)
        click.echo("wrote %s with all settings and their defaults" % target)
        return

    try:
        config = configuration.load(config_path or configuration.CONFIG_FILE, required=config_path is not None)
    except configuration.ConfigError as e:
        raise click.ClickException(str(e))
    if config_path or os.path.exists(configuration.CONFIG_FILE):
        click.echo("using settings from %s" % (config_path or configuration.CONFIG_FILE))
    else:
        click.echo("%s not found, using the defaults (create it with 'variax midi --write-config')"
                   % configuration.CONFIG_FILE)
    saved = load_tunings_json()
    knob_tunings = _knob_tunings_from_json(saved) if saved else None

    from . import bridge
    import rtmidi
    start = time.time()

    def report(line):
        click.echo("%8.2f  %s" % (time.time() - start, line))

    def run():
        with VariaxLink(log=_traffic_logger() if verbose else None) as link:
            link.handshake()
            tunings = knob_tunings
            if tunings is None:
                tunings = link.read_tunings()
                click.echo("tuning knob tunings read from the guitar ('variax tunings --save' saves them)")
            else:
                click.echo("using tuning names and values from %s" % TUNINGS_FILE)
            midi_in = rtmidi.MidiIn()
            midi_out = rtmidi.MidiOut() if config["midi"]["forward_from_guitar"] else None
            port = config["midi"]["port"]
            midi_in.open_virtual_port(port)
            if midi_out:
                midi_out.open_virtual_port(port)
            click.echo('MIDI port "%s" ready on channel %d, %s; Ctrl-C to stop'
                       % (port, config["midi"]["channel"],
                          "program changes select patches" if config["midi"]["program_change"] == "patches"
                          else "program changes select models"))
            # stop cleanly on Ctrl-C and on SIGTERM (kill, or a service manager stopping it)
            signal.signal(signal.SIGTERM, signal.default_int_handler)
            try:
                bridge.run(config, link, midi_in, midi_out, tunings, report)
            except KeyboardInterrupt:
                click.echo("stopped")
            finally:
                midi_in.close_port()
                if midi_out:
                    midi_out.close_port()
    _run(run)


@main.command()
def models():
    """List program numbers and model names (no guitar needed)."""
    click.echo("program  name             model")
    for program, label, model in jtv.all_programs():
        click.echo("%7d  %-16s %s" % (program, label, model))
