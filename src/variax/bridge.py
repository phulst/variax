"""`variax midi`: a virtual MIDI port that translates MIDI from other apps into messages for the
guitar, and passes the guitar's own knob changes back.

The translation logic (Bridge) is kept apart from the MIDI and USB plumbing (run), so it can be
tested without either.
"""

import queue
import time

from . import actions, jtv, protocol
from .interface import VariaxError

ECHO_WINDOW = 0.2  # seconds: a message from the app that repeats what the bridge just sent it is an echo
MAX_OFFSET = 12 - 12 / (1 << 23)  # the highest pitch offset the guitar can store (just under +12)


class Bridge:
    """Translates between an app's MIDI (on the configured channel and CC numbers) and the guitar.

    link: a VariaxLink (or anything with send_and_wait_ack and read_words).
    send_to_app: function taking a list of MIDI bytes, for the guitar's changes; None if not forwarding.
    knob_tunings: {slot 1-11: (name, offsets)} for tuning CC values 1-11.
    report: function taking a line of text describing what happened.
    """

    def __init__(self, config, link, send_to_app=None, knob_tunings=None, report=None, clock=time.monotonic):
        self.config = config
        self.link = link
        self.send_to_app = send_to_app if config["midi"]["forward_from_guitar"] else None
        self.knob_tunings = knob_tunings or {}
        self.report = report or (lambda line: None)
        self.clock = clock
        self.channel = config["midi"]["channel"] - 1
        self.keep = config["behavior"]["tuning_method"] == "keep"

        cc = config["cc"]
        self.cc_actions = {}
        for name in ("volume", "tone", "tuning", "twelve_string", "modeling", "program"):
            if cc[name] is not False:
                self.cc_actions[cc[name]] = (name, None)
        for name in ("string_semitones", "string_cents"):
            if cc[name] is not False:
                for string, number in enumerate(cc[name]):
                    self.cc_actions[number] = (name, string)

        # The tuning the bridge has set, per string (low E first): semitones + cents / 100.
        self.semitones = [0.0] * 6
        self.cents = [0.0] * 6
        self.tuning = None              # None: nothing sent yet; "none"; or "offsets"
        self.model_tuning_on = None     # whether the model's tuning switch is known to be on
        self.dirty_strings = set()
        self.echoes = {}                # (kind, number, value) -> time sent to the app

    # --- from the app -------------------------------------------------------------------------

    def handle_app(self, messages):
        """Handle a batch of messages from the app. Within a batch only the last value of each CC
        is used, and string changes are sent together, so the guitar never falls behind."""
        pending = {}
        for msg in messages:
            status = msg[0]
            if status == 0xF0:
                # only Line 6 SysEx goes to the guitar; apps probe new ports with their own
                # (Logic Pro, for example, looks for Mackie Control surfaces)
                if msg.startswith(protocol.LINE6_SYSEX_PREFIX):
                    self._flush(pending)
                    self._send(msg, "SysEx from the app: %s" % protocol.hexs(msg))
            elif status < 0xF0 and status & 0x0F == self.channel:
                kind = status & 0xF0
                if kind == 0xC0 and len(msg) >= 2:
                    if self._is_echo("pc", msg[1], None):
                        continue
                    self._flush(pending)
                    self.program_change(msg[1])
                elif kind == 0xB0 and len(msg) >= 3:
                    if self._is_echo("cc", msg[1], msg[2]):
                        continue
                    pending.pop(msg[1], None)
                    pending[msg[1]] = msg[2]
        self._flush(pending)

    def _flush(self, pending):
        for number, value in pending.items():
            self.control_change(number, value)
        pending.clear()
        self._write_strings()

    def program_change(self, number):
        midi = self.config["midi"]
        if midi["program_change"] == "patches":
            patch = self.config["patch"].get(number)
            if patch is not None:
                self.report("program change %d: patch %d" % (number, number))
                self.apply_patch(patch)
            elif midi["patch_fallback"] and number <= 104:
                self.report("program change %d: no patch %d, selecting model %d" % (number, number, number))
                self._select_model(number)
            else:
                self.report("program change %d: no patch %d, ignored" % (number, number))
            return
        if number > 104:
            self.report("program change %d ignored (models are 0-104)" % number)
            return
        self._select_model(number)
        if (not self.keep and self.config["behavior"]["reapply_tuning_after_model"]
                and self.tuning == "offsets"):
            self._send_tuning()

    def control_change(self, number, value):
        action = self.cc_actions.get(number)
        if action is None:
            return
        name, string = action
        if name == "volume":
            self._send(protocol.control_change(protocol.VOLUME_CC, value))
        elif name == "tone":
            self._send(protocol.control_change(protocol.TONE_CC, value))
        elif name == "tuning":
            self.tuning_value(value)
        elif name == "twelve_string":
            self._send_steps([("twelve-string", value >= 64)])
        elif name == "program":
            # for devices that can send a CC but no Program Change when a patch loads
            self.program_change(value)
        elif name == "modeling":
            self._send(protocol.MODELING_MESSAGE if value >= 64 else protocol.MAGNETIC_MESSAGE)
        elif name == "string_semitones":
            self.semitones[string] = float(max(-12, min(12, value - 64)))
            self.dirty_strings.add(string)
        elif name == "string_cents":
            self.cents[string] = float(value - 64)
            self.dirty_strings.add(string)

    def tuning_value(self, value):
        """Tuning CC: 0 = none, 1-11 = the tuning knob's tunings, 12 and up = [tunings]."""
        if value == 0:
            self.set_tuning(None)
            return
        if value <= 11:
            if value not in self.knob_tunings:
                self.report("tuning %d: unknown knob tuning, ignored" % value)
                return
            self.report("tuning %d: %s" % (value, self.knob_tunings[value][0]))
            self.set_tuning(self.knob_tunings[value][1])
        elif value in self.config["tunings"]:
            self.report("tuning %d from [tunings]" % value)
            self.set_tuning(self.config["tunings"][value])
        else:
            self.report("tuning %d: not in [tunings], ignored" % value)

    def set_tuning(self, offsets):
        """Set all six strings (None: no tuning) and send it."""
        self.dirty_strings.clear()
        if offsets is None:
            self.semitones, self.cents, self.tuning = [0.0] * 6, [0.0] * 6, "none"
        else:
            self.semitones, self.cents, self.tuning = [float(o) for o in offsets], [0.0] * 6, "offsets"
        self._send_tuning()

    def apply_patch(self, patch):
        if "modeling" in patch:
            self._send(protocol.MODELING_MESSAGE if patch["modeling"] else protocol.MAGNETIC_MESSAGE)
        if "model" in patch or "program" in patch:
            self._select_model(jtv.parse_model_name(patch["model"]) if "model" in patch else patch["program"])
        for name, cc in (("volume", protocol.VOLUME_CC), ("tone", protocol.TONE_CC)):
            if name in patch:
                self._send(protocol.control_change(cc, patch[name]))
        if "strings" in patch:
            self.set_tuning(jtv.parse_tuning_text(patch["strings"]))
        elif "tuning" in patch:
            name = patch["tuning"]
            if name.strip().lower() == "none":
                self.set_tuning(None)
            else:
                known = jtv.find_factory_tuning(name)
                try:
                    self.set_tuning(known[1] if known else actions.find_tuning(self.knob_tunings, name))
                except VariaxError as e:
                    self.report(str(e))
        if "twelve_string" in patch:
            self._send_steps([("twelve-string", patch["twelve_string"])])

    # --- sending to the guitar ----------------------------------------------------------------

    def _select_model(self, program):
        self._send(protocol.program_change(program))
        self.model_tuning_on = None  # the guitar reloads the stored model, with its own tuning switch

    def _offsets(self):
        return [max(-12.0, min(MAX_OFFSET, s + c / 100)) for s, c in zip(self.semitones, self.cents)]

    def _send_tuning(self):
        if self.tuning == "none":
            messages = actions.no_tuning_messages(self.keep)
            self.model_tuning_on = False if not self.keep else self.model_tuning_on
        elif self.keep:
            messages = [protocol.fly_tuning_message([round(s) for s in self.semitones])]
        else:
            messages = [protocol.set_strings_message(self._offsets()), protocol.tuning_enable_message(True)]
            self.model_tuning_on = True
        for msg in messages:
            self._send(msg)

    def _write_strings(self):
        """Send the strings changed by string CCs: one word for a single string, all six otherwise."""
        if not self.dirty_strings:
            return
        strings, self.dirty_strings = sorted(self.dirty_strings), set()
        self.tuning = "offsets"
        if self.keep or len(strings) > 1 or self.model_tuning_on is not True:
            self._send_tuning()
            return
        string = strings[0]
        word = round(self._offsets()[string] * (1 << 23) / 12)
        self._send(protocol.write_message(protocol.STRINGS_ADDRESS + 5 - string, [word]))

    def _send_steps(self, steps):
        for step in steps:
            for msg in actions.resolve(self.link, step, self.keep, self.knob_tunings):
                self._send(msg)

    def _send(self, msg, label=None):
        self.link.send_and_wait_ack(msg)
        self.report("-> guitar  %s" % (label or protocol.describe(msg)))

    # --- from the guitar ----------------------------------------------------------------------

    def handle_guitar(self, msg):
        """Pass the guitar's own changes to the app, on the bridge's channel and CC numbers."""
        status = msg[0]
        if status == 0xC0 and len(msg) >= 2:
            self.model_tuning_on = None
            self._to_app("pc", msg[1], None, [0xC0 | self.channel, msg[1]], protocol.describe(msg))
        elif status == 0xB0 and len(msg) >= 3:
            cc = self.config["cc"]
            name = {protocol.VOLUME_CC: "volume", protocol.TONE_CC: "tone",
                    protocol.TUNING_KNOB_CC: "tuning"}.get(msg[1])
            if name == "tuning" and msg[2] in self.knob_tunings:
                # the knob loads that position's tuning, ending any tuning the bridge set
                self.semitones, self.cents = [float(o) for o in self.knob_tunings[msg[2]][1]], [0.0] * 6
            if name and cc[name] is not False:
                self._to_app("cc", cc[name], msg[2], [0xB0 | self.channel, cc[name], msg[2]],
                             protocol.describe(msg, _as_json(self.knob_tunings)))

    def _to_app(self, kind, number, value, midi, description):
        if self.send_to_app is None:
            return
        self.send_to_app(midi)
        self.echoes[(kind, number, value)] = self.clock()
        self.report("<- guitar  %s" % description)

    def _is_echo(self, kind, number, value):
        sent = self.echoes.pop((kind, number, value), None)
        return sent is not None and self.clock() - sent < ECHO_WINDOW


def _as_json(knob_tunings):
    return [{"name": knob_tunings[s][0], "strings": jtv.format_strings(knob_tunings[s][1])}
            for s in sorted(knob_tunings)]


def run(config, link, midi_in, midi_out, knob_tunings, report, stop=lambda: False):
    """Run the bridge until stop() is true (or Ctrl-C). midi_in/midi_out are open rtmidi ports;
    the guitar's own messages are picked up through the link's on_receive hook."""
    app_queue = queue.Queue()
    midi_in.ignore_types(sysex=False, timing=True, active_sense=True)
    midi_in.set_callback(lambda event, data=None: app_queue.put(bytes(event[0])))
    bridge = Bridge(config, link, midi_out.send_message if midi_out else None, knob_tunings, report)
    guitar_messages = []
    link.on_receive = guitar_messages.append
    while not stop():
        batch = []
        while True:
            try:
                batch.append(app_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            bridge.handle_app(batch)
        link.listen(0.01)
        while guitar_messages:
            msg = guitar_messages.pop(0)
            if msg[0] in (0xC0, 0xB0):
                bridge.handle_guitar(msg)
    return bridge
