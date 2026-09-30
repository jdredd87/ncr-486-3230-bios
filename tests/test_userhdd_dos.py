"""The real DOS USERHDD.EXE, run in the emulator against simulated IDE devices.

Covers the parts the Windows simulation build can't: CMOS port I/O in the
8086 assembler routines, /DETECT (IDENTIFY over ports 1F0h-1F7h), the NCR
signature check, and interactive input. Results are then fed to the BIOS's
own POST copy routine (F000:3C58).
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from dosemu import DosMachine  # noqa: E402
from emu import AtaDisk, Atapi, IdeChannel, Machine, cmos_checksum  # noqa: E402

EXE = os.path.join(HERE, "..", "userhdd", "dos", "userhdd.exe")
failed = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def machine(master=None, slave=None, float_value=0xFF, image=None):
    d = DosMachine() if image is None else DosMachine(image)
    d.cmos[0x10], d.cmos[0x14] = 0x40, 0x41
    cmos_checksum(d.cmos)
    d.ide = IdeChannel(d, master, slave, float_value)
    return d


def post_table(cmos):
    m = Machine()
    m.cmos[:] = cmos
    m.run_until(0xF000, 0x3C58, 0xF000, 0x3D22, ds=0x40, bp=0)
    t = m.read(0xFE401, 16)
    return struct.unpack_from("<H", t)[0], t[2], t[14], m.mem_byte(0x415) & 0x40


# 1. command-line geometry, written through the real port I/O code
d = machine()
rc = d.run_exe(EXE, "1024 16 63 /C /Y")
check(rc == 0, "write 1024/16/63 /C exits 0")
check("written and verified" in d.stdout, "tool reports verified write")
check(d.cmos[0x12] >> 4 == 1, "drive C set to type 1")
cyl, hd, spt, bad = post_table(d.cmos)
check((cyl, hd, spt, bad) == (1024, 16, 63, 0), "POST accepts and copies %d/%d/%d" % (cyl, hd, spt))

# 2. /DETECT on a big modern drive: clamped to 1024 cylinders
d = machine(master=AtaDisk(16383, 16, 63, "BIG MODERN DRIVE"))
rc = d.run_exe(EXE, "/DETECT /C /Y")
check(rc == 0, "/DETECT big drive exits 0")
check("BIG MODERN DRIVE" in d.stdout, "model string decoded")
check("using 1024" in d.stdout, "clamps >1024 cylinders")
cyl, hd, spt, bad = post_table(d.cmos)
check((cyl, hd, spt) == (1024, 16, 63), "big drive -> 1024/16/63")

# 3. /DETECT on an old small drive
d = machine(master=AtaDisk(615, 4, 17, "OLD 20MB"))
rc = d.run_exe(EXE, "/DETECT /Y")
cyl, hd, spt, bad = post_table(d.cmos)
d.cmos[0x12] = 0x10
cyl, hd, spt, bad = post_table(d.cmos)
check(rc == 0 and (cyl, hd, spt) == (615, 4, 17), "old drive -> 615/4/17")

# 4. /DETECT /SLAVE
d = machine(master=AtaDisk(615, 4, 17), slave=AtaDisk(980, 10, 17, "SLAVE DRIVE"))
rc = d.run_exe(EXE, "/DETECT /SLAVE /D /Y")
d.cmos[0x12] &= 0x0F
cyl, hd, spt, bad = post_table(d.cmos)
check(rc == 0 and "SLAVE DRIVE" in d.stdout and (cyl, hd, spt) == (980, 10, 17),
      "slave drive detected -> 980/10/17 and set as D:")

# 5. /DETECT on a CD-ROM: refuses, writes nothing
d = machine(master=Atapi())
before = bytes(d.cmos)
rc = d.run_exe(EXE, "/DETECT /C /Y")
check(rc != 0 and "ATAPI" in d.stdout and bytes(d.cmos) == before, "CD-ROM recognised, nothing written")

# 6. /DETECT with nothing connected (floating bus 0xFF and pulled-down 0x7F)
for fv in (0xFF, 0x7F):
    d = machine(float_value=fv)
    before = bytes(d.cmos)
    rc = d.run_exe(EXE, "/DETECT /Y", max_insns=200_000_000)
    check(rc != 0 and "No drive" in d.stdout and bytes(d.cmos) == before,
          "no drive (bus reads %02Xh): reported, nothing written" % fv)

# 7. interactive entry
d = machine()
rc = d.run_exe(EXE, "", stdin="977\n5\n17\n65535\n977\ny\n")
cyl, hd, spt, bad = post_table(bytes(d.cmos[:0x12]) + b"\x10" + bytes(d.cmos[0x13:]))
check(rc == 0 and (cyl, hd, spt) == (977, 5, 17), "interactive entry 977/5/17")

# 8. answering N writes nothing
d = machine()
before = bytes(d.cmos)
rc = d.run_exe(EXE, "977 5 17", stdin="n\n")
check(rc == 0 and bytes(d.cmos) == before and "Nothing written" in d.stdout, "answer N: nothing written")

# 9. refuses to run on a non-NCR BIOS
img = bytearray(open(os.path.join(HERE, "..", "NCR-BIOS-517-0000672-VER2.03.00-U19.BIN"), "rb").read())
img[0x1FFEA:0x1FFED] = b"XYZ"
d = machine(image=bytes(img))
before = bytes(d.cmos)
rc = d.run_exe(EXE, "1024 16 63 /C /Y")
check(rc == 2 and bytes(d.cmos) == before, "non-NCR BIOS: refuses, nothing written")

print("unknown DOS calls:", sorted(set(hex(x) for x in d.unknown)) or "none")
sys.exit(1 if failed else 0)
