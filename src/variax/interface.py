"""USB connection to the Line 6 Variax USB Interface.

The interface (USB 0e41:534d) is vendor-specific, so it never shows up as a
MIDI port; we talk to it directly with libusb. After selecting alternate
setting 1 of interface 0 it carries raw MIDI bytes over two interrupt
endpoints, OUT 0x01 and IN 0x82, in packets of up to 32 bytes.
"""

import time

import libusb_package
import usb.core
import usb.util

from .protocol import (ACK_MESSAGE, ACTIVATE, IDENTITY_REPLY_PREFIX, IDENTITY_REQUEST, WORKBENCH_SYSEX, WRITE,
                       MidiParser, parse_read_reply, parse_tuning_reply, read_message, read_tuning_message)

VENDOR_ID = 0x0E41
PRODUCT_ID = 0x534D
EP_OUT = 0x01
EP_IN = 0x82
PACKET_SIZE = 32


class VariaxError(Exception):
    pass


def open_interface():
    """Find, configure and claim the Variax USB Interface."""
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID, backend=libusb_package.get_libusb1_backend())
    if dev is None:
        raise VariaxError("Variax USB Interface not found. Is it plugged in?")
    # On macOS, setting the configuration again on an already configured device
    # resets it and libusb loses the handle, so only set it when needed.
    try:
        configured = dev.get_active_configuration().bConfigurationValue == 1
    except usb.core.USBError:
        configured = False
    if not configured:
        dev.set_configuration(1)
    try:
        usb.util.claim_interface(dev, 0)
    except usb.core.USBError as e:
        if e.errno == 13:
            raise VariaxError("The Variax USB Interface is in use by another program "
                              "(another variax command, or Line 6 Central / Workbench). Close it first.") from e
        raise
    dev.set_interface_altsetting(interface=0, alternate_setting=1)  # alt 1 has the endpoints
    return dev


class VariaxLink:
    """An open connection: send MIDI messages to the guitar and receive its messages.

    log: optional function called as log(direction, message) for every message
    sent (">>") or received ("<<"); with raw=True, received USB packets are
    logged as they arrive instead of reassembled messages.
    """

    def __init__(self, log=None, raw=False):
        self.log = log
        self.raw = raw
        self.on_receive = None  # optional function called with every message received, whoever listens
        self.dev = open_interface()
        self.midi = MidiParser()

    def send(self, msg):
        if self.log:
            self.log(">>", msg)
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
            if self.log and self.raw and data:
                self.log("<<", data)
            for msg in self.midi.feed(data):
                if self.log and not self.raw:
                    self.log("<<", msg)
                if self.on_receive:
                    self.on_receive(msg)
                received.append(msg)
                if until and until(msg):
                    return received
        return received

    def handshake(self, activate=True):
        """Identify the interface, then activate the guitar's reports.

        Selecting the interface's alternate setting (needed on every connection)
        resets the host's USB data toggles but not always the interface's, so the
        first packet in either direction can be dropped as a duplicate. The
        identity request takes that hit: it is retried until answered (replies
        take 15-40 ms), so the messages that matter come after it.
        """
        is_reply = lambda m: m.startswith(IDENTITY_REPLY_PREFIX)
        for _ in range(30):
            self.send(IDENTITY_REQUEST)
            if any(is_reply(m) for m in self.listen(0.08, until=is_reply)):
                break
        else:
            raise VariaxError("No answer from the Variax USB Interface "
                              "(it answers the identity request even with the guitar off).")
        if activate:
            self.send(ACTIVATE)

    def send_and_wait_ack(self, msg, timeout=0.3):
        """Send a message. For a write (command 43), the only message the guitar acknowledges, wait
        for the acknowledgement (about 40 ms) and return whether it came; otherwise return None."""
        self.send(msg)
        if not msg.startswith(WORKBENCH_SYSEX + bytes([WRITE])):
            return None
        return any(m == ACK_MESSAGE for m in self.listen(timeout, until=lambda m: m == ACK_MESSAGE))

    def read_words(self, address, count):
        """Read `count` 24-bit words of the current model (the working copy) from a word address."""
        self.send(read_message(address, count))
        for msg in self.listen(1.0, until=lambda m: parse_read_reply(m) is not None):
            words = parse_read_reply(msg)
            if words is not None:
                return words
        raise VariaxError("No answer to a read from the guitar. Is it switched on (1/4\" cable plugged in)?")

    def read_tunings(self):
        """The tunings stored on the tuning knob: {slot: (name, offsets low E first)}."""
        tunings = {}
        for slot in range(1, 12):
            self.send(read_tuning_message(slot))
            for msg in self.listen(1.0, until=lambda m: parse_tuning_reply(m) is not None):
                reply = parse_tuning_reply(msg)
                if reply:
                    tunings[reply[0]] = (reply[1], reply[2])
        return tunings

    def close(self):
        usb.util.release_interface(self.dev, 0)
        usb.util.dispose_resources(self.dev)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
