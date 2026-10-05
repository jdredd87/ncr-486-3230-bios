"""Tests for the Tools chipset settings (UMC 82C480 timing) and their fail-safe.

    python tests/test_chipset.py

The settings page (Tools 9), what it saves in CMOS 4Eh-52h, how the end of
POST writes the saved values into the chipset registers, and the fail-safe:
a boot that never reaches INT 19h or Tools makes the next boot skip them,
and a held Shift key skips them once.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tools_harness import ESC, G_BASE, StopEmu, key, machine, run_tools  # noqa: E402

if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(HERE, "..", "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []
POST_STACK = dict(ss=0x0000, sp=0x0400)
UP, DOWN, LEFT, RIGHT = 0x4800, 0x5000, 0x4B00, 0x4D00
NCR = {0x81: 0x31, 0x82: 0x54, 0x91: 0x0A, 0x97: 0xB0}       # POST's table values


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def setup(flag=0xA5):
    m = machine(flag=flag)
    for r, v in NCR.items():
        m.chipset[r] = v
    return m


def saved(m):
    c = m.cmos
    if c[0x4E] != ord("C") or c[0x51] != ~(c[0x4E] + c[0x4F] + c[0x50]) & 0xFF:
        return None
    return c[0x4F] & 7, (c[0x4F] >> 4) & 3, c[0x50]


def save(m, isa, rec, r91):
    c = m.cmos
    c[0x4E], c[0x4F], c[0x50] = ord("C"), isa | rec << 4, r91
    c[0x51] = ~(c[0x4E] + c[0x4F] + c[0x50]) & 0xFF


def postend(m):
    m.near_call(0xF000, G_BASE + 3, max_insns=200_000_000, **POST_STACK)


def rows(m):
    return [line for line in m.screen_text().splitlines()[7:13]]


# ---------------------------------------------------------------- the page
m = setup()
run_tools(m, [key("9")])
t = m.screen_text()
r = rows(m)
check("Chipset settings" in t and "ISA bus clock" in r[0] and r[0].count("÷ 5  (6.7 MHz)") == 2
      and r[2].count("1 WS") == 2 and r[4].count("3-1-1-1") == 2,
      "page: NCR's values (bus ÷ 5, DRAM 1 WS, L2 3-1-1-1), setting and chip agree")
check("This boot: NCR defaults" in t, "page: says NCR's defaults are in use")
m = setup()
run_tools(m, [key("9"), RIGHT, DOWN, DOWN, RIGHT, DOWN, DOWN, RIGHT, RIGHT, key("s")])
check(saved(m) == (2, 0, 0x8E) and m.cmos[0x52] == 0 and "Saved." in m.screen_text(),
      "page: bus ÷ 4, DRAM read 0 WS, L2 burst 2-1-1-1 saved to CMOS 4Eh-51h (%r)" % (saved(m),))
m = setup()
run_tools(m, [key("9"), DOWN, DOWN, DOWN, RIGHT, key("s")])
check(saved(m)[2] & 3 == 3, "page: DRAM write 1 WS -> 0 WS")
m = setup()
run_tools(m, [key("9"), DOWN, DOWN, DOWN, RIGHT, RIGHT, RIGHT, key("s")])
check(saved(m)[2] & 3 == 2, "page: DRAM write steps 1, 0, 3 WS and back to 1 WS (reserved value skipped)")
m = setup()
run_tools(m, [key("9"), LEFT, key("s")])
check(saved(m)[0] == 0, "page: Left goes the other way (bus ÷ 6)")
m = setup()
save(m, 2, 1, 0x8E)
run_tools(m, [key("9"), key("d")])
check(saved(m) is None and "NCR's own values" in m.screen_text(), "page: D goes back to NCR's values")
m = setup()
run_tools(m, [key("9"), RIGHT, ESC])
check(saved(m) is None, "page: Esc leaves without saving")
m = setup()
run_tools(m, [key("9"), key("r")])
check("Chipset registers (index 22h, data 24h)" in m.screen_text() and "91h  0Ah  0000 1010  0Ah  DRAM,L2 WS"
      in m.screen_text(), "page: R shows the register view, with the bits named")

# ---------------------------------------------------------------- applied at the end of POST
m = setup()
m.chipset[0x81] = 0x31 | 0x08                               # other bits must survive
save(m, 2, 1, 0x8E)
postend(m)
check(m.chipset[0x81] == 0x3A and m.chipset[0x82] == 0x55 and m.chipset[0x91] == 0x8E,
      "end of POST: saved fields written, other bits kept (81h=%02X 82h=%02X 91h=%02X)" % (
          m.chipset[0x81], m.chipset[0x82], m.chipset[0x91]))
check(m.cmos[0x52] == ord("P"), "end of POST: fail-safe flag set while the boot is unproven")
run_tools(m, [key("9")])
check("custom settings in use" in m.screen_text() and m.cmos[0x52] == 0,
      "Tools: shows the custom settings; reaching Tools clears the fail-safe flag")
m = setup()
save(m, 2, 1, 0x8E)
postend(m)
try:
    m.run_to_any(0xF000, 0xE6F2, {(0xF000, 0xE066): "bios"}, max_insns=200_000_000, ss=0, sp=0x7B00)
except StopEmu:
    pass
check(m.cmos[0x52] == 0, "INT 19h: reaching the boot clears the fail-safe flag")
m = setup(flag=0x00)
save(m, 2, 1, 0x8E)
m.keys = [0x1C0D]
postend(m)
check("Chipset timing        custom settings in use" in m.screen_text(), "summary: shows the chipset timing state")

# ---------------------------------------------------------------- the fail-safe
m = setup()
save(m, 2, 1, 0x8E)
m.cmos[0x52] = ord("P")                                   # the last boot never got to INT 19h
postend(m)
check(all(m.chipset[r] == v for r, v in NCR.items()) and m.cmos[0x52] == ord("F"),
      "a boot that did not finish: the next one skips the settings and marks them failed")
run_tools(m, [key("9")])
check("skipped: a boot with them did not finish" in m.screen_text(), "Tools: says why the settings were skipped")
postend(m)
check(m.chipset[0x91] == 0x0A, "failed settings stay off on later boots")
run_tools(m, [key("9"), key("s")])
check(m.cmos[0x52] == 0, "saving again in Tools clears the failure")
postend(m)
check(m.chipset[0x91] == 0x8E, "...and the next boot applies them again")
m = setup()
save(m, 2, 1, 0x8E)
m.write(0x417, bytes([0x01]))                              # right Shift held
postend(m)
check(m.chipset[0x91] == 0x0A and m.cmos[0x52] != ord("P"), "Shift held at the end of POST: skipped this once")
run_tools(m, [key("9")])
check("skipped this boot (Shift held)" in m.screen_text(), "Tools: says Shift skipped them")
m = setup()
m.cmos[0x52] = ord("P")
postend(m)
check(all(m.chipset[r] == v for r, v in NCR.items()) and m.cmos[0x52] == 0,
      "no saved settings: the chipset is left as POST set it, any stale flag cleared")
m = setup()
save(m, 2, 1, 0x8E)
m.cmos[0x50] ^= 0x01                                      # damaged: the check byte fails
postend(m)
check(m.chipset[0x91] == 0x0A, "damaged saved settings are ignored")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
