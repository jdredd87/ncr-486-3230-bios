# NCR 3230 BIOS

Reverse-engineering, fixes and tools for the system BIOS of the **NCR System 3230** (486, BIOS 517-0000672 v2.03.00, chip U19, dated 10/08/93).

- **`NCR-BIOS-517-0000672-VER2.03.00-U19.BIN`** is the original ROM dump. It is never modified.
- **`build/NCR3230-203-improved.BIN`** is the improved ROM, ready to program into a chip.
- **`userhdd/dos/userhdd.exe`** replaces NCR's lost USERHDD.EXE. With the improved ROM it is no longer needed: Tools has a Hard disk setup page.

## Improved ROM

| Patch | What it fixes |
|---|---|
| `no_burnin` | A certain keyboard failure no longer reboots into NCR's factory burn-in mode, where F1 does nothing |
| `error_prompts` | POST prompts continue on their own after a countdown: 5 s for errors such as "Disk controller failure", 3 s for battery and settings warnings. ENTER continues straight away, F1 opens Setup and Ctrl-D works as before. |
| `ide_nodrive_fast` | A drive type set with nothing connected: POST waits about 0.05 s instead of about 16 s |
| `ide_atapi_skip` | A CD-ROM where a drive type is set is skipped in about 1 s with a note, instead of about 32 s plus a phantom hard disk |
| `hdd_auto` | Hard disks work like a mid-90s BIOS. When the settings are lost (no battery), C: and D: default to **Automatic** instead of "Not installed", the defaults are saved with valid checksums, and the disk init is no longer skipped after a settings loss. A drive set to Automatic that isn't connected is skipped quietly, without "Disk controller failure", a countdown or a phantom drive. So with no battery, an IDE hard disk is simply found at every boot. |
| `setup_year` | Setup accepts two-digit years 00–79 as 2000–2079 |
| `fancy_boot` | A blue boot screen with a typed-in banner, the credits and a "Press <F1> for SETUP" hint. Errors print in red, warnings in yellow, and list items get bullets. Setup's F2 screen gains "Fancy Boot Screen" (F3 toggles it, stored in CMOS 48h). The credits also appear on Setup's title line. With the screen switched off, POST looks exactly as before. |
| `tools_rom` | **NCR 3230 Tools** in the chip's unused 32 KB (E800:0000). **F10** at the end of POST opens the Tools menu, which has six pages: system information (CPU and measured MHz, coprocessor, caches, memory, ports, video, clock), drives (IDE model names for disks and CD-ROMs), memory map with option ROMs, a memory test (conventional and all extended memory, five patterns), a CMOS viewer, and **Hard disk setup** (see below). It also runs NCR's built-in floppy drive test and offers a boot menu. **F8** goes straight to the boot menu, which boots A:, C: or the **CD-ROM** once (see below). With the fancy screen on, a start-up chime plays and a system summary shows for 3 s. "PROCESSOR SPEED" shows the measured clock. If the extension is missing or damaged (signature and checksum are checked), all of this switches itself off. |

Each patch is NASM source in `patches/src/` and checks the original bytes it replaces. They are tested by running the real ROM code in an emulator, original against improved (`python tests/run_all.py`, 233 checks). `python tests/preview_screens.py` renders the boot and Setup screens to `build/preview.html`.

**On the real machine (2026-10-03):** the first improved build POSTs and boots, and `ide_atapi_skip` is confirmed. With a CD-ROM attached and no hard disk, POST printed "Disk 0: CD-ROM (ATAPI) found - not a hard disk, skipped" and carried on. The countdown, boot screen, Setup option and Tools are tested only in the emulator so far.

**Is the Tools area reachable on your board?** The splash shows "F1 Setup  F8 Boot menu  F10 Tools" when the BIOS can read the extension at E8000, and only "Press <F1> for SETUP" when it can't. In that case the Tools features stay off; everything else works.

### Hard disk setup

For an IDE hard disk, nothing needs setting up: **Automatic** (type 2) asks the drive for its geometry at every boot, and it is now the default. The fixed drive types 4–47 are still in the ROM for old MFM/RLL-era drives and for software that reads the table, but you never need to pick one.

To change the settings, press **F10** at the end of POST and choose **7  Hard disk setup**. The page lists what is on the IDE cable (model, size and geometry). Then:

| Key | Does |
|---|---|
| C / D | Change drive C: or D:, cycling through Not installed, Automatic, User type, and the fixed type it had before (if any) |
| U | Type in a user geometry (cylinders, heads, sectors): what USERHDD.EXE was for |
| M | Copy the master drive's own geometry into the user type |
| S | Save to CMOS (types, the type-1 table and the checksums). Enter then restarts so POST uses the new settings. |

Use the user type only for a disk that must keep the geometry it was partitioned with on another PC. Without a CMOS battery the settings are lost at power-off and the page says so; Automatic still works then, because it is the default.

