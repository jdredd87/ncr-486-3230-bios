"""Replacement for NCR's lost USERHDD.EXE (user-defined hard disk, Setup type 1).

Usage:  python tools/userhdd.py CYLINDERS HEADS SECTORS [OUT.SCR]
Example: python tools/userhdd.py 1024 16 63          (any IDE drive >= 504 MB)

It writes a DOS DEBUG script (default build/USERHDD.SCR). Boot DOS from a
floppy on the NCR machine, then run:
    DEBUG < USERHDD.SCR
Then enter Setup and set the fixed disk type to 1.

What USERHDD.EXE did, as read from the BIOS:
  POST (F000:3C58) copies these CMOS bytes into the type-1 slot of the drive
  table at F000:E401 when drive C or D is type 1. Setup (FA40:1227) refuses
  type 1 unless the same checksum is valid.

  CMOS  field (standard AT fixed-disk parameter table offset)
  72h   cylinders, low byte      (+0)
  73h   cylinders, high byte     (+1)
  74h   heads                    (+2)
  75h   write precomp, low       (+5)   FFFFh = none
  76h   write precomp, high      (+6)
  77h   max ECC burst            (+7)
  78h   control byte             (+8)   bit 3 set when heads > 8
  79h   landing zone, low        (+C)
  7Ah   landing zone, high       (+D)
  7Bh   sectors per track        (+E)
  7Ch   checksum: low byte of the sum of 72h..7Bh (and that sum must not be 0)

Only one type-1 geometry exists. C and D both use it if both are set to type 1.
"""
import os
import sys

if len(sys.argv) < 4:
    sys.exit(__doc__)
cyl, heads, spt = (int(x) for x in sys.argv[1:4])
out = sys.argv[4] if len(sys.argv) > 4 else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "..", "build", "USERHDD.SCR")
if not 1 <= cyl <= 1024:
    sys.exit("cylinders must be 1..1024 (the BIOS is CHS-only; use 1024 for bigger drives)")
if not 1 <= heads <= 16:
    sys.exit("heads must be 1..16")
if not 1 <= spt <= 63:
    sys.exit("sectors per track must be 1..63")

wpc, lz = 0xFFFF, cyl
data = [cyl & 0xFF, cyl >> 8, heads, wpc & 0xFF, wpc >> 8, 0,
        0x08 if heads > 8 else 0x00, lz & 0xFF, lz >> 8, spt]
total = sum(data)
assert total & 0xFFFF, "checksum sum must be non-zero"
data.append(total & 0xFF)

lines = []
for reg, val in zip(range(0x72, 0x7D), data):
    lines += ["o 70 %02X" % reg, "o 71 %02X" % val]
lines.append("q")

os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
with open(out, "w", newline="\r\n") as f:
    f.write("\n".join(lines) + "\n")

mb = cyl * heads * spt * 512 / (1024 * 1024)
print("geometry %d cyl x %d heads x %d spt = %.1f MB (%.0f MB decimal)"
      % (cyl, heads, spt, mb, cyl * heads * spt * 512 / 1e6))
print("CMOS 72h-7Ch:", " ".join("%02X" % b for b in data))
print("wrote", os.path.abspath(out))
