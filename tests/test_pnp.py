"""Tests for ISA Plug and Play configuration (tools_rom).

    python tests/test_pnp.py

Emulated ISA PnP cards (PnP ISA 1.0a: initiation key, serial isolation,
resource data, configuration registers) are found and configured by the real
ROM code at the end of POST: an AWE64-style card (audio, wavetable, game
port), a PnP modem, and a card that cannot be satisfied. Also the Tools page,
its settings (off, IRQ/DMA/I/O kept free for non-PnP cards) and Shift.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pnptools import awe64, modem, only_irq5  # noqa: E402
from tools_harness import ENTER, ESC, G_BASE, key, machine, run_tools  # noqa: E402

if len(sys.argv) <= 1:
    subprocess.check_call([sys.executable, os.path.join(HERE, "..", "tools", "build_rom.py"), "--all"],
                          stdout=subprocess.DEVNULL)
failed = []
POST_STACK = dict(ss=0x0000, sp=0x0400)


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def setup(*cards, flag=0xA5):
    m = machine(flag=flag)
    m.pnp.cards = list(cards)
    return m


def postend(m):
    m.near_call(0xF000, G_BASE + 3, max_insns=600_000_000, **POST_STACK)


def io(card, ldn, n):
    r = card.ld(ldn)
    return r.get(0x60 + 2 * n, 0) << 8 | r.get(0x61 + 2 * n, 0)


def cfg(card, ldn):
    r = card.ld(ldn)
    return dict(io=[io(card, ldn, n) for n in range(3)], irq=r.get(0x70), irq2=r.get(0x72),
                dma=(r.get(0x74), r.get(0x75)), active=r.get(0x30) == 1, irqtype=r.get(0x71))


def keep(m, irqs=(), dmas=(), io1=(0, 0), io2=(0, 0), off=False):
    c = m.cmos
    vals = [1 if off else 0, sum(1 << i for i in irqs) & 0xFF, sum(1 << i for i in irqs) >> 8,
            sum(1 << d for d in dmas), io1[0] & 0xFF, io1[0] >> 8, io1[1], io2[0] & 0xFF, io2[0] >> 8, io2[1]]
    c[0x54] = ord("P")
    c[0x55:0x5F] = bytes(vals)
    c[0x5F] = ~(sum(c[0x54:0x5F])) & 0xFF


# ---------------------------------------------------------------- an AWE64
card = awe64()
m = setup(card)
postend(m)
a, w, g = cfg(card, 0), cfg(card, 1), cfg(card, 2)
check(card.csn == 1 and card.state == "wfk", "AWE64: found, CSN 1, left waiting for the key")
check(a["io"] == [0x220, 0x330, 0x388] and a["irq"] == 5 and a["dma"] == (1, 5) and a["active"]
      and a["irqtype"] == 2, "AWE64 audio: 220h/330h/388h, IRQ 5 (edge, high), DMA 1 and 5, activated (%r)" % (a,))
check(w["io"] == [0x620, 0xA20, 0xE20] and w["active"] and w["irq"] == 0 and w["dma"] == (4, 4),
      "AWE64 wavetable: 620h/A20h/E20h, no IRQ or DMA, activated")
check(g["io"][0] == 0x200 and g["active"], "AWE64 game port: 200h, activated")
run_tools(m, [key("p")])
t = m.screen_text()
check("Creative SB AWE64  PnP  (CTL009D)" in t or "Creative SB AWE64 PnP  (CTL009D)" in t,
      "Tools: lists the card by name and ID")
check("CTL0045  I/O 220 330 388  IRQ 5  DMA 1 5" in t and "CTL0022  I/O 620 A20 E20" in t
      and "CTL7002  I/O 200" in t, "Tools: each device with its resources")
check("SET BLASTER=A220 I5 D1 H5 P330 E620 T6" in t, "Tools: the BLASTER line for DOS")
check("1 card, 3 of 3 devices configured" in t, "Tools: status line")
m2 = setup(awe64(), flag=0x00)
m2.keys = [0x1C0D]
postend(m2)
check("Plug and Play         1 card, 3 of 3 devices configured" in m2.screen_text(), "summary: Plug and Play line")

# ---------------------------------------------------------------- kept free for non-PnP cards
card = awe64()
m = setup(card)
keep(m, irqs=[5])
postend(m)
a = cfg(card, 0)
check(a["irq"] == 10 and a["active"] and a["io"][0] == 0x220,
      "IRQ 5 kept free: the audio takes the next set and IRQ 10 (%r)" % (a,))
card = awe64()
m = setup(card)
keep(m, io1=(0x220, 0x20))
postend(m)
a = cfg(card, 0)
check(a["io"][0] == 0x240 and a["active"], "I/O 220h-23Fh kept free: the audio moves to 240h")
card = awe64()
m = setup(card)
keep(m, dmas=[1])
postend(m)
a = cfg(card, 0)
check(a["dma"][0] in (0, 3) and a["dma"][0] != 1 and a["active"], "DMA 1 kept free: another channel (%r)" % (a["dma"],))

# ---------------------------------------------------------------- off, Shift, nothing there
card = awe64()
m = setup(card)
keep(m, off=True)
postend(m)
check(card.csn == 0 and not cfg(card, 0)["active"], "off: the card is not touched")
run_tools(m, [key("p")])
check("This boot: off" in m.screen_text(), "off: Tools says so")
card = awe64()
m = setup(card)
m.write(0x417, bytes([0x02]))
postend(m)
check(not cfg(card, 0)["active"], "Shift held: skipped this boot")
m = setup()
postend(m)
run_tools(m, [key("p")])
check("no PnP cards found" in m.screen_text(), "no cards: says so")

# ---------------------------------------------------------------- several cards, conflicts
c1, c2 = awe64(), modem()
m = setup(c1, c2)
postend(m)
a, mo = cfg(c1, 0), cfg(c2, 0)
check(c1.csn in (1, 2) and c2.csn in (1, 2) and c1.csn != c2.csn, "two cards: each gets its own CSN")
check(mo["active"] and mo["io"][0] not in (0x2F8,) and mo["irq"] not in (3, 4, 5, 7),
      "modem: COM2 (2F8h, IRQ 3) is taken, so it gets %Xh, IRQ %s" % (mo["io"][0], mo["irq"]))
check(a["irq"] == 5 and a["active"], "...and the AWE64 still gets IRQ 5")
c3 = only_irq5()
m = setup(c3)
keep(m, irqs=[5])
postend(m)
check(not cfg(c3, 0)["active"] and c3.state == "wfk", "a device that only takes IRQ 5, with IRQ 5 kept free, is left off")
run_tools(m, [key("p")])
check("not configured: no free resources fit" in m.screen_text(), "Tools: says which device could not be configured")

# ---------------------------------------------------------------- the settings page
card = awe64()
m = setup(card)
postend(m)
run_tools(m, [key("p"), key("i")] + [key("5"), ENTER] + [key("1")] + [key(c) for c in "2A0"] + [ENTER]
          + [key(c) for c in "20"] + [ENTER] + [key("s")])
c = m.cmos
check(c[0x54] == ord("P") and c[0x56] == 0x20 and c[0x59:0x5C] == bytes([0xA0, 0x02, 0x20])
      and c[0x5F] == ~(sum(c[0x54:0x5F])) & 0xFF, "Tools: IRQ 5 and I/O 2A0h-2BFh kept free, saved to CMOS 54h-5Fh")
check("Kept free: I/O        2A0-2BF" in m.screen_text() and "Kept free: IRQ        5" in m.screen_text(),
      "Tools: shows what is kept free")
run_tools(m, [key("p"), key("r")])
check(cfg(card, 0)["irq"] == 10 and "configured again" in m.screen_text(), "Tools: R configures the cards again now")
m = setup(awe64())
run_tools(m, [key("p"), key("c"), key("s")])
check(m.cmos[0x55] & 1, "Tools: C switches it off, saved")

print("\n%d failed" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