### Booting from CD-ROM

The stock BIOS predates the El Torito standard for bootable CDs. `tools_rom` adds it:

1. Put a bootable CD in the IDE CD-ROM drive (master or slave on the motherboard's IDE port).
2. At the end of POST press **F8**, then **3** (CD-ROM). The menu shows the drive's model name.
3. The BIOS waits for the disc to spin up (Esc cancels), reads the boot catalog and starts the disc.

| Boot image type | Typical discs | After booting |
|---|---|---|
| Floppy emulation (1.2, 1.44 or 2.88 MB) | DOS and Windows 95/98 boot CDs, most 1990s utility CDs | The image is A: and read-only. A real floppy drive becomes B:. |
| No emulation | ISOLINUX (Linux, FreeDOS 1.x), Windows 2000/XP | The CD is BIOS drive E0h, with the INT 13h extensions the loaders use. |
| Hard-disk emulation | rare | Not supported: the BIOS says so and boots normally. |

If anything fails (no drive, no disc, a data CD), it prints why and carries on with the normal boot order. The CD service takes 3 KB from the top of base memory (637 KB free), and its code runs from the ROM at E8000. With EMM386 add `X=E800-EFFF` so it doesn't map memory over it. A booted DOS still needs its own CD-ROM driver (such as OAKCDROM.SYS on a Windows 98 boot disc) to read the rest of the CD as a drive letter.

### Flashing

1. Read the original chip with your programmer. Its SHA-256 must be `f634b7b83cb80fe6f9a6ba17fb40eb79695cce652a6b99e1b5f72ad1b3098e03`. That proves this dump is exact.
2. Program the **original** image into the new chip first and check that it boots. That proves the chip type and programming.
3. Then program `build/NCR3230-203-improved.BIN`, keeping the original chip as a fallback. SHA-256: `a6c671379fb89f2ef64d8aa5ebe2d7bb6c16962ad41c15622937cac5068ede2f`.

The BIOS has no flash-writing code, so plan on an external programmer.

## USERHDD.EXE

With the improved ROM, Tools → Hard disk setup does this job, so you only need USERHDD with the original ROM.

Setup's disk type 1 ("parameter set by USERHDD.EXE") needed a utility that is lost. `userhdd/dos/userhdd.exe` does the same job. Run it from DOS on the NCR:

    USERHDD                 show the settings, then enter a geometry
    USERHDD 1024 16 63 /C   set the type-1 geometry and make C: type 1
    USERHDD /DETECT /C      read the geometry from the IDE drive (add /SLAVE for the slave)
    USERHDD /SHOW           show the settings only

It needs a working CMOS battery, because the geometry is stored in CMOS. For IDE drives, Setup's type 2 ("Automatic") often needs no utility at all.

## Working on it

Requirements:
- Python 3 with `pip install -r requirements.txt` (Capstone, Unicorn)
- [NASM](https://www.nasm.us/) to assemble patches
- Free Pascal with the i8086-msdos target to rebuild USERHDD

```
python tools/build_rom.py --all            # assemble patches/src and build the improved ROM
python tests/run_all.py                    # build, then run every test
python tests/hdinit.py [IMAGE.BIN]         # report: POST disk init with simulated drives
python tools/disasm_bios.py                # regenerate out/system_bios_F000.lst
python tools/disasm_bios.py --module A400:0003:FA40 split/system_bios_F000.bin out/module_FA40.lst
python tools/apply_patch.py PATCH [IN] [OUT]   # apply one .patch file, fix checksums
```

Build USERHDD from `userhdd/`:

    ppcross8086 -Tmsdos -WmSmall -Cp8086 -O2 -FEdos userhdd.pas     (DOS program)
    ppc386 -dSIMCMOS -O2 -FEsim userhdd.pas                          (Windows test build)

| Folder | Contents |
|---|---|
| `patches/src/` | Patch sources (NASM). `patches/*.patch` are generated from them. |
| `tools/` | Disassembler, patch assembler and applier, ROM builder, checksum fixer, emulator (`emu.py`, `dosemu.py`), `userhdd.py` (DEBUG-script fallback for USERHDD) |
| `tests/` | Emulator tests for the patches and USERHDD |
| `out/` | Disassembly listings of the system BIOS and the Setup module |
| `split/` | The VGA BIOS and system BIOS cut out of the image |
| `docs/` | [BIOS notes](docs/bios-notes.md) (memory map, POST, CMOS, disks, free space), [hardware notes](docs/hardware-notes.md) (L2 cache, P1 connector, CPU upgrades), and the P1 probe worksheet |

## Copyright

The ROM image, the images derived from it (`split/`, `build/`) and the disassembly listings (`out/`) contain NCR Corporation and Cirrus Logic firmware. They are kept here for personal repair and preservation of this machine; this repository is private. The tools, patches and documentation are original work.
