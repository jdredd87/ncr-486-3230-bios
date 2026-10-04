"""Apply a byte patch file to the NCR BIOS image, then fix both checksums.

Usage:  python tools/apply_patch.py PATCHFILE [IN.BIN] [OUT.BIN]
Defaults: IN  = NCR-BIOS-517-0000672-VER2.03.00-U19.BIN
          OUT = build/<patchfile name>.BIN

Patch file format, one change per line ('#' or ';' starts a comment):

    F000:9EE0  00 00 00  ->  B8 34 12     ; system BIOS address
    FA40:0310  4C 04     ->  4D 04        ; Setup module address (= F000:A400 + offset)
    IMG:1FFA0  4E        ->  6E           ; raw image offset

The bytes left of '->' must match the image exactly, or nothing is written.
That guards against patching the wrong spot or applying a patch twice.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
patch_path = sys.argv[1]
src = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "NCR-BIOS-517-0000672-VER2.03.00-U19.BIN")
dst = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
    HERE, "..", "build", os.path.splitext(os.path.basename(patch_path))[0] + ".BIN")

img = bytearray(open(src, "rb").read())
assert len(img) == 0x20000, "expected a 128 KB image"


def image_offset(addr):
    seg, off = addr.split(":")
    off = int(off, 16)
    if seg.upper() == "IMG":
        return off
    seg = int(seg, 16)
    linear = seg * 16 + off
    if not 0xE0000 <= linear < 0x100000:
        raise ValueError("%s is outside the ROM (E0000-FFFFF)" % addr)
    return linear - 0xE0000


errors, changes = [], []
for n, line in enumerate(open(patch_path), 1):
    line = re.split(r"[#;]", line, maxsplit=1)[0].strip()
    if not line:
        continue
    m = re.match(r"(\S+)\s+([0-9A-Fa-f ]+?)\s*->\s*([0-9A-Fa-f ]+)$", line)
    if not m:
        errors.append("line %d: cannot parse: %s" % (n, line))
        continue
    at = image_offset(m.group(1))
    old, new = bytes.fromhex(m.group(2)), bytes.fromhex(m.group(3))
    if len(old) != len(new):
        errors.append("line %d: old and new byte counts differ (%d vs %d)" % (n, len(old), len(new)))
        continue
    have = bytes(img[at:at + len(old)])
    if have != old:
        errors.append("line %d: %s expected %s, image has %s" % (n, m.group(1), old.hex(" "), have.hex(" ")))
        continue
    changes.append((at, new, m.group(1)))

if errors:
    print("\n".join(errors))
    sys.exit("patch NOT applied")
for at, new, where in changes:
    img[at:at + len(new)] = new
    print("patched %-10s (image %05Xh) %d byte(s)" % (where, at, len(new)))

os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
open(dst, "wb").write(img)
subprocess.check_call([sys.executable, os.path.join(HERE, "fix_checksum.py"), dst])
