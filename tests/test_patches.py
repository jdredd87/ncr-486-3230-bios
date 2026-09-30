"""Behaviour tests for every BIOS patch: original ROM vs. improved ROM.

    python tests/test_patches.py [IMPROVED.BIN]

Each test runs the real ROM code in the emulator. Where it makes sense the
original is run too, to show the problem exists before the patch.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from emu import ORIGINAL, AtaDisk, Atapi, Machine, StopEmu  # noqa: E402
import hdinit  # noqa: E402

IMPROVED = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "NCR3230-203-improved.BIN")
if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


# ---------------------------------------------------------------- burn-in
def burnin(image):
    """Where does POST go from F000:474C with AH = 0 (keyboard input port forced to 0)?
    The original falls through to F000:4753 (set the burn-in marker and reboot);
    the fix jumps to F000:4769 (the normal error / F1 prompt)."""
    m = Machine(image)
    cs, ip = m.run_steps(0xF000, 0x474C, 2, ax=0x0000, ds=0x40)   # cmp ah,0 ; branch
    return {0x4753: "burnin", 0x4769: "prompt"}.get(ip, "%04X:%04X" % (cs, ip))


check(burnin(ORIGINAL) == "burnin", "original: AH=0 at F000:474C enters burn-in mode")
check(burnin(IMPROVED) == "prompt", "improved: AH=0 goes to the normal error/F1 prompt instead")


# ---------------------------------------------------------------- battery prompt
def prompt(image, keys=(), flags=0x04):
    """Run the POST error-prompt block (F000:4775) with 'battery lost' flags."""
    m = Machine(image)
    m.install_rom_vectors()
    m.keys = list(keys)
    m.write(0x46C, b"\x00\x00")
    m.tick_at(0xF9F10)
    try:
        m.run_until(0xF000, 0x4775, 0xF000, 0x47AF, ax=flags, ds=0x40, max_insns=50_000_000)
        return "continued", m
    except StopEmu as e:
        return str(e), m


r, m = prompt(ORIGINAL)
check("wait for key" in r, "original: battery-lost prompt blocks waiting for a key")
r, m = prompt(IMPROVED)
check(r == "continued" and 50 <= m.ticks_advanced <= 60,
      "improved: no key -> continues after ~3 s (%s ticks)" % getattr(m, "ticks_advanced", "?"))
check("Press <F1> for SETUP" in m.text(), "improved: prompt text still shown")
r, m = prompt(IMPROVED, keys=[0x3B00])
check(r == "continued" and getattr(m, "ticks_advanced", 0) <= 1 and m.keys == [0x3B00],
      "improved: F1 pressed -> stops waiting at once and F1 stays queued for the Setup check")
r, m = prompt(IMPROVED, flags=0x02)
check("wait for key" in r, "improved: other errors (e.g. disk failure) still wait for Enter")


# ---------------------------------------------------------------- setup year
def year(image, typed, month=0x02, day=0x29):
    """Run Setup's date handling from FA40:1091 to the validity branch at FA40:10AD."""
    m = Machine(image)
    m.write(0x700 + 8, bytes([month]))
    m.write(0x700 + 7, bytes([day]))
    m.run_until(0xFA40, 0x1091, 0xFA40, 0x10AD, ax=typed, ds=0x70, max_insns=100_000)
    return m.mem_byte(0x700 + 0x32), m.mem_byte(0x700 + 9), m.zf()


for img, name in ((ORIGINAL, "original"), (IMPROVED, "improved")):
    c, y, ok = year(img, 0x0026, 0x09, 0x30)
    exp = (0x20, 0x26, True) if img is IMPROVED else (0x00, 0x26, False)
    check((c, y, ok) == exp, "%s: typed '26' -> %02X%02X %s" % (name, c, y, "valid" if ok else "invalid"))
cases = [(0x0085, 0x02, 0x28, (0x19, 0x85, True)), (0x2024, 0x02, 0x29, (0x20, 0x24, True)),
         (0x2023, 0x02, 0x29, (0x20, 0x23, False)), (0x1999, 0x12, 0x31, (0x19, 0x99, True)),
         (0x2099, 0x12, 0x31, (0x20, 0x99, True)), (0x2100, 0x01, 0x01, (0x21, 0x00, False)),
         (0x0079, 0x01, 0x01, (0x20, 0x79, True))]
for typed, mo, dy, exp in cases:
    got = year(IMPROVED, typed, mo, dy)
    check(got == exp, "improved: %02X-%02X-%04X -> %02X%02X %s" % (
        mo, dy, typed, got[0], got[1], "valid" if got[2] else "invalid"))


# ---------------------------------------------------------------- IDE
def ide(image, **kw):
    return hdinit.run(image, **kw)


o = ide(ORIGINAL, master=Atapi())
check(o.ready_retries > 30000, "original: CD-ROM with C=auto -> %d ready retries (~32 s)" % o.ready_retries)
m = ide(IMPROVED, master=Atapi())
check(m.ready_retries == 0 and m.mem_byte(0x475) == 0 and "CD-ROM (ATAPI)" in m.text(),
      "improved: CD-ROM with C=auto -> skipped at once, 0 hard disks")
check(m.mem_byte(0x415) & 0x02 == 0, "improved: CD-ROM skip is not reported as a POST error")
check(m.mem_byte(0x48E) & 0x80 == 0, "improved: no stale IRQ 14 flag left behind")
m = ide(IMPROVED, master=Atapi(), ctype=0x40)
check(m.ready_retries == 0 and m.mem_byte(0x475) == 0, "improved: CD-ROM with C=type 4 -> skipped")
m = ide(IMPROVED, master=AtaDisk(615, 4, 17), slave=Atapi(), ctype=0x23)
t = m.read(0xFE411, 16)
check(m.mem_byte(0x475) == 1 and "Disk 1: CD-ROM" in m.text() and struct.unpack_from("<H", t)[0] == 615,
      "improved: disk + CD-ROM slave with D=auto -> C: kept (615 cyl), D: skipped")

for disk in (AtaDisk(615, 4, 17), AtaDisk(16383, 16, 63), AtaDisk(980, 10, 17)):
    o, m = ide(ORIGINAL, master=disk), ide(IMPROVED, master=AtaDisk(disk.cyl, disk.heads, disk.spt))
    same = (o.read(0xFE411, 16) == m.read(0xFE411, 16) and o.mem_byte(0x475) == m.mem_byte(0x475)
            and o.text() == m.text() and [c for c in m.cmds if c != 0xA1] == o.cmds)
    check(same and m.mem_byte(0x48E) & 0x80 == 0,
          "improved: %d/%d/%d disk handled exactly as the original (only an extra A1 probe)" % (
              disk.cyl, disk.heads, disk.spt))
for ct in (0x40, 0x10):
    o, m = ide(ORIGINAL, master=AtaDisk(940, 8, 17), ctype=ct), ide(IMPROVED, master=AtaDisk(940, 8, 17), ctype=ct)
    check(o.mem_byte(0x475) == m.mem_byte(0x475) and o.text() == m.text(),
          "improved: fixed type %d behaves as the original" % (ct >> 4))

o = ide(ORIGINAL)
m = ide(IMPROVED)
check(o.real_seconds > 10 and m.real_seconds < 0.5 and "Disk controller failure" in m.text(),
      "no drive on the cable: %.1f s -> %.2f s, same error message" % (o.real_seconds, m.real_seconds))
m = ide(IMPROVED, ctype=0x00, master=Atapi())
check(m.cmds == [] and m.mem_byte(0x475) == 0, "improved: C=0 still never touches the IDE bus")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
