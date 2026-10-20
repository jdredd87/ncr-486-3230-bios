"""Tests for the Tools chipset settings (UMC 82C480 timing) and their fail-safe.

    python tests/test_chipset.py

The settings page (Tools 9), what it saves in CMOS 4Eh-52h, how the end of
POST writes the saved values into the chipset registers, and the fail-safe:
a boot that never reaches INT 19h or Tools makes the next boot skip them,
and a held Shift key skips them once. Also the Cirrus Logic video memory
clock on the same page (CMOS 60h, SR1F), NCR's POST clearing CMOS 53h (why
the clock is not kept there any more), the video memory speed test (V), the
real VGA BIOS's own handling of that clock, and the Video line naming the
chip and its memory.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tools_harness import ESC, G_BASE, StopEmu, key, machine, run_tools  # noqa: E402
from emu import CirrusVga  # noqa: E402

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

m = setup()                                                 # Ctrl-Alt-Del: POST skipped its table
m.chipset[0x81], m.chipset[0x82], m.chipset[0x91] = 0x32, 0x57, 0x0F
postend(m)
check(m.chipset[0x81] == 0x31 and m.chipset[0x82] == 0x54 and m.chipset[0x91] == 0x0A,
      "no saved settings: values left from the boot before go back to POST's table")
m = setup()
save(m, 2, 1, 0x8F)
m.cmos[0x52] = ord("P")                                     # that boot hung, then Ctrl-Alt-Del
m.chipset[0x81], m.chipset[0x82], m.chipset[0x91] = 0x32, 0x55, 0x8F
postend(m)
check(m.chipset[0x81] == 0x31 and m.chipset[0x91] == 0x0A and m.cmos[0x52] == ord("F"),
      "fail-safe after Ctrl-Alt-Del: the too-fast values are taken out of the chip")
m = setup()
run_tools(m, [key("9"), RIGHT, key("s")])
check("Saved. Restart" in m.screen_text(), "page: S reads the block back and says it is saved")
m = setup()
orig_out = m.port_out


def lossy(port, size, value):                               # a CMOS that loses writes to 50h
    if port == 0x71 and m.cmos_index & 0x7F == 0x50:
        return
    orig_out(port, size, value)


m.port_out = lossy
run_tools(m, [key("9"), RIGHT, key("s")])
t = m.screen_text()
check("NOT saved: CMOS 4Eh-51h/60h read back wrong" in t and "÷ 4" in t.splitlines()[7],
      "page: a save that does not read back is reported, the choice stays on screen")

# ---------------------------------------------------------------- video memory clock (Cirrus GD542x)
def cirrus(m, **kw):
    m.vga = CirrusVga(**kw)
    return m.vga


MC = 0x60                                                   # the video clock's CMOS byte


def mclk_saved(m):
    v = m.cmos[MC]
    return v & 0x0F if v >> 4 == (v & 0x0F) ^ 0x0F else None


m = setup()
v = cirrus(m)
run_tools(m, [key("9")])
r = m.screen_text().splitlines()[13]
check("Video memory clock" in r and "VGA BIOS's (50.1 MHz)" in r and "50.1 MHz" in r.split(")")[-1],
      "page: video memory clock row, the VGA BIOS's 50.1 MHz, read from the chip (%r)" % r.strip())
m = setup()
v = cirrus(m)
run_tools(m, [key("9")] + [DOWN] * 6 + [RIGHT, RIGHT, RIGHT, key("s")])
check(mclk_saved(m) == 3 and saved(m) is not None, "page: 57.3 MHz saved to CMOS 60h with the chipset block")
postend(m)
check(v.sr[0x1F] == 0x20 and m.cmos[0x52] == ord("P"), "end of POST: SR1F = 20h (57.3 MHz), under the fail-safe")
run_tools(m, [key("9")])
r = m.screen_text().splitlines()[13]
check("57.3 MHz" in r and r.count("57.3 MHz") == 2, "page: setting and chip both show 57.3 MHz")
m = setup()
v = cirrus(m, mclk=0x5C)                                    # bit 6 set: must survive
save(m, 0, 0, 0x0A)
m.cmos[MC] = 0x5 | (0x5 ^ 0xF) << 4
postend(m)
check(v.sr[0x1F] == 0x62, "end of POST: 60.9 MHz written, bits 7-6 kept (SR1F=%02X)" % v.sr[0x1F])
m = setup()
v = cirrus(m, unlocked=False)
save(m, 0, 0, 0x0A)
m.cmos[MC] = 0x2 | (0x2 ^ 0xF) << 4
postend(m)
check(v.sr[0x1F] == 0x1F and v.sr[0x06] == 0x0F, "locked extensions: unlocked to write SR1F, locked again")
m = setup()
v = cirrus(m)
save(m, 0, 0, 0x0A)
m.cmos[MC] = 0x22                                         # not a valid choice byte
postend(m)
check(v.sr[0x1F] == 0x1C and not [w for w in v.sr_writes if w[0] == 0x1F], "damaged CMOS 60h: the clock is left alone")
m = setup()
v = cirrus(m)
m.cmos[MC] = 0x3 | (0x3 ^ 0xF) << 4                       # without a chipset block: not used
postend(m)
check(v.sr[0x1F] == 0x1C, "CMOS 60h alone (no saved chipset block): not applied")
m = setup()
v = cirrus(m)
save(m, 0, 0, 0x0A)
m.cmos[MC] = 0x3 | (0x3 ^ 0xF) << 4
m.write(0x417, bytes([0x02]))
postend(m)
check(v.sr[0x1F] == 0x1C, "Shift held: the video clock is skipped too")
m = setup()
v = cirrus(m)
save(m, 0, 0, 0x0A)
m.cmos[MC] = 0x3 | (0x3 ^ 0xF) << 4
run_tools(m, [key("9"), key("d")])
check(m.cmos[MC] == 0 and saved(m) is None, "page: D clears the video clock with the rest")
m = setup()
run_tools(m, [key("9")])
check("no Cirrus chip" in m.screen_text().splitlines()[13], "no Cirrus chip: the row says so")
save(m, 0, 0, 0x0A)
m.cmos[MC] = 0x3 | (0x3 ^ 0xF) << 4
postend(m)
check(m.cmos[0x52] == ord("P"), "no Cirrus chip: the rest of the settings still apply")

for how, prep in (("no saved settings", lambda m: None),
                  ("Shift held", lambda m: (save(m, 0, 0, 0x0A), m.cmos.__setitem__(MC, 0x5 | 0xA0),
                                            m.write(0x417, bytes([0x02])))),
                  ("the last boot failed", lambda m: (save(m, 0, 0, 0x0A), m.cmos.__setitem__(MC, 0x5 | 0xA0),
                                                      m.cmos.__setitem__(0x52, ord("P"))))):
    m = setup()
    v = cirrus(m, mclk=0x62)                                # 60.9 MHz kept over Ctrl-Alt-Del, bit 6 set
    prep(m)
    postend(m)
    check(v.sr[0x1F] == 0x5C, "%s: a clock left from the boot before goes back to 50.1 MHz (SR1F=%02X)"
          % (how, v.sr[0x1F]))

m = setup()
v = cirrus(m)
m.stubs.pop(0x10)                                           # the real VGA BIOS's INT 10h
m.far_call(0xE000, 0x0003, max_insns=50_000_000)            # its start-up
starts = [w for w in v.sr_writes if w[0] == 0x1F]
v.sr[0x1F] = 0x20                                           # as the end of POST leaves it
for mode in (0x03, 0x13, 0x5F, 0x03):
    m.int_call(0x10, ax=mode, max_insns=50_000_000)
m.int_call(0x10, ax=0x4F02, bx=0x101, max_insns=50_000_000)
check(starts == [(0x1F, 0x1C)] and v.sr[0x1F] == 0x20,
      "VGA BIOS: sets 1Ch (50.1 MHz) once at start-up; mode sets and VESA modes keep a later value")
m = setup()
v = cirrus(m, mclk=0x22)
m.stubs.pop(0x10)
m.write(0x472, struct.pack("<H", 0x1234))                  # Ctrl-Alt-Del
m.far_call(0xE000, 0x0003, max_insns=50_000_000)
check(not [w for w in v.sr_writes if w[0] == 0x1F] and v.sr[0x1F] == 0x22,
      "VGA BIOS: on a warm boot it leaves the memory clock as it was")

m = setup()
v = cirrus(m)
run_tools(m, [key("9")] + [DOWN] * 6 + [RIGHT] * 5 + [key("s")])
m.cmos[0x53] = 0xA5
m.run_until(0xF000, 0x40EE, 0xF000, 0x4108, max_insns=5_000_000)    # NCR's POST, keyboard input port bit 5 low
check(m.cmos[0x53] == 0 and mclk_saved(m) == 5, "NCR's POST clears CMOS 53h (F000:40FE); the clock in 60h stays")

m = setup()
v = cirrus(m, mclk=0x20)
run_tools(m, [key("9"), key("v")], max_insns=400_000_000)
t = m.screen_text()
rows = t.splitlines()[12:18]
check("Video memory speed test" in t and len(rows) == 6 and all(r.count("KB/s") == 2 for r in rows),
      "speed test: write and read speed for each of the six clocks")
check("57.3 MHz" in rows[3] and "< before the test" in rows[3] and "< before" not in "".join(rows[:3] + rows[4:]),
      "speed test: the clock in use before the test is marked")
clk = [w[1] & 0x3F for w in v.sr_writes if w[0] == 0x1F]
check(clk == [0x1C, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x20] and v.sr[0x1F] == 0x20,
      "speed test: each clock in turn, then the clock as it was (%s)" % clk)
m = setup()
run_tools(m, [key("9"), key("v")])
check("No Cirrus video chip answers." in m.screen_text(), "speed test: no Cirrus chip, nothing measured")

# ---------------------------------------------------------------- the chip named
for cid, name, mem, mtxt in ((0x90, "CL-GD5426", 2, "1 MB"), (0x94, "CL-GD5424", 1, "512 KB"),
                             (0x8C, "CL-GD5422", 2, "1 MB"), (0x98, "CL-GD5428", 3, "2 MB")):
    m = setup()
    cirrus(m, chip_id=cid | 1, mem_code=mem)                # low bits: revision, ignored
    run_tools(m, [key("1")])
    check("Cirrus %s, %s, BIOS at" % (name, mtxt) in m.screen_text(),
          "System information: Video names the %s with %s" % (name, mtxt))
m = setup()
cirrus(m, chip_id=0xB8)
run_tools(m, [key("1")])
check("Cirrus CL-GD54xx, 1 MB" in m.screen_text(), "an unknown Cirrus ID: CL-GD54xx")
m = setup()
run_tools(m, [key("1")])
check("VGA colour, BIOS at" in m.screen_text(), "no Cirrus chip: Video line as before")
m = setup(flag=0x00)
cirrus(m)
m.keys = [0x1C0D]
postend(m)
check("Video                 Cirrus CL-GD5426, 1 MB, BIOS at" in m.screen_text(), "summary: names the video chip")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
