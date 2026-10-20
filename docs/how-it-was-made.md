# Reworking the NCR 3230 BIOS: tools and process

How the original NCR BIOS was taken apart, studied and improved, and which tools did each step. Written 2026-10-18 by StevenC & Claude, at Enhanced Edition 1.4; updated for 1.8.

## Overview

The NCR System 3230 BIOS was never decompiled into source code and rebuilt. We disassembled the original ROM so we could read it, then wrote new code in assembly and patched it into the original image. Every byte outside the patched spots is still NCR's.

- **Starting point:** NCR BIOS 517-0000672, version 2.03.00, dated 10/08/93, chip U19. It is a 128 KB image holding a Cirrus Logic VGA BIOS and NCR's system BIOS.
- **Result:** the *Enhanced Edition*, now at version 1.8. It adds a Tools menu (F10), CD-ROM boot, a boot menu and saved boot order, large hard disks, PicoMEM handling, chipset and video memory timing settings and ISA Plug and Play.
- **Repository:** [github.com/jdredd87/ncr-486-3230-bios](https://github.com/jdredd87/ncr-486-3230-bios).

Patching in place was chosen over a full rebuild for three reasons:

1. **Risk.** A rebuilt BIOS must match the original byte for byte before any change is safe. A patch touches only the bytes it names, and checks them first.
2. **Compatibility.** DOS-era software jumps straight into fixed BIOS addresses. Patching never moves them.
3. **Effort.** Only the parts being changed need to be understood, not all 64 KB of NCR's code.

## The toolchain

Everything used is free, and every project script is in the repository. No commercial disassembler (IDA, Ghidra) was used. The whole chain runs on Python 3 plus NASM.

| Tool | Kind | Used for |
| --- | --- | --- |
| Python 3 | language | Every script below |
| [Capstone](https://www.capstone-engine.org/) 5 | disassembly library | Decoding 16-bit x86 instructions inside the disassembler |
| [Unicorn](https://www.unicorn-engine.org/) 2 | CPU emulator library | Running the real ROM code in the test rig |
| [NASM](https://www.nasm.us/) | assembler | Assembling every patch and the Tools extension |
| Free Pascal (i8086-msdos) | compiler | Building the USERHDD.EXE replacement for DOS |
| `tools/disasm_bios.py` | project script | Recursive-descent disassembler: ROM to readable listings |
| `tools/asm2patch.py` | project script | Assembles a patch source and records old and new bytes |
| `tools/apply_patch.py` | project script | Applies one `.patch` file after checking the old bytes |
| `tools/build_rom.py` | project script | Builds the full improved ROM, prints its version and SHA-256 |
| `tools/fix_checksum.py` | project script | Corrects the VGA and system BIOS checksum bytes |
| `tools/emu.py` | project script | PC emulator: CMOS, chipset, IDE, ATAPI CD, ISA PnP, keyboard, video |
| `tools/dosemu.py` | project script | Minimal DOS layer on top of the emulator, to run DOS EXEs |
| `tools/version.py` | project script | Reads the Enhanced Edition version for the build and tests |
| `tests/*.py` | project scripts | 393 checks comparing the original ROM with the improved one |
| EPROM programmer | hardware | Reading the original chip and burning new ones |

The Python libraries install with `pip install -r requirements.txt` (`capstone>=5.0`, `unicorn>=2.1`).

## Step 1: taking the ROM apart

The chip was read with a programmer into `NCR-BIOS-517-0000672-VER2.03.00-U19.BIN`, which is never modified. Its SHA-256 is `f634b7b83cb80fe6f9a6ba17fb40eb79695cce652a6b99e1b5f72ad1b3098e03`, and every build starts from this file.

The 128 KB image holds three areas:

| Image offset | CPU sees it at | Contents |
| --- | --- | --- |
| 00000–07FFF | E000:0000 | Cirrus Logic CL-GD542x VGA BIOS v1.30 (`55 AA 40`), checksum byte at 07FFF |
| 08000–0FFFF | E800:0000 | Unused, all FFh. This became the home of the Tools extension. |
| 10000–1FFFF | F000:0000 | NCR system BIOS, 64 KB, checksum byte at F000:FFFF |

The system BIOS itself splits into three parts:

- **F000:0000–A3FF:** POST, burn-in and diskette diagnostics, the INT 13h hard-disk handler, keyboard, INT 15h and message text.
- **F000:A400–DFFF:** the Setup module. It has its own `55 AA` header, is assembled at offset 0 and runs as segment FA40.
- **F000:E000–FFFF:** the IBM PC/AT fixed entry points, the 8×8 font, vector tables, the reset vector at FFF0 and the date "10/08/93".

The VGA and system BIOS were cut out into `split/` for the disassembler. The VGA BIOS has never been changed: the one video feature, a faster video memory clock (1.5), is set from the Tools extension after the VGA BIOS has started. Each area has an 8-bit checksum that must add up to 00h, so any change needs a correction byte fixed afterwards. `tools/fix_checksum.py` does that.

## Step 2: disassembling and understanding the code

A plain disassembler run over a BIOS mixes code and data, because tables, strings and code sit side by side. So we wrote `tools/disasm_bios.py`, a recursive-descent disassembler that decodes with Capstone. It starts only where code is certain to be, and follows the code from there:

- the reset vector (FFF0) and the IBM fixed entry points;
- the ROM interrupt vector tables at F000:FEF3 and FF23, and handlers POST installs;
- "ROM-stack" calls, which POST makes before RAM works (`mov sp, X` / `jmp`, with the return address stored at X);
- jump tables, sized from the `cmp` limit or count word in front of them;
- far calls, and calls whose argument follows inline (FA40:1A90 prints the string whose offset comes after the call).

Anything not reached is written out as strings or `db` rows. The output is two listings: `out/system_bios_F000.lst` (about 21,400 lines) and `out/module_FA40.lst` for Setup (about 4,850 lines), made with `--module A400:0003:FA40`.

The listings were then read section by section, and findings went into [bios-notes.md](bios-notes.md). The ones that shaped the project:

- **Free space.** Zero-filled gaps inside F000 (1,325 bytes at 9ED3, 763 at EC5C, 530 at F85C and smaller ones), and the empty 32 KB at E800.
- **The hard-disk handler** (F000:94E3) supports INT 13h functions 00h–15h only: CHS, so about 504 MB at most.
- **Why POST stalls.** A CD-ROM or a missing drive with a drive type set costs 16–32 s of retry loops.
- **The burn-in trap.** A certain keyboard failure reboots into NCR's factory burn-in mode, where F1 does nothing.
- **CMOS use.** Which bytes POST and Setup check and default, and which are free (48h, 4Ah–5Fh).
- **The hidden floppy test.** NCR's floppy drive test (F000:0C00) is reachable only through Ctrl-D.
- **USERHDD.EXE.** Drive type 1 reads a geometry from CMOS 72h–7Ch that NCR's lost utility used to write.

## Step 3: the emulator test rig

Burning a chip for every try would be slow, and a bad ROM leaves the machine dead. So `tools/emu.py` runs the real ROM code, not a rewrite of it, on the Unicorn CPU emulator in 16-bit real mode, against simulated hardware:

| Simulated part | What it does |
| --- | --- |
| Memory | 1 MB address space, with the 128 KB image mapped at E0000–FFFFF |
| CMOS and clock | Ports 70h/71h with 128 bytes of CMOS RAM |
| Chipset | Index and data ports 22h/24h, including the write-protect bit for the shadowed F000 BIOS |
| Cirrus video chip | Extended sequencer and CRTC registers: unlock, chip ID, memory size, memory clock |
| IDE | Master and slave: none, an ATA disk of any size, or an ATAPI CD-ROM reading an ISO file, with or without a disc |
| Timer and refresh | PIT and port 61h, so the BIOS's delay loops finish |
| ISA Plug and Play | Cards with the initiation key, serial isolation, resource data and configuration registers |
| Keyboard and screen | Keys queued for INT 16h, and the text screen read back for checks |

The tests in `tests/` (11 scripts, 393 checks, run with `python tests/run_all.py`) call routines in the original ROM and in the improved one and compare what happens. They check, for example, how long POST waits with a CD-ROM, what CMOS holds after a lost battery, whether a 34 GB disk reads the right sectors, or which IRQ an AWE64 gets.

Two helpers build test inputs on the fly: `isotools.py` makes bootable El Torito ISO images, and `pnptools.py` makes AWE64-style and modem PnP cards. `tools/dosemu.py` adds enough DOS to run USERHDD.EXE against the emulated CMOS. `tests/preview_screens.py` renders the boot, Setup and Tools screens to `build/preview.html`, so the screens could be checked before burning.

## Step 4: writing the changes

Every change is NASM assembly in `patches/src/*.asm`. A source file is split into chunks, and each chunk names the address it goes to and what must be there now:

```
;@ F000:474F max=4          place this code at F000:474F, at most 4 bytes
    jmp 0x4769
    nop
;@ F000:9F24 free           ...the original bytes there must be 00 (free space)
;@ E800:0000 ff             ...the original bytes there must be FF (erased)
```

`tools/asm2patch.py` assembles each chunk on its own with `org` set to its address, so jumps and calls into NCR's code encode correctly. It then writes a `.patch` file listing each address with the original bytes and the new ones. This is the whole of `no_burnin.patch`, which turns a conditional jump into an unconditional one:

```
F000:474F  0F 85 16 00  ->  E9 17 00 90
```

The original bytes always come from the untouched dump. `apply_patch.py` refuses a patch whose original bytes don't match, which guards against patching the wrong spot or patching twice. Two patches that overlap are refused for the same reason.

There are eight patches, applied in this order:

| Patch | What it changes |
| --- | --- |
| `no_burnin` | One jump: a keyboard failure no longer reboots into burn-in mode |
| `error_prompts` | POST prompts continue after a countdown |
| `ide_nodrive_fast` | A drive type with nothing connected: 0.05 s instead of 16 s |
| `ide_atapi_skip` | A CD-ROM where a hard-disk type is set: skipped in 1 s instead of 32 s |
| `hdd_auto` | Automatic hard disks by default, absent drives skipped |
| `setup_year` | Setup accepts two-digit years 00–79 |
| `fancy_boot` | Blue boot screen, coloured messages, credits, Setup switch |
| `tools_rom` | The Tools extension at E800 and the glue that calls it |

The small patches fit in NCR's free gaps. The large features did not, so `tools_rom` (about 7,900 lines of assembly) puts them in the empty 32 KB at E800, where about 25.9 KB is now used. It starts with an `NCRX` signature, a size word and a checksum. Its fixed entry points are E800:000A (Tools), 000D (end of POST), 0010 (clock speed), 0013 (boot), 0016 (disk set-up) and 0019 (option-ROM capture).

NCR's code reaches the extension through a small jump table, the **glue**, at F000:F860. A few of NCR's calls are redirected into it, for example the end-of-POST beep (F000:47B6), the disk init call (F000:436E) and the INT 19h boot entry (F000:E6F2). The glue checks the signature and checksum before every call. If the E800 area is missing or damaged, the glue runs NCR's original code instead, so the machine still boots.

```
Calls patched in NCR's code              Glue                     Tools extension, E800
+------------------------------+
| Processor speed line  3891   |--+
| Hard disk init call   436E   |--+
| End-of-POST beep      47B6   |--+--> Glue jump table F000:F860
| F8 / F10 key check    47CB   |--+              |
| INT 19h boot entry    E6F2   |--+              v
+------------------------------+        NCRX signature and    yes   000A Tools and boot menus
                                        checksum OK?  ---------->   000D Chime and summary
                                               |                    0010 Clock speed
                                               | no                 0013 Boot: menu, order, CD
                                               v                    0016 Large-disk set-up
                                        NCR's original code         0019 Chipset, PnP, INT 19h
                                        (that feature stays off)
```

## Step 5: building, checking and flashing

One command builds the finished ROM: `python tools/build_rom.py --all`.

1. It re-assembles every `patches/src/*.asm` into its `.patch` file, so the patches always match their sources.
2. It applies the eight patches in order to a copy of the original dump. Each patch first checks the bytes it replaces.
3. It fixes both checksum bytes: the VGA BIOS at 07FFF and the system BIOS at F000:FFFF.
4. It writes `build/NCR3230-203-improved.BIN` and prints the Enhanced Edition version and the image's SHA-256.

`python tests/run_all.py` runs the build and then all 393 checks. A version is burned only when every check passes.

The BIOS has no flash-writing code, so chips are programmed with an external EPROM programmer, in this order:

1. Read the original chip and confirm the dump's SHA-256 (`f634b7b8…`), so the dump is known to be exact.
2. Program the original image into a new chip and boot it. That proves the chip type and the programmer.
3. Program the improved image, keeping the original chip as a fallback. Version 1.8's SHA-256 is `6bf1fdc14eadbc92f1ec2fdc1723afa44942582ad5300d9917fe01d72a4d6b3b`.

The version lives in one file, `patches/src/version.inc`. It shows on the boot screen, the end-of-POST summary, Setup's title line and Tools → System information, and is stored at E800:0008. Each burned version gets a [CHANGELOG.md](../CHANGELOG.md) entry and a git tag. NCR's own version (2.03.00) and date (10/08/93) are never changed, because DOS-era software reads them.

## What was built from there

The work ran from 2026-09-30 to 2026-10-19: fixes first, then the Tools extension, then the numbered releases. Newest first:

| Date | Version | What it added |
| --- | --- | --- |
| 2026-10-19 | 1.5 | Video memory clock setting for the Cirrus video chip; the Video line names the chip and its memory |
| 2026-10-19 | 1.6 | The memory test catches parity errors (a bad parity chip on a stick) and names the 16-byte line |
| 2026-10-19 | 1.7 | Memory test log fix (addresses after the sixth entry) and the range of parity errors |
| 2026-10-19 | 1.8 | Video memory clock moved to CMOS 60h (NCR's POST cleared 53h); video memory speed test |
| 2026-10-06 | 1.4 | ISA Plug and Play: PnP cards such as the AWE64 are found and configured at boot, with a Tools page and the `SET BLASTER=` line |
| 2026-10-05 | 1.3 | Chipset identified as UMC 82C480; Tools chipset settings (bus clock, I/O recovery, DRAM and L2 wait states) with a fail-safe |
| 2026-10-05 | 1.2 | Tools chipset register viewer |
| 2026-10-05 | 1.1 | "INTERRUPT CONTROLLERS" in the POST list no longer shown in red |
| 2026-10-05 | 1.0 | First numbered release: everything below, plus the version on every screen |
| 2026-10-05 | — | Saved boot order, with an editor that lists all devices |
| 2026-10-05 | — | PicoMEM and other option ROMs that take over booting: the BIOS keeps control; summary shown 8 s |
| 2026-10-04 | — | Large-disk (LBA) mode: up to 8.4 GB through CHS, 128 GB through the INT 13h extensions |
| 2026-10-04 | — | Hard disks Automatic by default; Tools Hard disk setup replaces USERHDD.EXE |
| 2026-10-04 | — | CD-ROM boot (El Torito), floppy emulation and no emulation; confirmed on the machine |
| 2026-10-04 | — | Tools extension at E800: Tools menu (F10), boot menu (F8), system summary, measured clock |
| 2026-10-03 | — | Auto-continuing POST prompts, blue boot screen, credits, chime; first boot on the real machine |
| 2026-09-30 | — | POST fixes for CD-ROMs and missing drives, Setup year fix, the NASM patch pipeline |
| 2026-09-30 | — | USERHDD.EXE replacement in Free Pascal, and the emulator test rig |
| 2026-09-30 | — | First disassembly of the ROM, tools and first patches |

On the real machine so far: POST, boot, Tools, the summary and CD-ROM boot work. Large-disk mode, Hard disk setup, the PicoMEM handling, the boot order, chipset settings and Plug and Play are tested in the emulator; hardware results are still to come.

## Hardware research: the chipset

NCR's BIOS writes 16 chipset registers from a table at F000:2225 but never names them, and UMC's published overviews list features, not registers. The register map came from another vendor's BIOS for the same chips.

1. **The chips.** Photos of the CPU board showed the UMC UM82C481BF (memory controller), UM82C482AF (system controller) and UM82C206F (DMA, interrupts, timer, clock), plus an SMC FDC37C661 for the floppy, IDE, serial and parallel ports. A socketed 33.3 MHz oscillator drives the CPU and bus.
2. **A first look on the machine.** Version 1.2 added a read-only register viewer to Tools, showing registers 80h–9Fh beside the values NCR's table writes.
3. **The decoding.** An AMI BIOS dated 06/06/92 for another UMC 480 board has an Advanced Chipset Setup screen. Its setup records give each option's CMOS byte, bit mask and choices. Its code copies CMOS into the chipset with register = CMOS address + 30h (a `sub al, 30h` at offset 8FD6h). Its help texts confirm the result, for example "DRAM Read WS … controlled by bits 3-2 of register 91H".
4. **Settings with a safety net.** Version 1.3 turned the decoded fields into Tools → 9 settings: ISA bus clock (81h), I/O recovery (82h), and DRAM and L2 cache wait states (91h). They are saved in CMOS 4Eh–51h and applied at the end of POST. CMOS 52h is set to `P` before applying and cleared once the boot reaches INT 19h or Tools; if a boot never gets that far, the next one skips the settings. Holding Shift at the end of POST skips them once.

The full map is in [chipset-umc480.md](chipset-umc480.md). The fields are confirmed by the AMI BIOS, but their effect on this board has not yet been measured.

The same research settled the RAM ceiling. The board has 8 slots of 30-pin SIMMs (2 banks), and the largest SIMM the chipset addresses is 4M×9, so 32 MB is the hardware limit.

## Rules and lessons

The rules the project kept:

- **Never move the IBM fixed entry points** (E05B, E6F2, EC59, F065, FA6E, FE6E, FFF0 and the rest). DOS-era software jumps to them directly.
- **Never change NCR's version or date.** Software reads 2.03.00 and 10/08/93; the Enhanced Edition version is shown beside them.
- **Every patch checks the bytes it replaces**, and every build starts from the untouched dump.
- **Fail soft.** A damaged E800 area switches the extension off; bad chipset settings are skipped on the next boot.
- **Use only CMOS bytes NCR leaves alone** (48h, 4Ah–5Fh), each block with its own check byte, so a dead battery can't feed garbage into a setting.
- **Code that runs after DOS starts lives in ROM**, not RAM that a memory manager may move. EMM386 must exclude E800–EFFF.

Bugs the emulator caught before a chip was burned:

- **One check of three.** POST skipped the disk init after lost settings in three places (F000:42A6, 4325 and 90C4). Patching only one did nothing.
- **A lost LBA value.** A stray `xor ah,ah` cleared part of the sector number before the end-of-disk check.
- **RAM that could move.** An early large-disk design kept its tables in a RAM block that EMM386 could relocate. They moved into the shadowed F000 BIOS (F000:EED6).
- **A clobbered vector.** The routines that unlock and lock the shadowed BIOS changed AX, which held part of the PicoMEM's saved INT 19h vector.
- **Offsets too big for a byte.** The chipset option table stored variable offsets of 100h or more in single bytes.
- **Only the first I/O base.** The PnP code saved a register after overwriting it, so only the first I/O range of a device was programmed.

Two problems showed up only on the real machine. The summary screen vanished after about a second, because a loop counter ran out before the timer ticks; it now times by the BIOS tick count. And the first boot order editor got stuck showing a dash; it was redesigned to always list all four devices.

## Reproducing the work

Install Python 3, NASM and the two libraries (`pip install -r requirements.txt`), then from the repository root:

```
python tools/disasm_bios.py                # regenerate out/system_bios_F000.lst
python tools/disasm_bios.py --module A400:0003:FA40 split/system_bios_F000.bin out/module_FA40.lst
python tools/build_rom.py --all            # assemble patches/src and build the improved ROM
python tests/run_all.py                    # build, then run all 393 checks
python tests/preview_screens.py            # render the screens to build/preview.html
python tools/apply_patch.py PATCH [IN] [OUT]   # apply one .patch file and fix checksums
```

To change something: edit the `.asm` in `patches/src/` (never the generated `.patch`), add a test, run the build and tests, bump `version.inc`, add a `CHANGELOG.md` entry and tag the commit.

| Folder | Contents |
| --- | --- |
| `patches/src/` | Patch sources (NASM) and `version.inc` |
| `patches/` | Generated `.patch` files |
| `tools/` | Disassembler, patch assembler and applier, ROM builder, checksum fixer, emulator |
| `tests/` | Emulator tests and the ISO and PnP card builders |
| `split/` | The VGA BIOS and system BIOS cut out of the image |
| `out/` | Disassembly listings of the system BIOS and Setup |
| `build/` | The improved ROM and the screen preview |
| `docs/` | BIOS notes, chipset register map, hardware notes |
| `userhdd/` | The USERHDD.EXE replacement (Free Pascal) |

The ROM image and everything derived from it contain NCR and Cirrus Logic firmware, kept for repairing and preserving these machines. The tools, patches and documentation are original work by StevenC & Claude.
