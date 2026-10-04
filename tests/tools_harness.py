"""Shared setup for running the Tools extension in the emulator."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from emu import AtaDisk, Atapi, IdeChannel, Machine, StopEmu, cmos_checksum  # noqa: E402

IMAGE = os.path.join(ROOT, "build", "NCR3230-203-improved.BIN")
F10, F8, F1, ESC, ENTER = 0x4400, 0x4200, 0x3B00, 0x011B, 0x1C0D
G_BASE = 0xF860


def key(ch):
    """INT 16h value for a typed character (scan code not needed by the tools)."""
    return ord(ch)


def machine(image=IMAGE, ext_mb=3, master="cdrom", slave=None, fake_rom=True, flag=0x00):
    m = Machine(image, ram_mb=1 + ext_mb if ext_mb else 1)
    m.install_rom_vectors()
    m.video_init(3)
    c = m.cmos
    c[0x10], c[0x12], c[0x14], c[0x15], c[0x16] = 0x40, 0x00, 0x41, 0x80, 0x02
    c[0x17], c[0x18] = (ext_mb * 1024) & 0xFF, (ext_mb * 1024) >> 8
    c[0x30], c[0x31] = c[0x17], c[0x18]
    c[0x44], c[0x46], c[0x47], c[0x48] = 0xE5, 0x00, 0x4E, flag
    c[0x07], c[0x08], c[0x09], c[0x32] = 0x04, 0x10, 0x26, 0x20   # 2026-10-04
    c[0x04], c[0x02], c[0x00] = 0x13, 0x45, 0x10
    cmos_checksum(c)
    s = sum(c[0x44:0x48])
    c[0x7E], c[0x7F] = s >> 8, s & 0xFF
    devs = {"cdrom": Atapi(model="TOSHIBA CD-ROM XM-5302TA"),
            "disk": AtaDisk(1024, 16, 63, "QUANTUM FIREBALL 540A"), None: None}
    m.ide = IdeChannel(m, devs[master], devs[slave])
    m.write(0x408, struct.pack("<H", 0x378))         # LPT1
    m.write(0x400, struct.pack("<HH", 0x3F8, 0x2F8))  # COM1, COM2
    m.chipset[0x92], m.chipset[0x93] = 0x21, 0xF8     # L2 on, 256 KB
    if fake_rom:                                      # an option ROM at C8000 like the PicoMEM's
        rom = bytearray(16 * 1024)
        rom[0:3] = b"\x55\xAA\x20"
        rom[0x20:0x40] = b"PicoMEM BIOS v1.2 (test ROM)\0\0\0\0"
        rom[-1] = (-sum(rom)) & 0xFF
        m.write(0xC8000, rom)
    return m


def run_tools(m, keys, page=0, max_insns=200_000_000):
    """Run the Tools entry with queued keys until it waits for more input or returns."""
    m.keys = list(keys)
    try:
        m.far_call(0xE800, 0x000A, ax=page, max_insns=max_insns)
        return "returned"
    except StopEmu as e:
        return str(e)


def esc_after_polls(m, polls):
    """Make INT 16h AH=01 report Esc once it has been polled `polls` times."""
    orig = m._int16
    state = {"n": 0}

    def stub():
        ah = m.reg("ax") >> 8
        if ah == 1 and not m.keys:
            state["n"] += 1
            if state["n"] == polls:
                m.keys.append(ESC)
        orig()
    m.stubs[0x16] = stub
    return state
