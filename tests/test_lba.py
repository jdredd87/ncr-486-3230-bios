"""Tests for large-disk (LBA) mode in tools_rom.

    python tests/test_lba.py

Runs POST from the floppy check through the hard disk init (F000:4293-4371)
with simulated IDE disks, so the stock disk init and the new LBA set-up both
run, then drives INT 13h: translated CHS reads and writes, the INT 13h
extensions beyond 8.4 GB, and the drives that must stay on the stock code.
Every emulated sector holds its own LBA, so each read is checked exactly.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from emu import AtaDisk, IdeChannel, Machine, StopEmu  # noqa: E402

IMAGE = os.path.join(ROOT, "build", "NCR3230-203-improved.BIN")
if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


class NoLbaDisk(AtaDisk):
    def identify(self):
        w = bytearray(super().identify())
        w[98:100] = b"\0\0"                          # word 49: no LBA
        return bytes(w)


def sector(lba):
    return struct.pack("<I", lba) * 128              # what AtaDisk returns for an unwritten sector


def translate(total):
    heads = 32
    while heads < 255 and total > 1024 * heads * 63:
        heads = 255 if heads == 128 else heads * 2
    return min(total // (heads * 63), 1024), heads, 63


def post(master, slave=None, ctype=0x23, prep=None):
    m = Machine(IMAGE, ram_mb=2)
    m.install_rom_vectors()
    m.video_init(3)
    m.cmos[0x10], m.cmos[0x12], m.cmos[0x0E], m.cmos[0x0D] = 0x40, ctype, 0, 0x80
    m.ide = IdeChannel(m, master, slave)
    m.write(0x4AE, struct.pack("<H", 1))
    if prep:
        prep(m)
    r = m.run_to_any(0xF000, 0x4293, {(0xF000, 0x4371): "after"}, max_insns=400_000_000, ss=0, sp=0x400)
    assert r == "after"
    return m


def int13(m, **regs):
    m.int_call(0x13, ss=0x0000, sp=0x7000, **regs)
    return m.reg("ax") >> 8, m.cf()


def params(m, drive):
    ah, cf = int13(m, ax=0x0800, dx=drive)
    cx, dx = m.reg("cx"), m.reg("dx")
    return cf, ((cx >> 8) | ((cx & 0xC0) << 2)) + 1, (dx >> 8) + 1, cx & 0x3F, dx & 0xFF


def chs(cyl, head, sec):
    return ((cyl & 0xFF) << 8) | ((cyl >> 2) & 0xC0) | sec, head << 8


def dap(m, count, seg, lba, at=0x600):
    m.write(at, struct.pack("<BBHHHQ", 16, 0, count, 0, seg, lba))


# ---------------------------------------------------------------- 2 GB disk, Automatic
d = AtaDisk(4092, 16, 63, "QUANTUM FIREBALL 2.1GB")
total = 4092 * 16 * 63
L, H, S = translate(total)
m = post(d)
check(m.mem_word(0x413) == 640 and m.vector(0x13)[0] == 0xE800 and m.mem_byte(0x475) == 1,
      "2 GB: LBA mode set up after POST's disk init (INT 13h -> ROM, no base memory taken)")
hd = [(a, p) for a, _, _, p in m.rom_writes if 0xFEED6 <= a < 0xFEF06]
check(hd and all(p == 0 for a, p in hd) and m.chipset[0x9B] & 1,
      "2 GB: tables written to F000 with the shadow unlocked, then locked again")
cf, c, h, s, n = params(m, 0x80)
check(not cf and (c, h, s, n) == (L, H, S, 1) and (L, H) == (1023, 64),
      "2 GB: AH=08h reports the LBA-assisted geometry %d/%d/%d" % (c, h, s))
tbl = m.read(0xFEEE6, 16)
check(m.vector(0x41) == (0xF000, 0xEEE6) and struct.unpack_from("<H", tbl)[0] == L and tbl[2] == H and tbl[3] == 0xA0
      and tbl[14] == 63 and sum(tbl) & 0xFF == 0, "2 GB: INT 41h -> translated table (A0h signature, checksum)")
lba = (1000 * H + 50) * S + 9
cx, dx = chs(1000, 50, 10)
ah, cf = int13(m, ax=0x0203, cx=cx, dx=dx | 0x80, es=0x2000, bx=0)
check(not cf and m.reg("ax") == 0x0003 and m.read(0x20000, 1536) == sector(lba) + sector(lba + 1) + sector(lba + 2),
      "2 GB: AH=02h reads CHS 1000/50/10 = LBA %d (above the old 504 MB)" % lba)
m.write(0x30000, b"\xA5" * 512 + b"\x5A" * 512)
ah, cf = int13(m, ax=0x0302, cx=cx, dx=dx | 0x80, es=0x3000, bx=0)
check(not cf and d.sectors.get(lba) == b"\xA5" * 512 and d.sectors.get(lba + 1) == b"\x5A" * 512,
      "2 GB: AH=03h writes to the right sectors")
ah, cf = int13(m, ax=0x0202, cx=cx, dx=dx | 0x80, es=0x4000, bx=0)
check(not cf and m.read(0x40000, 1024) == b"\xA5" * 512 + b"\x5A" * 512, "2 GB: ...and reads them back")
ah, cf = int13(m, ax=0x0410, cx=cx, dx=dx | 0x80)
check(not cf and m.reg("ax") == 0x0010, "2 GB: AH=04h verifies")
ah, cf = int13(m, ax=0x1500, dx=0x80)
check(not cf and ah == 3 and (m.reg("cx") << 16 | m.reg("dx")) == L * H * S, "2 GB: AH=15h: fixed disk, sector count")
cx, dx = chs(L, 0, 1)
ah, cf = int13(m, ax=0x0201, cx=cx, dx=dx | 0x80, es=0x2000, bx=0)
check(cf and ah == 0x04, "2 GB: a cylinder past the end -> AH=04h")
ah, cf = int13(m, ax=0x4100, bx=0x55AA, dx=0x80)
check(not cf and ah == 0x21 and m.reg("bx") == 0xAA55 and m.reg("cx") & 1, "2 GB: AH=41h reports the extensions")
ah, cf = int13(m, ax=0x0100, dx=0x80)
check(not cf and ah == 0 and m.mem_byte(0x474) == 0, "2 GB: AH=01h status")

# ---------------------------------------------------------------- 34 GB disk: beyond 8.4 GB with the extensions
d = AtaDisk(65535, 16, 63, "MAXTOR 34GB")
total = 65535 * 16 * 63
m = post(d)
cf, c, h, s, n = params(m, 0x80)
check(not cf and (c, h, s) == (1024, 255, 63), "34 GB: CHS view is capped at 1024/255/63 (8.4 GB)")
dap(m, 3, 0x2000, 60_000_000)
ah, cf = int13(m, ax=0x4200, dx=0x80, ds=0, si=0x600)
check(not cf and m.read(0x20000, 1536) == sector(60_000_000) + sector(60_000_001) + sector(60_000_002)
      and m.mem_word(0x602) == 3, "34 GB: AH=42h reads LBA 60,000,000 (about 30 GB in)")
dap(m, 200, 0x2000, 1000)
ah, cf = int13(m, ax=0x4200, dx=0x80, ds=0, si=0x600)
check(not cf and m.read(0x20000, 200 * 512) == b"".join(sector(1000 + i) for i in range(200)),
      "34 GB: a 200-sector read (two ATA commands, across 64 KB)")
m.write(0x50000, bytes(range(256)) * 2)
dap(m, 1, 0x5000, total - 1)
ah, cf = int13(m, ax=0x4300, dx=0x80, ds=0, si=0x600)
check(not cf and d.sectors.get(total - 1) == bytes(range(256)) * 2, "34 GB: AH=43h writes the very last sector")
dap(m, 2, 0x5000, total - 1)
ah, cf = int13(m, ax=0x4200, dx=0x80, ds=0, si=0x600)
check(cf and ah == 0x04 and m.mem_word(0x602) == 0, "34 GB: a read past the end -> AH=04h, nothing transferred")
m.write(0x700, struct.pack("<H", 0x1A) + bytes(0x18))
ah, cf = int13(m, ax=0x4800, dx=0x80, ds=0, si=0x700)
p = m.read(0x700, 0x1A)
check(not cf and struct.unpack_from("<Q", p, 16)[0] == total and struct.unpack_from("<H", p, 24)[0] == 512,
      "34 GB: AH=48h reports all %d sectors" % total)

# ---------------------------------------------------------------- drives that stay on the stock code
m = post(AtaDisk(615, 4, 17))
check(m.mem_word(0x413) == 640 and m.vector(0x13) == (0xF000, 0x94E3), "615/4/17 disk: stock handler, no memory taken")
ah, cf = int13(m, ax=0x4100, bx=0x55AA, dx=0x80)
check(cf, "615/4/17 disk: no extensions, exactly as before")
m = post(NoLbaDisk(2000, 16, 63))
check(m.vector(0x13) == (0xF000, 0x94E3) and params(m, 0x80)[1:4] == (1023, 16, 63),
      "a big disk without LBA: stock handler, fitted to 1024/16/63 as before")


def user_1024(m):
    m.cmos[0x72:0x7C] = struct.pack("<HBHBBHB", 1024, 16, 0xFFFF, 0, 8, 1024, 63)
    m.cmos[0x7C] = sum(m.cmos[0x72:0x7C]) & 0xFF


m = post(AtaDisk(4092, 16, 63), ctype=0x10, prep=user_1024)
check(m.vector(0x13) == (0xF000, 0x94E3), "a big disk set to user type 1024/16/63 keeps the old 504 MB layout")

# ---------------------------------------------------------------- big C:, small D:
big, small = AtaDisk(4092, 16, 63), AtaDisk(615, 4, 17)
m = post(big, small)
check(m.mem_byte(0x475) == 2 and params(m, 0x80)[1:3] == (1023, 64), "big C: + small D: -> C: in LBA mode")
cf, c, h, s, n = params(m, 0x81)
check(not cf and (c, h, s, n) == (614, 4, 17, 2), "...D: keeps its own geometry through the stock handler")
cx, dx = chs(10, 2, 5)
ah, cf = int13(m, ax=0x0201, cx=cx, dx=dx | 0x81, es=0x2000, bx=0)
check(not cf and m.read(0x20000, 512) == sector((10 * 4 + 2) * 17 + 4), "...D: reads the right sector")
cx, dx = chs(900, 63, 63)
ah, cf = int13(m, ax=0x0201, cx=cx, dx=dx | 0x80, es=0x2000, bx=0)
check(not cf and m.read(0x20000, 512) == sector((900 * 64 + 63) * 63 + 62), "...and C: after a D: access")

# ---------------------------------------------------------------- booting, Tools, no shadow RAM
d = AtaDisk(4092, 16, 63, "QUANTUM FIREBALL 2.1GB")
mbr = bytearray(512)
mbr[0:2], mbr[510:512] = b"\xEB\xFE", b"\x55\xAA"
d.sectors[0] = bytes(mbr)
m = post(d)
m.write(0x4F0, struct.pack("<HB", 0x424E, 0x80))    # boot menu: C: (the stock INT 19h would try A: first)
try:
    r = m.run_to_any(0xF000, 0xE6F2, {(0x0000, 0x7C00): "boot"}, max_insns=400_000_000, ss=0, sp=0x7B00)
except StopEmu as e:
    r = str(e)
check(r == "boot" and m.read(0x7C00, 512) == bytes(mbr) and m.reg("dx") & 0xFF == 0x80,
      "INT 19h boots the large disk's MBR through the new handler")

sys.path.insert(0, HERE)
from tools_harness import key, run_tools  # noqa: E402
m = post(AtaDisk(4092, 16, 63, "QUANTUM FIREBALL 2.1GB"))
run_tools(m, [key("2")])
t = m.screen_text()
check("QUANTUM FIREBALL 2.1GB  (disk, 2014 MB, LBA)" in t and "1023/64/63" in t,
      "Tools drives page: the disk is marked LBA and C: shows 1023/64/63")
m = post(AtaDisk(615, 4, 17, "OLD DISK"))
run_tools(m, [key("2")])
check("OLD DISK  (disk, 20 MB)" in m.screen_text(), "Tools drives page: a small disk is not marked LBA")


def read_only_f000(m):
    from unicorn import UC_HOOK_MEM_WRITE_PROT, UC_PROT_EXEC, UC_PROT_READ
    m.uc.mem_protect(0xF0000, 0x10000, UC_PROT_READ | UC_PROT_EXEC)
    m.uc.hook_add(UC_HOOK_MEM_WRITE_PROT, lambda *a: True)   # writes are dropped, as with no shadow RAM


m = post(AtaDisk(4092, 16, 63), prep=read_only_f000)
check(m.vector(0x13) == (0xF000, 0x94E3) and m.vector(0x41)[1] != 0xEEE6 and int13(m, ax=0x4100, bx=0x55AA, dx=0x80)[1],
      "BIOS not shadowed (F000 not writable): LBA mode stays off, stock handler")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
