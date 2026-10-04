"""Run the BIOS's POST hard-disk init (F000:9062) against simulated IDE setups.

    python tests/hdinit.py [IMAGE.BIN]

Reports per case: whether POST returned, messages printed, drives counted,
IDE commands issued, INT 13h AH=10h "drive ready" retries (each followed by a
~1 ms delay on real hardware) and an estimate of real time.
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from emu import ORIGINAL, AtaDisk, Atapi, IdeChannel, Machine, cmos_checksum  # noqa: E402


def run(image=ORIGINAL, master=None, slave=None, ctype=0x20, float_value=0xFF, limit=400_000_000,
        ext=(0, 0), status0e=0):
    m = Machine(image)
    m.install_rom_vectors()
    m.cmos[0x10], m.cmos[0x12], m.cmos[0x0E] = 0x40, ctype, status0e
    m.cmos[0x19], m.cmos[0x1A] = ext
    cmos_checksum(m.cmos)
    m.ide = IdeChannel(m, master, slave, float_value)
    m.write(0x4AE, struct.pack("<H", 1))       # tiny delay so the emulator is quick
    t = time.time()
    try:
        m.near_call(0xF000, 0x9062, max_insns=limit, ds=0x40, es=0)
        m.result = "returned"
    except Exception as e:  # noqa: BLE001
        m.result = "STOP: %s" % e
    m.host_seconds = time.time() - t
    m.ready_retries = sum(1 for n, ax in m.ints if n == 0x13 and ax >> 8 == 0x10)
    # I/O at ~1 us each, plus ~1 ms of calibrated delay per ready retry.
    m.real_seconds = m.io_count * 1e-6 + m.ready_retries * 1e-3
    m.cmds = [c[1] for c in m.ide.log if isinstance(c[1], int)]
    return m


CASES = [
    ("C=auto, old 615/4/17 disk", dict(master=AtaDisk(615, 4, 17, "OLD"))),
    ("C=auto, big 16383/16/63 disk", dict(master=AtaDisk(16383, 16, 63, "BIG"))),
    ("C=auto, CD-ROM as master", dict(master=Atapi())),
    ("C=type 4, CD-ROM as master", dict(master=Atapi(), ctype=0x40)),
    ("C=auto, nothing (bus FFh)", dict()),
    ("C=auto, nothing (bus 7Fh)", dict(float_value=0x7F)),
    ("C=auto disk + CD-ROM slave, D=0", dict(master=AtaDisk(615, 4, 17), slave=Atapi())),
    ("C=auto disk, D=auto CD-ROM slave", dict(master=AtaDisk(615, 4, 17), slave=Atapi(), ctype=0x23)),
    ("C=0, CD-ROM as master", dict(master=Atapi(), ctype=0x00)),
    ("C=auto disk, D=auto, no slave", dict(master=AtaDisk(615, 4, 17), ctype=0x23)),
    ("C=type 4, nothing (bus FFh)", dict(ctype=0x40)),
    ("C=auto disk, settings lost (0Eh=C0h)", dict(master=AtaDisk(615, 4, 17), ctype=0x23, status0e=0xC0)),
]


def describe(label, m):
    tbl = m.read(0xFE411, 16)
    geo = "%d/%d/%d" % (struct.unpack_from("<H", tbl)[0], tbl[2], tbl[14])
    print("%-36s %-8s real~%5.1fs retries=%-6d drives=%d slot2=%-10s cmds=%s msgs=%r" % (
        label, m.result[:8], m.real_seconds, m.ready_retries, m.mem_byte(0x475), geo,
        " ".join("%02X" % c for c in m.cmds[:8]), m.text().replace("\r\n", " | ").strip(" |")[:80]))


if __name__ == "__main__":
    image = sys.argv[1] if len(sys.argv) > 1 else ORIGINAL
    print("image:", os.path.basename(image))
    for label, kw in CASES:
        describe(label, run(image, **kw))
