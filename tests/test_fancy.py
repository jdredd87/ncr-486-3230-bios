"""Tests for fancy_boot: splash, coloured messages, the Setup switch and credits.

    python tests/test_fancy.py [IMPROVED.BIN]

Runs the real POST and Setup code from the ROM in the emulator and checks
the resulting screens (characters and colours), comparing with the original
ROM wherever the output should be unchanged.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from emu import ORIGINAL, Machine, StopEmu, cmos_checksum  # noqa: E402
from version import ED_VERSION  # noqa: E402

IMPROVED = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "NCR3230-203-improved.BIN")
if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []

MSG = {"heading": 0x5408, "kbd_error": 0x53C6, "battery": 0x5513, "disk_fail": 0x9034,
       "cache": 0x5672, "keyboard": 0x5349, "interrupts": 0x527F}


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def machine(image, flag=0x00, mode=3):
    m = Machine(image)
    m.install_rom_vectors()
    m.video_init(mode)
    m.cmos[0x10], m.cmos[0x14], m.cmos[0x15], m.cmos[0x16] = 0x40, 0x41, 0x80, 0x02
    m.cmos[0x44], m.cmos[0x47], m.cmos[0x48] = 0xE5, 0x4E, flag
    cmos_checksum(m.cmos)
    s = sum(m.cmos[0x44:0x48])
    m.cmos[0x7E], m.cmos[0x7F] = s >> 8, s & 0xFF
    return m


def post(image, flag=0x00, mode=3, messages=("heading", "kbd_error", "battery", "disk_fail", "cache")):
    m = machine(image, flag, mode)
    m.run_until(0xF000, 0x328D, 0xF000, 0x32B9, ds=0x40, max_insns=20_000_000)
    for k in messages:
        m.near_call(0xF000, 0x4D06, si=MSG[k], max_insns=2_000_000)
    return m


def row_of(m, text):
    for r, line in enumerate(m.screen_text().splitlines()):
        if text in line:
            return r, line.index(text)
    return None, None


def setup(image, keys, flag=0x00):
    m = machine(image, flag)
    m.keys = list(keys)
    try:
        m.far_call(0xFA40, 0x0003, max_insns=50_000_000, ds=0x40)
    except StopEmu:
        pass
    return m


# ---------------------------------------------------------------- splash
m = post(IMPROVED)
L = m.screen_text().splitlines()
check(L[0].startswith("╔") and L[0].endswith("╗") and L[3].startswith("╚"), "splash: double-line banner on rows 0-3")
check("NCR System 3230" in L[1] and "Enhanced Edition %s" % ED_VERSION in L[1], "splash: title line with our version")
tools = m.read(0xE8000, 4) == b"NCRX"
if tools:
    check("Enhanced by StevenC & Claude" in L[2] and "F1 Setup  F8 Boot menu  F10 Tools" in L[2],
          "splash: credits and F1/F8/F10 hints (Tools extension present)")
else:
    check("Enhanced by StevenC & Claude" in L[2] and "Press <F1> for SETUP" in L[2], "splash: credits and F1 hint")
mx = machine(IMPROVED)
mx.write(0xE8000, b"\xFF" * 0x8000)                 # board that does not map E8000
mx.run_until(0xF000, 0x328D, 0xF000, 0x32B9, ds=0x40, max_insns=20_000_000)
check("Press <F1> for SETUP" in mx.screen_text().splitlines()[2], "splash: without the extension only the F1 hint")
check(L[5].startswith("ROM BIOS Version"), "splash: POST text continues below the banner (row 5)")
check(m.cell(20, 40)[1] == 0x17 and m.cell(1, 2)[1] == 0x1F, "splash: blue screen, bright title")
check(m.cursor()[0] > 5, "splash: cursor below the banner")

# ---------------------------------------------------------------- coloured messages
r, c = row_of(m, "FLEX DISK")
check(r is not None and m.cell(r, c - 1) == bytes([0x10, 0x1B]), "colour: '_' list marker drawn as a cyan bullet")
check(m.cell(r, c)[1] == 0x17, "colour: heading text in normal grey")
r, c = row_of(m, "Keyboard Error or Keyboard Missing")
check(r is not None and m.cell(r, c)[1] == 0x1C, "colour: error message in red")
r, c = row_of(m, "Disk controller failure")
check(r is not None and m.cell(r, c)[1] == 0x1C, "colour: 'failure' message in red")
r, c = row_of(m, "** Battery Power Lost")
check(r is not None and m.cell(r, c)[1] == 0x1E, "colour: '**' warning in yellow")
mi = post(IMPROVED, messages=("heading", "interrupts", "kbd_error"))
r, c = row_of(mi, "INTERRUPT CONTROLLERS")
check(r is not None and mi.cell(r, c)[1] == 0x17, "colour: 'INTERRUPT CONTROLLERS' (a test name with RR) is not red")
r, c = row_of(mi, "Keyboard Error or Keyboard Missing")
check(r is not None and mi.cell(r, c)[1] == 0x1C, "colour: ...while 'Error' still is")

# ---------------------------------------------------------------- switched off = original
o = post(ORIGINAL)
off = post(IMPROVED, flag=0xA5)
check(off.read(0xB8000, 4000) == o.read(0xB8000, 4000), "switched off: POST screen identical to the original BIOS")
check(off.text() == o.text(), "switched off: identical text output")

# ---------------------------------------------------------------- monochrome
mm = post(IMPROVED, mode=7)
ML = mm.screen_text().splitlines()
attrs = {mm.cell(r, c)[1] for r in range(25) for c in range(80)}
check("NCR System 3230" in ML[1] and attrs <= {0x07, 0x0F}, "monochrome: banner shown, only normal/bright attributes")
r, c = row_of(mm, "FLEX DISK")
check(r is not None and mm.cell(r, c - 1)[0] == ord("_"), "monochrome: messages printed unchanged (no colour scheme)")

# ---------------------------------------------------------------- Setup
mo, mi = setup(ORIGINAL, []), setup(IMPROVED, [])
LO, LI = mo.screen_text().splitlines(), mi.screen_text().splitlines()
check("Enhanced Edition %s by StevenC & Claude" % ED_VERSION in LI[0]
      and LI[0].startswith("   Setup, Version 2.01.00 (3230)"),
      "Setup: credits on the title line")
check(LO[1:] == LI[1:], "Setup: main screen otherwise unchanged")

fo, fi = setup(ORIGINAL, [0x3C00]), setup(IMPROVED, [0x3C00])
FO, FI = fo.screen_text().splitlines(), fi.screen_text().splitlines()
check(FI[14].rstrip("║ ").endswith("Fancy Boot Screen:         Yes"), "Setup F2: 'Fancy Boot Screen: Yes' beside Boot from Flex Disk")
check("F3  Fancy boot screen on/off" in FI[21], "Setup F2: F3 help line")
check(all(FO[r] == FI[r] for r in range(25) if r not in (14, 21)), "Setup F2: every other line unchanged")
check(fi.cell(14, 39)[1] == fi.cell(14, 3)[1] and fi.cell(14, 66)[1] == fi.cell(4, 67)[1],
      "Setup F2: new label and value use Setup's own colours")

t1 = setup(IMPROVED, [0x3C00, 0x3D00])
check(t1.cmos[0x48] == 0xA5 and "Fancy Boot Screen:          No" in t1.screen_text().splitlines()[14],
      "Setup F2: F3 switches it off (CMOS 48h = A5h)")
t2 = setup(IMPROVED, [0x3C00, 0x3D00, 0x3D00])
check(t2.cmos[0x48] == 0x00 and "Fancy Boot Screen:         Yes" in t2.screen_text().splitlines()[14],
      "Setup F2: F3 again switches it back on")
t3 = setup(IMPROVED, [0x3C00], flag=0xA5)
check("Fancy Boot Screen:          No" in t3.screen_text().splitlines()[14], "Setup F2: shows No when CMOS 48h = A5h")
t4 = setup(IMPROVED, [0x3C00, 0x2D78])
check(chr(7) in t4.text() and t4.cmos[0x48] == 0x00, "Setup F2: other keys still beep and change nothing")
check(t1.cursor() == setup(IMPROVED, [0x3C00]).cursor(), "Setup F2: cursor restored after F3")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
