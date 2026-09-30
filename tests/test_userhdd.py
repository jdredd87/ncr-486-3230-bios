"""USERHDD.EXE (simulation build) vs. the BIOS's own POST and Setup code.

Runs userhdd/sim/userhdd.exe against a CMOS.BIN, then executes the real ROM:
  F000:3C58-3D22  POST copy of CMOS 72h-7Ch into the type-1 table at F000:E401
  F000:2B4C-2BBA  POST standard checksum check (10h-2Dh vs 2Eh/2Fh)
  FA40:1232-1253  Setup's type-1 validity check (CF=0 means accepted)
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from emu import Machine, cmos_checksum  # noqa: E402

SIM = os.path.join(HERE, "..", "userhdd", "sim", "userhdd.exe")


def base_cmos():
    c = bytearray(128)
    c[0x0A], c[0x0B], c[0x0D] = 0x26, 0x02, 0x80
    c[0x10] = 0x40            # A: 1.44 MB
    c[0x14] = 0x41            # 1 floppy, VGA
    c[0x15], c[0x16] = 0x80, 0x02
    cmos_checksum(c)
    return c


def run_tool(cmos, *args):
    d = tempfile.mkdtemp()
    try:
        open(os.path.join(d, "CMOS.BIN"), "wb").write(cmos)
        r = subprocess.run([SIM, *args], cwd=d, capture_output=True, text=True, input="")
        out = bytearray(open(os.path.join(d, "CMOS.BIN"), "rb").read())
        return r.returncode, r.stdout, out
    finally:
        shutil.rmtree(d)


def post_copy(cmos):
    m = Machine()
    m.cmos[:] = cmos
    m.run_until(0xF000, 0x3C58, 0xF000, 0x3D22, ds=0x40, bp=0)
    return m


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        check.failed = True


check.failed = False


def geometry_case(cyl, heads, spt, drive):
    rc, out, cm = run_tool(base_cmos(), str(cyl), str(heads), str(spt), "/" + drive, "/Y")
    check(rc == 0, "tool exit code 0 for %d/%d/%d /%s (got %d)" % (cyl, heads, spt, drive, rc))
    nib = cm[0x12] >> 4 if drive == "C" else cm[0x12] & 0xF
    check(nib == 1, "CMOS 12h drive %s nibble is 1 (12h=%02X)" % (drive, cm[0x12]))

    m = post_copy(cm)
    t = m.read(0xFE401, 16)
    cyl_t, heads_t = struct.unpack_from("<HB", t)
    wpc = struct.unpack_from("<H", t, 5)[0]
    ctl, lz, spt_t = t[8], struct.unpack_from("<H", t, 12)[0], t[14]
    check((cyl_t, heads_t, spt_t) == (cyl, heads, spt),
          "POST copied geometry into F000:E401: %d/%d/%d" % (cyl_t, heads_t, spt_t))
    check(wpc == 0xFFFF and lz == cyl, "precomp none, landing zone = cylinders")
    check(ctl == (0x08 if heads > 8 else 0), "control byte %02X (bit 3 = >8 heads)" % ctl)
    check((m.mem_byte(0x415) & 0x40) == 0, "POST did not flag 'User defined HDD Table not correct'")
    unlocked = [w for w in m.rom_writes if 0xFE401 <= w[0] < 0xFE411]
    check(unlocked and all(w[3] == 0 for w in unlocked),
          "every table write happened with shadow write-protect off")
    check(m.chipset[0x9B] & 1 == 1, "shadow write-protect restored afterwards")

    # POST standard checksum check
    m2 = Machine()
    m2.cmos[:] = cm
    m2.run_until(0xF000, 0x2B4C, 0xF000, 0x2BBA, ds=0x40)
    check((m2.mem_byte(0x415) & 0x08) == 0, "POST checksum check passes (no 'Configuration not Set')")

    # Setup's check that type 1 may be selected
    m3 = Machine()
    m3.cmos[:] = cm
    m3.run_until(0xFA40, 0x1232, 0xFA40, 0x1253, ds=0x70)
    check(not m3.cf(), "Setup accepts type 1")


geometry_case(1024, 16, 63, "C")
geometry_case(615, 4, 17, "D")
geometry_case(1, 1, 1, "C")

# Negative control: a corrupted table must be rejected by POST and Setup.
rc, out, cm = run_tool(base_cmos(), "1024", "16", "63", "/C", "/Y")
cm[0x7B] ^= 0x01
m = post_copy(cm)
check((m.mem_byte(0x415) & 0x40) != 0, "corrupted table: POST flags 'User defined HDD Table not correct'")
m3 = Machine()
m3.cmos[:] = cm
m3.run_until(0xFA40, 0x1232, 0xFA40, 0x1253, ds=0x70)
check(m3.cf(), "corrupted table: Setup refuses type 1")

# Tool rejects out-of-range input and leaves CMOS alone.
before = base_cmos()
rc, out, cm = run_tool(before, "2000", "16", "63", "/Y")
check(rc != 0 and cm == before, "out-of-range cylinders rejected, CMOS unchanged")

# /SHOW reports a valid table.
rc, out, cm = run_tool(run_tool(base_cmos(), "977", "5", "17", "/C", "/Y")[2], "/SHOW")
check("valid" in out and "977 cylinders" in out, "/SHOW reports the table")

sys.exit(1 if check.failed else 0)
