"""Fix the checksums of a (modified) NCR 486 BIOS image.

Usage:  python tools/fix_checksum.py IMAGE.BIN [OUT.BIN]

The 128 KB image holds:
  00000-07FFF  Cirrus Logic VGA option ROM (55 AA 40), 8-bit sum must be 00
  08000-0FFFF  unused (FF)
  10000-1FFFF  system BIOS, F000 segment, 8-bit sum must be 00;
               the correction byte lives at F000:FFFF (image offset 1FFFF)
The VGA ROM's correction byte is its last byte (image offset 07FFF).
"""
import sys

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else src
d = bytearray(open(src, "rb").read())
assert len(d) == 0x20000, "expected a 128 KB image"


def fix(start, length, name):
    last = start + length - 1
    old = d[last]
    d[last] = 0
    d[last] = (-sum(d[start:start + length])) & 0xFF
    state = "unchanged" if d[last] == old else "%02Xh -> %02Xh" % (old, d[last])
    print("%-12s checksum byte at %05Xh: %s" % (name, last, state))


assert d[0] == 0x55 and d[1] == 0xAA and d[2] == 0x40, "VGA option ROM header missing"
fix(0x00000, 0x8000, "VGA ROM")

# Tools extension at image 08000 (E800:0000): "NCRX", word size, word checksum.
# The 16-bit sum of all words in [08000, 08000+size) must be 0.
if d[0x8000:0x8004] == b"NCRX":
    size = d[0x8004] | (d[0x8005] << 8)
    assert 8 <= size <= 0x8000 and size % 2 == 0, "bad tools extension size"
    d[0x8006] = d[0x8007] = 0
    s = sum(d[0x8000 + i] | (d[0x8001 + i] << 8) for i in range(0, size, 2)) & 0xFFFF
    c = (-s) & 0xFFFF
    d[0x8006], d[0x8007] = c & 0xFF, c >> 8
    print("%-12s checksum word at 08006h: %04Xh (%d bytes)" % ("Tools ext", c, size))

fix(0x10000, 0x10000, "System BIOS")
open(dst, "wb").write(d)
print("wrote", dst)
