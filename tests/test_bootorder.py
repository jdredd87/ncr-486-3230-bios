"""Tests for the saved boot order (tools_rom).

    python tests/test_bootorder.py

The order editor (boot menu, O) and what INT 19h then does with a hard disk,
a CD-ROM (bootable disc, data disc or no disc), a floppy and an option ROM
that hooked INT 19h (a stand-in for the PicoMEM), including the option ROM
handing back to the BIOS.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from isotools import boot_sector, make_iso, pattern  # noqa: E402
from tools_harness import (ESC, F8, AtaDisk, Atapi, IdeChannel, StopEmu, key,  # noqa: E402
                           machine, run_tools)

if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(HERE, "..", "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []
POST_STACK = dict(ss=0x0000, sp=0x0400)
G_POSTEND = 0xF860 + 3
ROMBOOT = (0xC800, 0x0100)
STOPS = {(0x0000, 0x7C00): "boot", (0xF000, 0xE066): "stock", ROMBOOT: "rom"}
A, C, CD, ROM = 1, 2, 3, 4
RIGHT, DOWN = 0x4D00, 0x5000


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def set_order(m, *devs):
    d = list(devs) + [0] * (4 - len(devs))
    m.cmos[0x4A], m.cmos[0x4B], m.cmos[0x4C] = ord("O"), d[0] << 4 | d[1], d[2] << 4 | d[3]
    m.cmos[0x4D] = ~(m.cmos[0x4A] + m.cmos[0x4B] + m.cmos[0x4C]) & 0xFF


def saved_order(m):
    c = m.cmos
    if c[0x4A] != ord("O") or c[0x4D] != ~(c[0x4A] + c[0x4B] + c[0x4C]) & 0xFF:
        return None
    return [c[0x4B] >> 4, c[0x4B] & 15, c[0x4C] >> 4, c[0x4C] & 15]


FLOPPY = boot_sector() + pattern(2880, b"FD44")[512:]


def setup(cd="none", mbr=True, rom=False, floppy_fails=True):
    """Hard disk master (bootable MBR), CD-ROM slave: 'boot' disc, 'data' disc or 'none'."""
    m = machine(master=None, flag=0xA5)
    disk = AtaDisk(1024, 16, 63, "QUANTUM FIREBALL 540A")
    if mbr:
        disk.sectors[0] = boot_sector()
    iso = {"boot": make_iso(FLOPPY, 2), "data": make_iso(FLOPPY, 2, eltorito=False), "none": b""}[cd]
    m.ide = IdeChannel(m, disk, Atapi(iso, model="TOSHIBA CD-ROM XM-5302TA", no_disc=(cd == "none")))
    m.cmos[0x12] = 0x20
    m.write(0x4AE, struct.pack("<H", 1))
    m.set_vector(0x13, 0xF000, 0xEC59)
    m.near_call(0xF000, 0x9062, max_insns=400_000_000, ds=0x40, es=0, **POST_STACK)
    if floppy_fails:                                   # no FDC in the emulator: the drive has no disk
        def int40():
            m.set_regs(ax=0x8000 | (m.reg("ax") & 0xFF))
            m._setflag(1, True)
        m.stubs[0x40] = int40
    if rom:
        m.write(0xC8100, b"\xEB\xFE")
        m.set_vector(0x19, *ROMBOOT)
    return m


def postend(m):
    m.near_call(0xF000, G_POSTEND, max_insns=200_000_000, **POST_STACK)


def int19(m):
    try:
        return m.run_to_any(0xF000, 0xE6F2, STOPS, max_insns=600_000_000, ss=0, sp=0x7B00)
    except StopEmu as e:
        return str(e)


def boot(m):
    postend(m)
    return int19(m)


def turs(m):
    return sum(1 for e in m.ide.log if len(e) == 3 and e[1] == "pkt" and e[2].startswith("00"))


# ---------------------------------------------------------------- the editor
m = setup()
run_tools(m, [key("o")], page=1)
t = m.screen_text()
check("Boot order" in t and "1.    Floppy A:" in t and "4.    Option ROM boot" in t
      and "BIOS default" in t, "editor: opens from the boot menu (O), starts from A:, C:, CD-ROM, option ROM")
m = setup()
run_tools(m, [key("o"), key(" "), key("s")], page=1)
check(saved_order(m) == [C, A, CD, ROM] and "Saved: this order is used" in m.screen_text(),
      "editor: Space on place 1 makes it C: (A: swaps down); S saves to CMOS 4Ah-4Dh")
m = setup()
run_tools(m, [key("o"), DOWN, DOWN, RIGHT, RIGHT, RIGHT, key("s")], page=1)
# place 3 (CD-ROM): -> option ROM (swaps with place 4) -> none -> A: (swaps with place 1)
check(saved_order(m) == [0, C, A, CD], "editor: arrows move and change places, swapping duplicates")
m = setup()
set_order(m, CD, C)
run_tools(m, [key("o"), key("d")], page=1)
check(saved_order(m) is None and "BIOS default is used" in m.screen_text(), "editor: D goes back to the BIOS default")
m = setup()
set_order(m, CD, C)
run_tools(m, [key("o"), key(" "), ESC], page=1)
check(saved_order(m) == [CD, C, 0, 0], "editor: Esc leaves without saving")
m = setup()
set_order(m, CD, C)
run_tools(m, [], page=1)
check("CD-ROM, Hard disk C:" in m.screen_text(), "boot menu: shows the saved order")
m = setup()
set_order(m, CD, C)
m.keys = [0x1C0D]
m.cmos[0x48] = 0
m.near_call(0xF000, G_POSTEND, max_insns=200_000_000, **POST_STACK)
check("Boot order            CD-ROM, Hard disk C:" in m.screen_text(), "summary: shows the boot order")

# ---------------------------------------------------------------- booting in order
m = setup(cd="none")
set_order(m, CD, C)
r = boot(m)
check(r == "boot" and m.reg("dx") & 0xFF == 0x80 and "did not become ready" in m.screen_text()
      and "next boot device" in m.screen_text() and turs(m) <= 12,
      "CD-ROM, C: with no disc: the CD gives up quickly (%d checks), C: boots" % turs(m))
m = setup(cd="boot")
set_order(m, CD, C)
check(boot(m) == "boot" and m.reg("dx") & 0xFF == 0x00 and m.read(0x7C00, 512) == FLOPPY[:512],
      "CD-ROM, C: with a bootable disc: the CD boots")
m = setup(cd="data")
set_order(m, CD, C)
check(boot(m) == "boot" and m.reg("dx") & 0xFF == 0x80 and "not bootable" in m.screen_text(),
      "CD-ROM, C: with a data CD: C: boots")
m = setup(cd="boot")
set_order(m, C, CD)
check(boot(m) == "boot" and m.reg("dx") & 0xFF == 0x80, "C:, CD-ROM: C: boots although a bootable CD is in")
m = setup(cd="boot")
set_order(m, A, CD, C)
check(boot(m) == "boot" and m.reg("dx") & 0xFF == 0x00 and "floppy A: no boot disk" in m.screen_text()
      and m.read(0x7C00, 512) == FLOPPY[:512], "A:, CD-ROM, C:: no floppy, so the CD boots")
m = setup(mbr=False)
set_order(m, C)
check(boot(m) == "stock" and "hard disk C: not bootable" in m.screen_text(),
      "C: only, not bootable: on to the stock boot (insert system disk)")

# ---------------------------------------------------------------- option ROM (PicoMEM) in the order
m = setup(rom=True)
set_order(m, ROM, C)
check(boot(m) == "rom", "option ROM, C:: the option ROM's boot runs first")
check(int19(m) == "boot" and m.reg("dx") & 0xFF == 0x80, "...and when it hands back (INT 19h again), C: boots")
m = setup(rom=True, cd="none")
set_order(m, C, ROM)
check(boot(m) == "boot" and m.reg("dx") & 0xFF == 0x80, "C:, option ROM: C: boots, the ROM is not called")
m = setup(rom=True, mbr=False)
set_order(m, C, ROM)
check(boot(m) == "rom", "C: (not bootable), option ROM: the ROM's boot follows")
m = setup(rom=True)
set_order(m, C, CD)
m.cmos[0x4B] ^= 0x10                                   # damaged: the check byte no longer matches
check(boot(m) == "rom", "a damaged saved order -> the BIOS default (option ROM first)")

# ---------------------------------------------------------------- F8 still wins
m = setup(cd="boot")
set_order(m, C)
postend(m)
m.write(0x4F0, struct.pack("<HB", 0x424E, 0xE0))      # boot menu: CD-ROM once
check(int19(m) == "boot" and m.reg("dx") & 0xFF == 0x00, "a boot menu choice (CD-ROM) overrides the saved order")
m = setup(cd="none")
set_order(m, C)
postend(m)
m.write(0x4F0, struct.pack("<HB", 0x424E, 0x00))      # boot menu: A: once, no disk in it
check(int19(m) == "boot" and m.reg("dx") & 0xFF == 0x80, "a failed boot menu choice falls back to the saved order")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
