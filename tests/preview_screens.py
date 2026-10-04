"""Render what the improved BIOS shows, by running its real code in the emulator.

    python tests/preview_screens.py [IMAGE.BIN] [OUT.html]

Writes an HTML page (default build/preview.html) with these screens:
  1. POST: splash + diagnostics lines + coloured messages + error countdown
  2. the same with the fancy screen switched off (CMOS 48h = A5h)
  3. Setup main screen
  4. Setup F2 screen with the new option
  5. Setup F2 screen after pressing F3
Each screen also prints as text so the run can be checked in a terminal.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from emu import Machine, StopEmu, cmos_checksum  # noqa: E402

IMAGE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "NCR3230-203-improved.BIN")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "build", "preview.html")

# POST message addresses (id byte before the text) in the F000 segment.
MSG = {"keyboard": 0x5349, "kbd_error": 0x53C6, "flex": 0x5408, "memory": 0x533A,
       "cache": 0x5672, "battery": 0x5513, "disk_fail": 0x9034}


def base_machine(flag_off=False, mode=3):
    m = Machine(IMAGE)
    m.install_rom_vectors()
    m.video_init(mode)
    m.cmos[0x10], m.cmos[0x14], m.cmos[0x15], m.cmos[0x16] = 0x40, 0x41, 0x80, 0x02
    m.cmos[0x44], m.cmos[0x47] = 0xE5, 0x4E
    m.cmos[0x48] = 0xA5 if flag_off else 0x00
    cmos_checksum(m.cmos)
    s = sum(m.cmos[0x44:0x48])
    m.cmos[0x7E], m.cmos[0x7F] = s >> 8, s & 0xFF
    return m


def countdown_poll_address(m):
    """Address of 'mov ah,1 / int 16h' inside the countdown routine (F000:A140..)."""
    blob = m.read(0xFA140, 0x100)
    i = blob.find(bytes([0xB4, 0x01, 0xCD, 0x16]))
    return 0xFA140 + i if i >= 0 else None


def post_screen(flag_off=False, mode=3, prompt=True):
    m = base_machine(flag_off, mode)
    # POST from "clear the screen" through the splash and the first two lines.
    m.run_until(0xF000, 0x328D, 0xF000, 0x32B9, ds=0x40, max_insns=20_000_000)
    for key in ("keyboard", "kbd_error", "flex", "cache", "battery", "disk_fail"):
        m.near_call(0xF000, 0x4D06, si=MSG[key], max_insns=2_000_000)
    if prompt:
        poll = countdown_poll_address(m)
        if poll:
            m.tick_at(poll)
        m.write(0x46C, b"\0\0")
        try:
            m.run_until(0xF000, 0x4775, 0xF000, 0x47AF, ax=0x02, ds=0x40, max_insns=50_000_000)
        except StopEmu as e:
            print("prompt:", e)
    return m


def setup_screen(keys):
    m = base_machine()
    m.keys = list(keys)
    try:
        m.far_call(0xFA40, 0x0003, max_insns=50_000_000, ds=0x40)
    except StopEmu:
        pass
    return m


def main():
    shots = [
        ("POST with the fancy screen (an error countdown at the bottom)", post_screen()),
        ("POST with the fancy screen switched off in Setup", post_screen(flag_off=True)),
        ("Setup: main screen", setup_screen([])),
        ("Setup: F2 screen with the new option", setup_screen([0x3C00])),
        ("Setup: F2 screen after pressing F3", setup_screen([0x3C00, 0x3D00])),
    ]
    html = ['<!doctype html><meta charset="utf-8"><title>NCR 3230 BIOS preview</title>',
            '<style>body{background:#222;color:#ddd;font:14px system-ui;margin:16px}'
            'pre.vga{font:16px/1 "Cascadia Mono",Consolas,monospace;display:inline-block;'
            'background:#000;padding:4px;margin:0 0 24px}h2{font-size:15px}</style>']
    for title, m in shots:
        print("=" * 20, title)
        print(m.screen_text())
        html.append("<h2>%s</h2>%s" % (title, m.screen_html(title)))
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(html))
    print("wrote", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
