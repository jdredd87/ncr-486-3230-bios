"""Build a ROM image from the original plus a list of patches.

Usage:  python tools/build_rom.py OUT.BIN PATCH [PATCH ...]
        python tools/build_rom.py --all        (the recommended set, see RECOMMENDED)

Each PATCH is a name in patches/ (with or without .patch). Patch sources in
patches/src/*.asm are re-assembled first so the .patch files are current.
Patches are applied in order to the original image; every one verifies the
original bytes it replaces, so overlapping patches are refused. Both
checksums are fixed at the end and the SHA-256 of the result is printed.
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ORIGINAL = os.path.join(ROOT, "NCR-BIOS-517-0000672-VER2.03.00-U19.BIN")
RECOMMENDED = ["no_burnin", "battery_prompt", "ide_nodrive_fast", "ide_atapi_skip", "setup_year"]
RECOMMENDED_OUT = os.path.join(ROOT, "build", "NCR3230-203-improved.BIN")


def regenerate():
    src = os.path.join(ROOT, "patches", "src")
    for f in sorted(os.listdir(src)):
        if f.endswith(".asm"):
            subprocess.check_call([sys.executable, os.path.join(HERE, "asm2patch.py"),
                                   os.path.join(src, f)], stdout=subprocess.DEVNULL)


def build(out, names):
    regenerate()
    cur = ORIGINAL
    tmp = out + ".tmp"
    for i, n in enumerate(names):
        p = os.path.join(ROOT, "patches", n if n.endswith(".patch") else n + ".patch")
        r = subprocess.run([sys.executable, os.path.join(HERE, "apply_patch.py"), p, cur, tmp],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit("patch %s failed:\n%s%s" % (n, r.stdout, r.stderr))
        os.replace(tmp, out)
        cur = out
        print("applied", n)
    d = open(out, "rb").read()
    assert sum(d[0x10000:]) & 0xFF == 0 and sum(d[:0x8000]) & 0xFF == 0
    print("wrote %s\nSHA-256 %s" % (os.path.abspath(out), hashlib.sha256(d).hexdigest()))


if __name__ == "__main__":
    if sys.argv[1:] == ["--all"]:
        build(RECOMMENDED_OUT, RECOMMENDED)
    else:
        build(sys.argv[1], sys.argv[2:])
