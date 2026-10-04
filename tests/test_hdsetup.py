"""Tests for the Tools "Hard disk setup" page (tools_rom).

    python tests/test_hdsetup.py

Runs the page in the emulator with simulated IDE drives and typed keys, and
checks what it shows and the CMOS bytes it saves: drive types (12h, 19h/1Ah),
the type-1 table USERHDD.EXE used to write (72h-7Ch) and the checksum.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tools_harness import ENTER, ESC, AtaDisk, Atapi, IdeChannel, StopEmu, key, machine, run_tools  # noqa: E402

if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(HERE, "..", "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []
BS = 0x0E08


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def typed(s):
    return [ENTER if c == "\r" else key(c) for c in s]


def disk(cyl=1024, heads=16, spt=63, model="QUANTUM FIREBALL 540A"):
    return AtaDisk(cyl, heads, spt, model)


def setup(master=None, slave=None, ctype=0x00, prep=None):
    m = machine(master=None)
    m.ide = IdeChannel(m, master, slave)
    m.cmos[0x12] = ctype
    if prep:
        prep(m)
    return m


def page(m, keys):
    """Open item 7 and press the keys; stops when the next key is awaited."""
    return run_tools(m, typed("7") + list(keys))


def std_ok(c):
    return (c[0x2E] << 8 | c[0x2F]) == sum(c[0x10:0x2E])


def user_ok(c):
    s = sum(c[0x72:0x7C]) & 0xFFFF
    return s != 0 and (s & 0xFF) == c[0x7C]        # the rule POST (F000:3C58) and Setup use


def user_geo(c):
    return struct.unpack_from("<H", c, 0x72)[0], c[0x74], c[0x7B]


# ---------------------------------------------------------------- what the page shows
m = setup(disk(1047, 16, 63), Atapi(model="TOSHIBA CD-ROM XM-5302TA"))
page(m, [])
t = m.screen_text()
check("Hard disk setup" in t and "QUANTUM FIREBALL 540A" in t and "1047/16/63" in t
      and "TOSHIBA CD-ROM XM-5302TA" in t, "page: shows the IDE devices and the disk's own geometry")
check("Hard disk C:          Not installed" in t and "Hard disk D:          Not installed" in t and "not set" in t,
      "page: shows the CMOS settings (none, user type not set)")
check("No CMOS battery" not in t, "page: no warning with a good battery")
m = setup(disk(), prep=lambda m: m.cmos.__setitem__(0x0D, 0x00))
page(m, [])
check("No CMOS battery" in m.screen_text(), "page: warns when the CMOS battery is flat")
m = setup(disk())
run_tools(m, [])
check("7  Hard disk setup" in m.screen_text() and "9  Continue booting" in m.screen_text(), "menu: item 7, 9 items")

# ---------------------------------------------------------------- Automatic
m = setup(disk())
page(m, typed("cs"))
check(m.cmos[0x12] == 0x20 and std_ok(m.cmos) and "Saved." in m.screen_text(),
      "C -> Automatic, saved: CMOS 12h = 20h, checksum valid")
m = setup(disk())
page(m, typed("cds"))
check(m.cmos[0x12] == 0x23 and std_ok(m.cmos), "C and D Automatic: 12h = 23h (D: Automatic is 3, as Setup stores it)")
m = setup(disk(), ctype=0x23)
page(m, [])
check(m.screen_text().count("Automatic  (detected at every boot)") == 2, "page: shows Automatic for both drives")
m = setup(disk())
page(m, typed("c") + [ESC])
check(m.cmos[0x12] == 0x00, "Esc leaves without saving")

# ---------------------------------------------------------------- user type (what USERHDD.EXE did)
m = setup(disk())
page(m, typed("dds"))
check(m.cmos[0x12] == 0x00 and "enter its geometry first" in m.screen_text(),
      "user type without a geometry is refused")
m = setup(disk())
page(m, typed("u1024\r16\r63\r") + typed("ccs"))
c = m.cmos
check(c[0x12] == 0x10 and user_geo(c) == (1024, 16, 63) and user_ok(c) and std_ok(c),
      "U 1024/16/63, C -> user type: 12h = 10h, table 72h-7Bh, check byte 7Ch valid")
check(c[0x75:0x79] == bytes([0xFF, 0xFF, 0, 8]) and struct.unpack_from("<H", c, 0x79)[0] == 1024,
      "user table: no precompensation, control byte 08h (>8 heads), landing zone = cylinders")
check("1024/16/63" in m.screen_text() and "504 MB" in m.screen_text(), "user type shown with its size")
m = setup(disk())
page(m, typed("u2000\r") + [BS] * 4 + typed("980\r10\r17\r") + typed("ccs"))
check(user_geo(m.cmos) == (980, 10, 17) and user_ok(m.cmos), "out-of-range input is ignored; backspace corrects it")
m = setup(disk())
page(m, typed("u12") + [ESC])
check("not set" in m.screen_text() and m.cmos[0x12] == 0, "Esc during input changes nothing")
m = setup(disk(1047, 16, 63))
page(m, typed("mccs"))
check(user_geo(m.cmos) == (1024, 16, 63) and m.cmos[0x12] == 0x10, "M copies the master's geometry (1047 -> 1024 cyl)")


def old_user(m):
    m.cmos[0x72:0x7C] = struct.pack("<HBHBBHB", 615, 4, 0xFFFF, 0, 0, 615, 17)
    m.cmos[0x7C] = sum(m.cmos[0x72:0x7C]) & 0xFF


m = setup(disk(), ctype=0x01, prep=old_user)
page(m, [])
t = m.screen_text()
check("615/4/17" in t and "User type (type 1)" in t, "an existing USERHDD table is read and shown")

# ---------------------------------------------------------------- fixed and extended types
m = setup(disk(), ctype=0xF0, prep=lambda m: m.cmos.__setitem__(0x19, 47))
page(m, [])
check("Type 47" in m.screen_text(), "an extended type (12h = F0h, 19h = 47) is shown")
m = setup(disk(), ctype=0xF0, prep=lambda m: m.cmos.__setitem__(0x19, 47))
page(m, typed("cccc") + typed("s"))
check(m.cmos[0x12] == 0xF0 and m.cmos[0x19] == 47 and std_ok(m.cmos),
      "C cycles none, Automatic, user, back to type 47, saved as 12h = F0h / 19h = 47")
m = setup(disk(), ctype=0x40)
page(m, typed("c"))
check("Not installed" in m.screen_text().split("Hard disk D:")[0], "type 4 -> C changes to Not installed")

# ---------------------------------------------------------------- restart after saving
m = setup(disk())
m.keys = typed("7cs") + [ENTER]
try:
    r = m.run_to_any(0xE800, 0x000A, {(0xFFFF, 0x0000): "reset"}, max_insns=200_000_000, ax=0)
except StopEmu as e:
    r = str(e)
check(r == "reset" and m.mem_word(0x472) == 0x1234 and m.cmos[0x12] == 0x20,
      "Enter after saving restarts (warm, 40:72 = 1234h)")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
