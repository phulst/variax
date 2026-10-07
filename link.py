"""Connection to the Variax through the Variax USB Interface: handshake, send, receive."""

import sys
import time

import usb.core
import usb.util

from monitor import (ACTIVATE, EP_IN, EP_OUT, IDENTITY_REPLY_PREFIX, IDENTITY_REQUEST,
                     PACKET_SIZE, MidiParser, describe, hexs, open_interface)

VARIAX_SYSEX = bytes.fromhex("F0 00 01 0C 07")
ACK = 0x71  # F0 00 01 0C 07 05 71 F7


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
            timeout_ms = max(1, int(min(0.2, deadline - time.time()) * 1000))
            try:
                data = bytes(self.dev.read(EP_IN, PACKET_SIZE, timeout=timeout_ms))
            except usb.core.USBTimeoutError:
                continue
            for msg in self.midi.feed(data):
                self._log("<<", msg)
                received.append(msg)
                if until and until(msg):
                    return received
        return received

    def handshake(self):
        # Selecting the interface's alternate setting (needed on every run) resets
        # the host's USB data toggles but not always the interface's, so the first
        # packet in either direction can be dropped as a duplicate. The identity
        # request takes that hit: it is retried until answered (replies take
        # 15-40 ms), so the messages that matter come after it.
        is_reply = lambda m: m.startswith(IDENTITY_REPLY_PREFIX)
        for _ in range(30):
            self.send(IDENTITY_REQUEST, "identity request")
            if any(is_reply(m) for m in self.listen(0.08, until=is_reply)):
                break
        else:
            sys.exit("No answer from the Variax USB Interface (it answers the identity request even with the guitar off).")
        self.send(ACTIVATE, "activate")

    def send_and_wait_ack(self, msg, timeout=0.3):
        """Send a message; for a Variax SysEx write, wait until the guitar acknowledges it."""
        self.send(msg)
        if msg[:1] == b"\xF0":
            self.listen(timeout, until=lambda m: m.startswith(VARIAX_SYSEX) and len(m) == 8 and m[6] == ACK)

    def close(self):
        usb.util.release_interface(self.dev, 0)
        usb.util.dispose_resources(self.dev)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
