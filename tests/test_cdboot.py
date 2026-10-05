"""Tests for the CD-ROM boot (El Torito) in tools_rom.

    python tests/test_cdboot.py

Builds small El Torito ISO images in memory, attaches them to the emulated
ATAPI drive and runs the real ROM code from INT 19h: floppy-emulation and
no-emulation boots, then the INT 13h service the booted system uses (CHS
reads of the emulated floppy, extended reads of the CD, the El Torito status
call), drive remapping, and the failure paths (no drive, no disc, a disc that
is not bootable).
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tools_harness import ESC, AtaDisk, Atapi, IdeChannel, StopEmu, key, machine, run_tools  # noqa: E402

if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(HERE, "..", "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []
POST_STACK = dict(ss=0x0000, sp=0x0400)
STOPS = {(0x0000, 0x7C00): "boot", (0x1000, 0x0000): "boot1000", (0xF000, 0xE066): "normal"}
CF = 1


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


from isotools import boot_sector, make_iso, pattern  # noqa: E402


FLOPPY = boot_sector() + pattern(2400, b"FD12")[512:]          # 1.2 MB, 80/2/15
FLOPPY144 = boot_sector() + pattern(2880, b"FD44")[512:]       # 1.44 MB, 80/2/18
NOEMU = b"\xEB\xFE" + pattern(4, b"NOEM")[2:]                  # 2 KB loader


def boot(iso=None, disk=False, cd_slave=None, prep=None, keys=(), equip=0x0000):
    m = machine(master=None)
    cd = Atapi(iso, model="TOSHIBA CD-ROM XM-5302TA") if iso is not None else None
    master = AtaDisk(1024, 16, 63, "QUANTUM FIREBALL 540A") if disk else cd
    slave = cd if disk else None
    m.ide = IdeChannel(m, master, slave)
    if disk:
        m.cmos[0x12] = 0x20
        m.write(0x4AE, struct.pack("<H", 1))
        m.set_vector(0x13, 0xF000, 0xEC59)
        m.near_call(0xF000, 0x9062, max_insns=400_000_000, ds=0x40, es=0, **POST_STACK)
    m.write(0x410, struct.pack("<H", equip))
    m.write(0x4F0, struct.pack("<HB", 0x424E, 0xE0))
    m.vec13_before = m.vector(0x13)
    if prep:
        prep(m)
    m.keys = list(keys)
    try:
        r = m.run_to_any(0xF000, 0xE6F2, STOPS, max_insns=400_000_000, ss=0, sp=0x7B00)
    except StopEmu as e:
        r = str(e)
    return r, m


def int13(m, **regs):
    m.int_call(0x13, ss=0x0000, sp=0x6800, **regs)
    return m.reg("ax"), m.cf()


def regs8(m, name):
    v = m.reg(name)
    return v >> 8, v & 0xFF


def text(m):
    return m.screen_text()


def iso_bytes(m):
    d = m.ide.dev[1] if isinstance(m.ide.dev[1], Atapi) else m.ide.dev[0]
    return d.iso


# ---------------------------------------------------------------- boot menu
m = machine(master="cdrom")
run_tools(m, [], page=1)
check("3  CD-ROM (TOSHIBA CD-ROM XM-5302TA)" in text(m), "menu: lists the CD-ROM drive by name")
m = machine(master="cdrom")
run_tools(m, [key("3")], page=1)
check(m.mem_word(0x4F0) == 0x424E and m.mem_byte(0x4F2) == 0xE0, "menu: 3 stores a one-shot CD-ROM boot")
m = machine(master="disk")
run_tools(m, [], page=1)
check("3  CD-ROM (no drive found)" in text(m), "menu: says when there is no CD-ROM drive")

# ---------------------------------------------------------------- floppy emulation (1.2 MB)
r, m = boot(make_iso(FLOPPY, 1))
seg = m.mem_word(0x413) * 64
check(r == "boot" and m.reg("dx") & 0xFF == 0x00 and m.read(0x7C00, 512) == FLOPPY[:512],
      "floppy emulation: boot sector loaded at 0:7C00, DL=00h")
check(m.mem_word(0x413) == 637 and m.vector(0x13) == (seg, 0),
      "floppy emulation: 3 KB taken from base memory for the INT 13h service")
check("floppy emulation: the CD is drive A:" in text(m), "floppy emulation: message on screen")
check(m.mem_word(0x410) & 0xC1 == 0x01, "floppy emulation: equipment word shows one floppy drive")

ax, cf = int13(m, ax=0x0201, cx=0x0101, dx=0x0100, es=0x2000, bx=0)    # C1 H1 S1 -> sector 45
check(not cf and ax == 0x0001 and m.read(0x20000, 512) == FLOPPY[45 * 512:46 * 512],
      "floppy emulation: INT 13h AH=02h reads CHS 1/1/1 (image sector 45)")
ax, cf = int13(m, ax=0x0206, cx=0x0003, dx=0x0000, es=0x2000, bx=0x0010)
check(not cf and ax == 0x0006 and m.read(0x20010, 6 * 512) == FLOPPY[2 * 512:8 * 512],
      "floppy emulation: a 6-sector read across CD sectors")
ax, cf = int13(m, ax=0x020F, cx=0x4F01, dx=0x0100, es=0x3000, bx=0)    # last track
check(not cf and ax == 0x000F and m.read(0x30000, 15 * 512) == FLOPPY[2385 * 512:],
      "floppy emulation: the last track (cylinder 79, head 1)")
ax, cf = int13(m, ax=0x0201, cx=0x0010, dx=0x0000, es=0x2000, bx=0)
check(cf and ax >> 8 == 0x04, "floppy emulation: sector 16 of a 15-sector track -> AH=04h")
ax, cf = int13(m, ax=0x0301, cx=0x0001, dx=0x0000, es=0x2000, bx=0)
check(cf and ax >> 8 == 0x03, "floppy emulation: writes fail as write-protected (AH=03h)")
ax, cf = int13(m, ax=0x0100, dx=0x0000)
check(not cf and ax >> 8 == 0x03, "floppy emulation: AH=01h returns the last status")
ax, cf = int13(m, ax=0x0800, dx=0x0000)
cx, dx, bx = m.reg("cx"), m.reg("dx"), m.reg("bx")
check(not cf and bx & 0xFF == 2 and cx == 0x4F0F and dx == 0x0101,
      "floppy emulation: AH=08h reports a 1.2 MB drive, 80/2/15, one drive")
ax, cf = int13(m, ax=0x1500, dx=0x0000)
check(not cf and ax >> 8 == 0x01, "floppy emulation: AH=15h floppy without change line")
ax, cf = int13(m, ax=0x4B01, dx=0x007F, ds=0x0000, si=0x0600)
spec = m.read(0x600, 0x13)
check(not cf and spec[0] == 0x13 and spec[1] == 1 and spec[2] == 0 and struct.unpack_from("<I", spec, 4)[0] == 20,
      "floppy emulation: AX=4B01h returns the specification packet")
ax, cf = int13(m, ax=0x0800, dx=0x0080)
check(m.vector(0x13)[0] == seg, "floppy emulation: other drives go on to the BIOS")

r, m = boot(make_iso(FLOPPY144, 2), equip=0x0001)
check(r == "boot" and "the floppy drive is B:" in text(m) and m.mem_word(0x410) & 0xC1 == 0x41,
      "floppy emulation (1.44 MB) with a real drive: it becomes B:, two drives")
ax, cf = int13(m, ax=0x0800, dx=0x0001)
check(not cf and m.reg("dx") & 0xFF == 2 and m.reg("bx") & 0xFF == 4,
      "floppy emulation: B: answers as the real 1.44 MB drive A:")
ax, cf = int13(m, ax=0x0800, dx=0x0000)
check(not cf and m.reg("cx") == 0x4F12 and m.reg("dx") & 0xFF == 2, "floppy emulation: A: is 80/2/18, two drives")

# ---------------------------------------------------------------- no emulation
iso = make_iso(NOEMU, 0, count=4)
r, m = boot(iso)
check(r == "boot" and m.reg("dx") & 0xFF == 0xE0 and m.read(0x7C00, 2048) == NOEMU,
      "no emulation: 2 KB loader at 0:7C00, DL=E0h")
check("no emulation: the CD is drive E0h" in text(m), "no emulation: message on screen")
check(m.mem_word(0x410) == 0, "no emulation: floppy drives left alone")
ax, cf = int13(m, ax=0x4100, bx=0x55AA, dx=0x00E0)
check(not cf and ax >> 8 == 0x21 and m.reg("bx") == 0xAA55 and m.reg("cx") & 1,
      "no emulation: AH=41h reports the INT 13h extensions")
m.write(0x600, struct.pack("<BBHHHQ", 16, 0, 3, 0x0000, 0x4000, 20))
ax, cf = int13(m, ax=0x4200, dx=0x00E0, ds=0, si=0x600)
check(not cf and m.read(0x40000, 6144) == iso[20 * 2048:23 * 2048] and m.mem_word(0x602) == 3,
      "no emulation: AH=42h reads 2048-byte sectors")
m.write(0x600, struct.pack("<BBHHHQ", 16, 0, 40, 0x0000, 0x5000, 0))
ax, cf = int13(m, ax=0x4200, dx=0x00E0, ds=0, si=0x600)
check(not cf and m.read(0x50000, 40 * 2048) == iso.ljust(40 * 2048, b"\0")[:40 * 2048], "no emulation: a 40-sector (80 KB) read")
m.write(0x600, struct.pack("<H", 0x1A) + bytes(0x18))
ax, cf = int13(m, ax=0x4800, dx=0x00E0, ds=0, si=0x600)
check(not cf and m.mem_word(0x600 + 24) == 2048, "no emulation: AH=48h reports 2048-byte sectors")
ax, cf = int13(m, ax=0x4B01, dx=0x00E0, ds=0, si=0x700)
spec = m.read(0x700, 0x13)
check(not cf and spec[1] == 0 and spec[2] == 0xE0 and struct.unpack_from("<H", spec, 14)[0] == 4,
      "no emulation: AX=4B01h specification packet")
ax, cf = int13(m, ax=0x0201, cx=1, dx=0x00E0, es=0x2000, bx=0)
check(cf and ax >> 8 == 0x01, "no emulation: CHS reads of the CD are refused")

r, m = boot(make_iso(NOEMU, 0, count=4, load_seg=0x1000))
check(r == "boot1000" and m.read(0x10000, 2048) == NOEMU, "no emulation: loader at its own load segment (1000h)")

# ---------------------------------------------------------------- CD-ROM as slave, hard disk as master
r, m = boot(make_iso(NOEMU, 0, count=4), disk=True)
check(r == "boot" and m.read(0x7C00, 2048) == NOEMU, "slave CD-ROM next to a hard disk boots")
ax, cf = int13(m, ax=0x0201, cx=0x0002, dx=0x0080, es=0x2000, bx=0)
check(not cf and m.read(0x20000, 8) == bytes([1, 0, 0, 0]) * 2,
      "hard disk C: still reads through the BIOS after a CD boot")
m.write(0x600, struct.pack("<BBHHHQ", 16, 0, 1, 0x0000, 0x4000, 19))
ax, cf = int13(m, ax=0x4200, dx=0x00E0, ds=0, si=0x600)
check(not cf and m.read(0x40000, 2) == b"\x01\x00", "...and the CD after a hard-disk access")


# ---------------------------------------------------------------- slow drive, failures
def slow_drive(n):
    def prep(m):
        orig = m.ide.packet
        state = {"n": n}

        def pk(pkt):
            if pkt[0] == 0x00 and state["n"] > 0:
                state["n"] -= 1
                m.ide.cur().sense = 0x02
                return m.ide.check_condition()
            return orig(pkt)
        m.ide.packet = pk
    return prep


r, m = boot(make_iso(FLOPPY, 1), prep=slow_drive(8))
check(r == "boot" and "waiting for the disc" in text(m), "a drive that takes a while to spin up is waited for")
r, m = boot(make_iso(FLOPPY, 1), prep=slow_drive(10**6), keys=[ESC])
check(r == "normal" and "did not become ready" in text(m) and m.mem_word(0x413) == 640,
      "no disc: Esc cancels, memory is given back, normal boot order")
r, m = boot(make_iso(FLOPPY, 1, eltorito=False))
check(r == "normal" and "not bootable" in text(m) and m.vector(0x13) == m.vec13_before,
      "a data CD (no El Torito record) -> message, INT 13h untouched, normal order")
r, m = boot(make_iso(FLOPPY, 1, bootable=False))
check(r == "normal" and "not bootable" in text(m), "a boot catalog without a bootable entry -> normal order")
r, m = boot(make_iso(FLOPPY, 4))
check(r == "normal" and "hard-disk emulation" in text(m), "hard-disk emulation images are refused")
r, m = boot(b"")
check(r == "normal" and "not bootable" in text(m) and m.mem_word(0x413) == 640, "an empty drive -> normal order")
r, m = boot(None, disk=True)
check(r == "normal" and "no CD-ROM drive" in text(m), "no CD-ROM drive -> message, normal order")
check(m.mem_word(0x4F0) == 0, "the CD-ROM choice is one-shot")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
