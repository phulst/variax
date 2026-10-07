"""Connection to the Variax through the Variax USB Interface: handshake, send, receive."""

import sys
import time

import usb.core
import usb.util

from monitor import (ACTIVATE, EP_IN, EP_OUT, IDENTITY_REPLY_PREFIX, IDENTITY_REQUEST,
                     PACKET_SIZE, MidiParser, describe, hexs, open_interface)


class VariaxLink:
    def __init__(self, verbose=True):
        self.verbose = verbose
        self.dev = open_interface()
        self.midi = MidiParser()
        self.start = time.time()

    def _log(self, direction, msg, label=None):
        if self.verbose:
            print("%8.2f  %s %-28s %s" % (time.time() - self.start, direction, hexs(msg),
                                          label or describe(msg)), flush=True)

    def send(self, msg, label=None):
        self._log(">>", msg, label)
        for i in range(0, len(msg), PACKET_SIZE):
            self.dev.write(EP_OUT, msg[i:i + PACKET_SIZE], timeout=1000)

    def listen(self, seconds, until=None):
        """Return the messages received within `seconds`, stopping early when until(msg) is true."""
        received = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                data = bytes(self.dev.read(EP_IN, PACKET_SIZE, timeout=200))
            except usb.core.USBTimeoutError:
                continue
            for msg in self.midi.feed(data):
                self._log("<<", msg)
                received.append(msg)
                if until and until(msg):
                    return received
        return received

    def handshake(self):
        for _ in range(10):
            self.send(IDENTITY_REQUEST, "identity request")
            is_reply = lambda m: m.startswith(IDENTITY_REPLY_PREFIX)
            if any(is_reply(m) for m in self.listen(0.3, until=is_reply)):
                break
        else:
            sys.exit("No answer from the Variax USB Interface (it answers the identity request even with the guitar off).")
        self.send(ACTIVATE, "activate")
        self.listen(0.2)

    def close(self):
        usb.util.release_interface(self.dev, 0)
        usb.util.dispose_resources(self.dev)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
