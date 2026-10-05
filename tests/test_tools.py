"""Tests for tools_rom: the Tools extension at E800 and its BIOS hooks.

    python tests/test_tools.py

Runs the real ROM code in the emulator: the Tools pages, the memory test
(with an injected fault), the end-of-POST summary and chime, the measured
"PROCESSOR SPEED", the F8/F10 keys, the one-shot boot device, and the
fall-back to stock behaviour when the extension is missing or damaged.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tools_harness import (ENTER, ESC, F1, F8, F10, G_BASE, StopEmu,  # noqa: E402
                           esc_after_polls, key, machine, run_tools)
from unicorn import UC_HOOK_MEM_READ  # noqa: E402

if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(HERE, "..", "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []
POST_STACK = dict(ss=0x0000, sp=0x0400)            # the stack POST uses at its end


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def text(m):
    return m.screen_text()


def no_extension(m):
    m.write(0xE8000, b"\xFF" * 0x8000)              # board does not map E8000


def damaged_extension(m):
    b = m.read(0xE8100, 1)[0]
    m.write(0xE8100, bytes([b ^ 0x40]))             # one flipped bit: checksum fails


# ---------------------------------------------------------------- pages
m = machine()
run_tools(m, [])
t = text(m)
check("NCR System 3230 · Tools" in t and "Enhanced by StevenC & Claude" in t, "menu: title bar with credits")
check(all(s in t for s in ("1  System information", "4  Memory test", "6  Floppy drive test", "7  Hard disk setup",
                         "9  Continue booting")),
      "menu: all items listed")
check(m.cell(6, 21)[1] == 0x3F, "menu: first item highlighted")
m = machine()
run_tools(m, [0x5000, 0x5000])                      # down, down
check(m.cell(8, 21)[1] == 0x3F and m.cell(6, 21)[1] != 0x3F, "menu: arrow keys move the highlight")

m = machine()
run_tools(m, [key("1")])
t = text(m)
check("Processor" in t and "Maths coprocessor     present" in t, "system info: processor and coprocessor")
check("Level 2 cache         256 KB, on" in t, "system info: L2 cache size from the chipset")
check("Extended memory       3072 KB" in t and "(total 4 MB)" in t, "system info: memory sizes")
check("COM1 3F8  COM2 2F8  LPT1 378" in t, "system info: serial and parallel ports")
check("2026-10-04 13:45:10" in t and "battery OK" in t, "system info: real-time clock and battery")
check("checksum OK" in t, "system info: extension checksum reported")

m = machine(master="disk", slave="cdrom")
run_tools(m, [key("2")])
t = text(m)
check("QUANTUM FIREBALL 540A  (disk, 504 MB)" in t, "drives: IDE disk model and size read from the drive")
check("TOSHIBA CD-ROM XM-5302TA  (CD-ROM / ATAPI)" in t, "drives: CD-ROM model read with IDENTIFY PACKET")
check("1.44 MB 3.5\"" in t, "drives: floppy type from CMOS")
check(m.mem_byte(0x48E) & 0x80 == 0, "drives: no stale IRQ 14 flag left for INT 13h")
m = machine(master=None)
run_tools(m, [key("2")])
check("IDE primary master    none" in text(m), "drives: empty IDE bus shows none")

m = machine()
run_tools(m, [key("3")])
t = text(m)
check("C8000    16 KB    PicoMEM BIOS v1.2 (test ROM)" in t, "memory map: option ROM found with its name")
check("E0000    32 KB    IBM VGA Compatible" in t, "memory map: onboard VGA BIOS")
check("100000   3072 KB   Extended RAM" in t, "memory map: extended RAM")

m = machine()
run_tools(m, [key("5")])
t = text(m)
check("Checksum 10h-2Dh      stored 010F, computed 010F  OK" in t, "CMOS: standard checksum decoded")
check("NCR checksum 44h-47h" in t and "Fancy boot (48h)      on" in t, "CMOS: NCR checksum and fancy flag")

# ---------------------------------------------------------------- memory test
m = machine(ext_mb=3)
esc_after_polls(m, 600)
run_tools(m, [key("4"), ENTER], max_insns=2_000_000_000)
t = text(m)
check("Stopped. 1 full pass(es), 0 error(s)" in t, "memory test: a clean full pass over 64 KB-640 KB and 1-4 MB")

BAD = 0x250004
m = machine(ext_mb=3)


def stuck(uc, access, address, size, value, user):
    if address <= BAD < address + size:
        uc.mem_write(BAD, bytes([uc.mem_read(BAD, 1)[0] & ~0x08]))


m.uc.hook_add(UC_HOOK_MEM_READ, stuck, begin=BAD - 3, end=BAD)
esc_after_polls(m, 300)
run_tools(m, [key("4"), ENTER], max_insns=2_000_000_000)
t = text(m)
check("00250004  AAAAAAAA  AAAAAAA2" in t, "memory test: stuck data bit found at the right address")
check(m.cell(13, 11)[1] == 0x1C, "memory test: error count shown in red")

BADC = 0x54320                                      # conventional memory fault too
m = machine(ext_mb=1)


def stuck2(uc, access, address, size, value, user):
    if address <= BADC < address + size:
        uc.mem_write(BADC, bytes([uc.mem_read(BADC, 1)[0] | 0x80]))


m.uc.hook_add(UC_HOOK_MEM_READ, stuck2, begin=BADC - 3, end=BADC)
esc_after_polls(m, 40)
run_tools(m, [key("4"), ENTER], max_insns=2_000_000_000)
check("00054320" in text(m), "memory test: conventional-memory fault found")

# ---------------------------------------------------------------- end of POST
m = machine()
m.log_ports = True
m.keys = [ENTER]
m.near_call(0xF000, G_BASE + 3, max_insns=200_000_000, **POST_STACK)
t = text(m)
check("System summary" in t and "TOSHIBA CD-ROM XM-5302TA" in t and "Floppy A:" in t,
      "summary: shown at the end of POST with drive names")
check(m.keys == [ENTER], "summary: a key ends it and stays queued for POST")
outs = [(p, v) for d, p, v in m.ports_log if d == "out"]
divs = [outs[i + 1][1] | (outs[i + 2][1] << 8) for i, (p, v) in enumerate(outs[:-2])
        if p == 0x43 and v == 0xB6]
check(divs[:4] == [1140, 905, 761, 570], "summary: start-up chime C-E-G-C on the speaker")
m = machine(flag=0xA5)
m.log_ports = True
m.near_call(0xF000, G_BASE + 3, max_insns=200_000_000, **POST_STACK)
outs = [(p, v) for d, p, v in m.ports_log if d == "out"]
tones = [i for i, (p, v) in enumerate(outs) if p == 0x43 and v == 0xB6]
check(len(tones) == 1 and "System summary" not in text(m), "summary: fancy screen off -> one plain beep, no summary")

# ---------------------------------------------------------------- processor speed line
m = machine()
m.cmos[0x43] = 0x21
m.run_until(0xF000, 0x3881, 0xF000, 0x3894, max_insns=50_000_000, **POST_STACK)
check("MHz" in m.text() and m.text().strip() != "33 MHz", "speed line: measured value printed (%r)" % m.text().strip())
m = machine()
no_extension(m)
m.cmos[0x43] = 33
m.run_until(0xF000, 0x3881, 0xF000, 0x3894, max_insns=50_000_000, **POST_STACK)
check(m.text().strip() == "33 MHz", "speed line: without the extension, CMOS 43h as before (%r)" % m.text().strip())

# ---------------------------------------------------------------- F1 / F8 / F10 at the end of POST
STOPS = {(0xF000, 0x47D2): "setup", (0xF000, 0x47FE): "after-tools", (0xF000, 0x4806): "other"}


def post_keys(keys, prep=None):
    m = machine()
    if prep:
        prep(m)
    m.keys = list(keys)
    try:
        return m.run_to_any(0xF000, 0x47C3, STOPS, max_insns=200_000_000, ds=0x40, **POST_STACK), m
    except StopEmu as e:
        return str(e), m


r, m = post_keys([F1])
check(r == "setup", "keys: F1 still opens Setup")
r, m = post_keys([0x2004])
check(r == "other", "keys: Ctrl-D still reaches its handler")
r, m = post_keys([F10, ESC])
check(r == "after-tools" and m.mem_word(0x5000) == 0xB800, "keys: F10 runs Tools, then POST continues")
r, m = post_keys([F8, key("2")])
check(r == "after-tools" and m.mem_word(0x4F0) == 0x424E and m.mem_byte(0x4F2) == 0x80,
      "keys: F8 boot menu stores a one-shot choice of C:")
r, m = post_keys([F8, ESC])
check(r == "after-tools" and m.mem_word(0x4F0) == 0, "keys: F8 then Esc leaves the normal boot order")
r, m = post_keys([F10], prep=no_extension)
check(r == "other", "keys: without the extension F10 is ignored as before")
r, m = post_keys([F10], prep=damaged_extension)
check(r == "other", "keys: a damaged extension (bad checksum) is never entered")

# ---------------------------------------------------------------- one-shot boot device
BOOTSTOPS = {(0x0000, 0x7C00): "bootsector", (0xF000, 0xE066): "normal"}


def boot(marker, drive, with_disk=True, prep=None):
    m = machine(master="disk" if with_disk else None)
    m.cmos[0x12] = 0x20
    m.write(0x4AE, struct.pack("<H", 1))
    m.set_vector(0x13, 0xF000, 0xEC59)      # as in real POST: INT 13h is still the diskette handler,
    m.near_call(0xF000, 0x9062, max_insns=400_000_000, ds=0x40, es=0, **POST_STACK)   # which this moves to INT 40h
    if with_disk:
        sector = bytearray(512)
        sector[0:3] = b"\xEB\xFE\x90"
        sector[510:512] = b"\x55\xAA"
        d = m.ide.dev[0]
        d.sectors[0] = bytes(sector)
    if marker:
        m.write(0x4F0, struct.pack("<HB", 0x424E, drive))
    if prep:
        prep(m)
    try:
        r = m.run_to_any(0xF000, 0xE6F2, BOOTSTOPS, max_insns=400_000_000, ss=0, sp=0x7B00)
    except StopEmu as e:
        r = str(e)
    return r, m


r, m = boot(True, 0x80)
check(r == "bootsector" and m.reg("dx") & 0xFF == 0x80 and m.read(0x7DFE, 2) == b"\x55\xAA",
      "boot menu: INT 19h boots C: once from the chosen drive (DL=80h)")
check(m.mem_word(0x4F0) == 0, "boot menu: the choice is cleared after use")
r, m = boot(False, 0)
check(r == "normal", "boot menu: no choice -> normal INT 19h boot order")
r, m = boot(True, 0x80, with_disk=False)
check(r == "normal" and "did not boot" in m.text(), "boot menu: failing device -> message, then the normal order")
r, m = boot(True, 0x80, prep=no_extension)
check(r == "normal", "boot menu: without the extension INT 19h is unchanged")

# ---------------------------------------------------------------- summary timing
def ticking(m):
    """Each INT 16h poll advances the BIOS tick count by one (18.2 per second)."""
    orig = m._int16
    state = {"ticks": 0}

    def stub():
        if m.reg("ax") >> 8 == 1 and not m.keys:
            m.write(0x46C, struct.pack("<H", (m.mem_word(0x46C) + 1) & 0xFFFF))
            state["ticks"] += 1
        orig()
    m.stubs[0x16] = stub
    return state


m = machine()
st = ticking(m)
m.near_call(0xF000, G_BASE + 3, max_insns=400_000_000, **POST_STACK)
check(145 <= st["ticks"] <= 147, "summary: shown for 8 s with no key (%d ticks)" % st["ticks"])
m = machine()
m.keys = [0x3920, ENTER]
m.near_call(0xF000, G_BASE + 3, max_insns=200_000_000, **POST_STACK)
check("held" in text(m) and m.keys == [], "summary: Space holds it; the next key boots and is taken")
m = machine()
m.keys = [0x3920, F10]
m.near_call(0xF000, G_BASE + 3, max_insns=200_000_000, **POST_STACK)
check(m.keys == [F10], "summary: after Space, F10 is left for POST (opens Tools)")

# ---------------------------------------------------------------- option ROM boot (PicoMEM)
ROMBOOT = (0xC800, 0x0100)                       # the fake option ROM's INT 19h
B19STOPS = {(0x0000, 0x7C00): "bootsector", (0xF000, 0xE066): "bios", ROMBOOT: "rom"}


def hooked(m):
    m.write(0xC8100, b"\xEB\xFE")
    m.set_vector(0x19, *ROMBOOT)                 # as the PicoMEM ROM does at its init


def order_c_only(m):
    m.cmos[0x4A:0x4E] = bytes([ord("O"), 0x20, 0x00, ~(ord("O") + 0x20) & 0xFF])


def postend(m):
    m.near_call(0xF000, G_BASE + 3, max_insns=200_000_000, **POST_STACK)


def boot19(m):
    try:
        return m.run_to_any(0xF000, 0xE6F2, B19STOPS, max_insns=400_000_000, ss=0, sp=0x7B00)
    except StopEmu as e:
        return str(e)


m = machine(flag=0xA5)
hooked(m)
postend(m)
saved = [(a, p) for a, _, _, p in m.rom_writes if 0xFEF06 <= a < 0xFEF0B]
check(m.vector(0x19) == (0xF000, 0xE6F2) and m.read(0xFEF06, 5) == struct.pack("<HHB", 0x0100, 0xC800, 1)
      and saved and all(p == 0 for a, p in saved), "option ROM: INT 19h taken back at the end of POST, ROM's kept")
check(boot19(m) == "rom" and m.mem_byte(0x4F3) == ord("P"), "option ROM: by default its own boot runs first")
check(boot19(m) == "bios", "option ROM: when it falls back to INT 19h, the BIOS boot order follows")

m = machine(flag=0xA5)
hooked(m)
postend(m)
order_c_only(m)
check(boot19(m) == "bios", "option ROM: a saved boot order without it (C: only) skips the ROM's boot")

m = machine(flag=0xA5, master="disk")
m.cmos[0x12] = 0x20
m.write(0x4AE, struct.pack("<H", 1))
m.set_vector(0x13, 0xF000, 0xEC59)
m.near_call(0xF000, 0x9062, max_insns=400_000_000, ds=0x40, es=0, **POST_STACK)
s0 = bytearray(512)
s0[0:2], s0[510:512] = b"\xEB\xFE", b"\x55\xAA"
m.ide.dev[0].sectors[0] = bytes(s0)
hooked(m)
postend(m)
m.write(0x4F0, struct.pack("<HB", 0x424E, 0x80))
check(boot19(m) == "bootsector", "option ROM: a boot menu choice (C:) wins over the ROM's boot")

m = machine(flag=0xA5)
hooked(m)
postend(m)
run_tools(m, [], page=1)
t = text(m)
check("4  Option ROM boot (PicoMEM BIOS v1.2 (test ROM))" in t and "BIOS default (option ROM boot first" in t,
      "boot menu: lists the option ROM's boot by name, and the normal order")
r = run_tools(m, [key("4")], page=1)
img = open(os.path.join(HERE, "..", "build", "NCR3230-203-improved.BIN"), "rb").read()
check(r == "returned" and m.mem_byte(0x4F2) == 0xFE and m.read(0xE8000, 0x8000) == img[0x8000:0x10000],
      "boot menu: 4 chooses the option ROM's boot once (Tools returns, ROM untouched)")
order_c_only(m)
check(boot19(m) == "rom", "option ROM: chosen with 4, it boots even when the saved order leaves it out")

m = machine(flag=0xA5)
postend(m)
check(m.vector(0x19) == (0xF000, 0xE6F2) and m.mem_byte(0xFEF0A) == 0 and boot19(m) == "bios",
      "no option ROM hook: INT 19h as before")
run_tools(m, [], page=1)
check("no option ROM hooked the boot" in text(m), "boot menu: says when there is no option ROM boot")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
