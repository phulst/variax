"""Print everything a James Tyler Variax sends through the Line 6 Variax USB Interface.

The interface (USB 0e41:534d) is vendor-specific, so it never shows up as a MIDI
port; we talk to it directly with libusb. It carries raw MIDI bytes over two
interrupt endpoints (OUT 0x01, IN 0x82). The startup handshake is the one from
the Linux kernel driver, sound/usb/line6/variax.c:

  1. send a Universal Identity Request, repeat until the guitar answers
  2. send the Variax "activate" SysEx; only then does the guitar report changes

Usage:
  uv run monitor.py                 # handshake, then print until Ctrl-C
  uv run monitor.py --raw           # print only the raw USB packets
  uv run monitor.py --no-handshake  # just listen (the guitar stays quiet)
  uv run monitor.py --seconds 30    # stop after 30 seconds
"""

import argparse
import sys
import time

import libusb_package
import usb.core
import usb.util

import jtv

VENDOR_ID = 0x0E41
PRODUCT_ID = 0x534D
EP_OUT = 0x01
EP_IN = 0x82
PACKET_SIZE = 32

IDENTITY_REQUEST = bytes([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7])
IDENTITY_REPLY_PREFIX = bytes([0xF0, 0x7E, 0x7F, 0x06, 0x02, 0x00, 0x01, 0x0C])
ACTIVATE = bytes([0xF0, 0x00, 0x01, 0x0C, 0x07, 0x00, 0x2A, 0x01, 0xF7])
LINE6_SYSEX_PREFIX = bytes([0xF0, 0x00, 0x01, 0x0C])

# Names from the old Linux staging driver (drivers/staging/line6/control.h, VARIAXMIDI_*).
CC_NAMES = {
    0x07: "volume knob",
    0x4F: "tone knob",
}


def hexs(data):
    return " ".join("%02X" % b for b in data)


class MidiParser:
    """Splits a raw byte stream into complete MIDI messages (handles running status)."""

    def __init__(self):
        self.buf = bytearray()
        self.running_status = None

    def feed(self, data):
        messages = []
        for b in data:
            if b >= 0xF8:  # real-time bytes can appear anywhere, even inside SysEx
                messages.append(bytes([b]))
            elif b == 0xF0:
                self.buf = bytearray([b])
                self.running_status = None
            elif self.buf and self.buf[0] == 0xF0:
                self.buf.append(b)
                if b == 0xF7:
                    messages.append(bytes(self.buf))
                    self.buf = bytearray()
            elif b & 0x80:
                self.buf = bytearray([b])
                self.running_status = b if b < 0xF0 else None
                if self._complete():
                    messages.append(self._take())
            else:
                if not self.buf and self.running_status is not None:
                    self.buf = bytearray([self.running_status])
                if self.buf:
                    self.buf.append(b)
                    if self._complete():
                        messages.append(self._take())
        return messages

    def _complete(self):
        status = self.buf[0]
        if status < 0xF0:
            data_len = 1 if (status & 0xF0) in (0xC0, 0xD0) else 2
        else:
            data_len = {0xF1: 1, 0xF2: 2, 0xF3: 1}.get(status, 0)
        return len(self.buf) == 1 + data_len

    def _take(self):
        msg = bytes(self.buf)
        self.buf = bytearray()
        return msg


def describe(msg):
    status = msg[0]
    if status == 0xF0:
        if msg.startswith(IDENTITY_REPLY_PREFIX) and len(msg) >= 17:
            family = msg[8] | msg[9] << 7
            member = msg[10] | msg[11] << 7
            version = bytes(msg[12:16]).decode("ascii", "replace")
            return "identity reply: Line 6 family %d, member %d, firmware %s" % (family, member, version)
        if msg.startswith(LINE6_SYSEX_PREFIX):
            return "Line 6 SysEx"
        return "SysEx"
    if status == 0xFF:
        return "reset (guitar resends its state; tuning knob push, which on a JTV-59 toggles the selector between models 1-3-5 and 2-3-4)"
    if status >= 0xF0:
        return "system message"
    kind = status & 0xF0
    channel = (status & 0x0F) + 1
    if kind == 0xC0:
        program = msg[1]
        return "program change ch%d %d  ->  %s" % (channel, program, jtv.describe_program(program))
    if kind == 0xB0:
        cc, value = msg[1], msg[2]
        if cc == 0x54:
            return "control change ch%d CC84 = %d  ->  tuning %s" % (channel, value, jtv.describe_tuning(value))
        name = CC_NAMES.get(cc, "")
        return "control change ch%d CC%d = %d%s" % (channel, cc, value, "  (%s)" % name if name else "")
    names = {0x80: "note off", 0x90: "note on", 0xA0: "poly pressure", 0xD0: "channel pressure", 0xE0: "pitch bend"}
    return "%s ch%d" % (names[kind], channel)


def open_interface():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID, backend=libusb_package.get_libusb1_backend())
    if dev is None:
        sys.exit("Variax USB Interface not found. Is it plugged in?")
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
            sys.exit("The interface is in use by another program (monitor.py or send.py?). Stop it first.")
        raise
    dev.set_interface_altsetting(interface=0, alternate_setting=1)  # alt 1 has the endpoints
    return dev


def main():
    parser = argparse.ArgumentParser(description="Print what the Variax sends over the Variax USB Interface.")
    parser.add_argument("--raw", action="store_true", help="print only raw USB packets, no decoding")
    parser.add_argument("--no-handshake", action="store_true", help="don't send the identity request and activate")
    parser.add_argument("--seconds", type=float, help="stop after this many seconds (default: run until Ctrl-C)")
    args = parser.parse_args()

    dev = open_interface()
    midi = MidiParser()
    start = time.time()

    def send(msg, label):
        print("%8.2f  >> %-28s %s" % (time.time() - start, hexs(msg), label), flush=True)
        for i in range(0, len(msg), PACKET_SIZE):
            dev.write(EP_OUT, msg[i:i + PACKET_SIZE], timeout=1000)

    def poll(timeout_ms):
        """Read one packet, print it, and return the complete MIDI messages it finished."""
        try:
            data = bytes(dev.read(EP_IN, PACKET_SIZE, timeout=timeout_ms))
        except usb.core.USBTimeoutError:
            return []
        if not data:
            return []
        now = time.time() - start
        if args.raw:
            print("%8.2f  << %s" % (now, hexs(data)), flush=True)
            return midi.feed(data)
        messages = midi.feed(data)
        for msg in messages:
            print("%8.2f  << %-28s %s" % (now, hexs(msg), describe(msg)), flush=True)
        return messages

    try:
        if not args.no_handshake:
            for _ in range(10):
                send(IDENTITY_REQUEST, "identity request")
                deadline = time.time() + 1.0
                answered = False
                while time.time() < deadline and not answered:
                    answered = any(m.startswith(IDENTITY_REPLY_PREFIX) for m in poll(200))
                if answered:
                    break
            else:
                sys.exit("No answer from the Variax USB Interface (it answers the identity request even with the guitar off).")
            time.sleep(0.1)
            send(ACTIVATE, "activate")

        print("listening, Ctrl-C to stop", flush=True)
        while args.seconds is None or time.time() - start < args.seconds:
            poll(500)
    except KeyboardInterrupt:
        pass
    finally:
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)


if __name__ == "__main__":
    main()
