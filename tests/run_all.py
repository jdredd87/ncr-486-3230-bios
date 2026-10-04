"""Run every test: python tests/run_all.py

Builds the improved ROM first, then runs each test script and prints a
one-line result per script. Exit code is non-zero if any script fails.
(tests/hdinit.py is a report, not a test: run it on its own.)
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SCRIPTS = ["test_userhdd.py", "test_userhdd_dos.py", "test_patches.py", "test_fancy.py", "test_tools.py",
           "test_cdboot.py", "test_hdsetup.py",
           "test_lba.py"]

subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build_rom.py"), "--all"],
                      stdout=subprocess.DEVNULL)
failed = 0
for s in SCRIPTS:
    t = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, s)], capture_output=True, text=True)
    passes = r.stdout.count("PASS ")
    fails = r.stdout.count("FAIL ")
    ok = r.returncode == 0 and fails == 0
    failed += not ok
    print("%-22s %s  %d passed, %d failed  (%.0f s)" % (s, "ok  " if ok else "FAIL", passes, fails, time.time() - t))
    if not ok:
        print("\n".join(l for l in r.stdout.splitlines() if l.startswith("FAIL")) or r.stdout[-2000:])
        print(r.stderr[-2000:])
print("all passed" if not failed else "%d script(s) failed" % failed)
sys.exit(1 if failed else 0)
