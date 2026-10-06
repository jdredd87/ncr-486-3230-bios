"""Build ISA PnP resource data (PnP ISA 1.0a tags) for the emulator's PnP cards."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from emu import IsaPnpCard, eisa_id  # noqa: E402


def name(text):
    b = text.encode()
    return bytes([0x82]) + struct.pack("<H", len(b)) + b


def ld(dev_id):
    return bytes([0x15]) + eisa_id(dev_id) + b"\x00"


def dep(priority=0):
    return bytes([0x31, priority])


END_DEP = bytes([0x38])


def irq(*levels):
    return bytes([0x22]) + struct.pack("<H", sum(1 << n for n in levels))


def dma(*chans):
    return bytes([0x2A, sum(1 << n for n in chans), 0x08])


def io(lo, hi, align, length):
    return bytes([0x47, 0x01]) + struct.pack("<HHBB", lo, hi, align, length)


def fixed_io(base, length):
    return bytes([0x4B]) + struct.pack("<HB", base, length)


def end():
    return bytes([0x79, 0x00])


def awe64(serial=0x1234ABCD):
    """A Sound Blaster AWE64 as it presents itself: audio, wavetable and game port."""
    r = bytes([0x0A, 0x10, 0x10]) + name("Creative SB AWE64  PnP")
    r += ld("CTL0045") + name("Audio")
    r += dep(0) + irq(5) + dma(1) + dma(5) + io(0x220, 0x220, 1, 16) + io(0x330, 0x330, 1, 2) + io(0x388, 0x388, 1, 4)
    r += dep(1) + irq(5, 7, 9, 10) + dma(0, 1, 3) + dma(5, 6, 7)
    r += io(0x220, 0x280, 0x20, 16) + io(0x300, 0x330, 0x30, 2) + io(0x388, 0x394, 4, 4)
    r += END_DEP
    r += ld("CTL0022") + name("WaveTable")
    r += dep(0) + io(0x620, 0x620, 1, 4) + io(0xA20, 0xA20, 1, 4) + io(0xE20, 0xE20, 1, 4)
    r += dep(1) + io(0x620, 0x680, 0x20, 4) + io(0xA20, 0xA80, 0x20, 4) + io(0xE20, 0xE80, 0x20, 4)
    r += END_DEP
    r += ld("CTL7002") + name("Game")
    r += dep(0) + io(0x200, 0x200, 1, 8) + dep(1) + io(0x200, 0x208, 8, 8) + END_DEP
    r += end()
    return IsaPnpCard("CTL009D", serial, r)


def modem(serial=0x00000042):
    """A PnP modem that would like COM2 (2F8h, IRQ 3), or else 280h-380h and another IRQ."""
    r = bytes([0x0A, 0x10, 0x10]) + name("PnP Modem 33600")
    r += ld("USR0004")
    r += dep(0) + irq(3) + io(0x2F8, 0x2F8, 1, 8)
    r += dep(1) + irq(3, 4, 5, 7, 10, 11) + io(0x280, 0x380, 0x08, 8)
    r += END_DEP + end()
    return IsaPnpCard("USR3031", serial, r)


def only_irq5(serial=0x0000BEEF):
    """A device with no alternative: IRQ 5 and nothing else."""
    r = bytes([0x0A, 0x10, 0x10]) + name("Stubborn Card")
    r += ld("XYZ0001") + irq(5) + io(0x340, 0x340, 1, 16) + end()
    return IsaPnpCard("XYZ0100", serial, r)
