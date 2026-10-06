# NCR 3230 BIOS

Reverse-engineering, fixes and new features for the system BIOS of the **NCR System 3230** (486, BIOS 517-0000672 v2.03.00, chip U19, dated 10/08/93).

- **`NCR-BIOS-517-0000672-VER2.03.00-U19.BIN`** is the original ROM dump. It is never modified.
- **`build/NCR3230-203-improved.BIN`** is the improved ROM, **Enhanced Edition 1.4**, ready to program into a chip. See [CHANGELOG.md](CHANGELOG.md) for what each version contains.
- **`userhdd/dos/userhdd.exe`** replaces NCR's lost USERHDD.EXE. It is needed only with the original ROM.

## What the improved ROM does

**Booting and POST**
- Boots without a hard disk, without a CMOS battery, and with a CD-ROM attached. CD-ROMs are recognised and skipped instead of stalling POST for 30 s.
- Error prompts ("Press F1", "Press ENTER") continue on their own after a countdown.
- A blue boot screen with credits, coloured messages and a start-up chime. It can be switched off in Setup.
- An end-of-POST **system summary**: processor and measured clock, memory, caches, drives, ports and video. It shows for 8 s with a countdown; Space holds it.
- **F8 boot menu**: boot once from A:, C:, the **CD-ROM**, or an option ROM such as the PicoMEM.
- **Saved boot order**, as on later BIOSes: up to four devices (A:, C:, CD-ROM, option ROM), tried in order at every boot. Missing or unbootable devices are skipped.
- **F10 Tools**: system information, drives, memory map, memory test, CMOS viewer, NCR's floppy drive test, **Hard disk setup**, the boot menu, **chipset settings** (memory and bus timing) with a register viewer, and **Plug and Play cards**.
- **ISA Plug and Play**: PnP cards such as a Sound Blaster AWE64 are found and configured at boot, so DOS can use them without CTCM or ICU.

**Hard disks**
- **Automatic** by default: IDE disks are detected at every boot, even with no battery.
- An absent drive is skipped quietly, without an error.
- Disks **over 504 MB**: up to 8.4 GB for DOS and FDISK, and up to 128 GB through the INT 13h extensions.
- A geometry can be typed in from Tools, instead of with USERHDD.EXE.

**CD-ROM**
- Boots El Torito CDs: DOS and Windows 9x boot CDs (floppy emulation), and ISOLINUX/FreeDOS/Windows 2000-style discs (no emulation).

**On the real machine (2026-10-04).** The improved ROM POSTs and boots. The Tools area at E8000 is reachable, the summary works, and booting from CD-ROM works. Large-disk mode and Hard disk setup are tested only in the emulator so far.

### The patches

| Patch | What it does |
|---|---|
| `no_burnin` | A certain keyboard failure no longer reboots into NCR's factory burn-in mode, where F1 does nothing. |
| `error_prompts` | POST prompts continue after a countdown: 5 s for errors such as "Disk controller failure", 3 s for battery and settings warnings. ENTER continues at once, F1 opens Setup, Ctrl-D works as before. |
| `ide_nodrive_fast` | A drive type set with nothing connected: POST waits about 0.05 s instead of about 16 s. |
| `ide_atapi_skip` | A CD-ROM where a hard-disk type is set is skipped in about 1 s with a note, instead of about 32 s plus a phantom hard disk. |
| `hdd_auto` | After lost settings, C: and D: default to Automatic, and the defaults are saved with valid checksums. The disk init is no longer skipped after a settings loss. An Automatic drive that isn't connected is skipped without "Disk controller failure", a countdown or a phantom drive. |
| `setup_year` | Setup accepts two-digit years 00–79 as 2000–2079. |
| `fancy_boot` | The blue boot screen, coloured messages and credits. Setup's F2 screen gains "Fancy Boot Screen" (F3 toggles it, stored in CMOS 48h). With it off, POST looks exactly as before. |
| `tools_rom` | Everything in the chip's unused 32 KB (E800:0000): the Tools menu, boot menu, summary and chime, measured "PROCESSOR SPEED", CD-ROM boot, saved boot order, large-disk mode, option-ROM boot control. If that area is missing or damaged (signature and checksum are checked), all of it switches off and the rest still works. |

Each patch is NASM source in `patches/src/` that checks the original bytes it replaces. They are tested by running the real ROM code in an emulator, original against improved (`python tests/run_all.py`, 359 checks). `python tests/preview_screens.py` renders the boot, Setup and Tools screens to `build/preview.html`.

**Is the Tools area reachable on your board?** The boot screen shows "F1 Setup  F8 Boot menu  F10 Tools" when the BIOS can read E8000, and only "Press <F1> for SETUP" when it can't. In that case the Tools features stay off and everything else works.

## Using it

### Keys at the end of POST

| Key | Does |
|---|---|
| F1 | Setup, as before |
| F8 | Boot menu |
| F10 | Tools |
| Space | Holds the system summary on screen; the next key boots, or F1/F8/F10 act as above |

### Chipset settings (Tools → 9)

The board's chipset is the **UMC 82C480** (UM82C481, UM82C482, UM82C206). Its registers are decoded in [docs/chipset-umc480.md](docs/chipset-umc480.md). NCR set it up conservatively, and this page lets you change the timing:

| Setting | NCR's value | Choices |
|---|---|---|
| ISA bus clock | bus ÷ 5 (6.7 MHz) | ÷ 6, 5, 4 (8.3 MHz, the usual ISA speed), 3, 2, 8 |
| I/O recovery time | 2 bus clocks | 2, 4, 8, 12 |
| DRAM read wait states | 1 WS | 3, 2, 1, 0 |
| DRAM write wait states | 1 WS | 3, 1, 0 |
| L2 cache read burst | 3-1-1-1 | 3-1-1-1, 3-2-2-2, 2-1-1-1 |
| L2 cache write wait states | 1 WS | 1, 2, 0 (later chip revisions) |

Each row shows the saved setting beside what is in the chip now. ↑↓ select, ←→ change, S saves, D goes back to NCR's values, and R shows all the registers (80h–9Fh, with the known bits named).

Saved settings are applied at the end of every POST, so restart after saving, then check them with the memory test (Tools 4). They need a CMOS battery.

**If a setting is too fast for the RAM, the machine can't lock you out:**
- **Automatic fail-safe:** if a boot with new settings never gets to booting or to Tools, the next boot skips them and Tools says so. They stay off until you save them again.
- **Manual skip:** holding **Shift** while POST finishes skips them for that boot.

### Plug and Play cards (Tools → P)

The 1993 BIOS predates Plug and Play, so ISA PnP cards (Sound Blaster AWE32/AWE64/SB16 PnP, PnP network and modem cards) used to come up switched off, and DOS needed Creative's CTCM or Intel's ICU to use them. Now, at the end of POST, the BIOS:

1. finds the cards (the PnP ISA 1.0a isolation protocol), up to four of them;
2. reads what each part of a card can use;
3. gives each part an I/O address, IRQ and DMA channel that don't clash with the motherboard (serial and parallel ports, floppy, IDE, video, PS/2 mouse) or with anything you've set aside;
4. switches them on.

An AWE64 comes up as A220 I5 D1 H5 P330 E620, and the page shows the matching `SET BLASTER=` line for AUTOEXEC.BAT. Windows 95/98 and CTCM can still reconfigure the cards afterwards.

| Key | Does |
|---|---|
| C | Configure at boot on/off |
| I / M | Keep an IRQ / DMA channel free for a non-PnP card (type the number; typing it again frees it) |
| 1 / 2 | Keep an I/O range free (base and length in hex), e.g. for a PicoMEM or a jumpered network card |
| S | Save (CMOS 54h–5Fh) |
| R | Configure the cards again now, with these settings |

Holding Shift while POST finishes skips it once.

### Boot menu (F8)

| Key | Boots once from |
|---|---|
| 1 | Floppy disk A: |
| 2 | Hard disk C: |
| 3 | CD-ROM (the drive's name is shown) |
| 4 | The option ROM's own boot, when a card such as the PicoMEM hooked the boot (its name is shown) |
| O | Opens the **boot order** editor (see below) |
| Esc | Normal boot order |

A choice from 1–4 applies to this boot only. If it fails, the saved boot order follows.

### Boot order (F8, then O)

All four devices are always listed, each once: Floppy A:, Hard disk C:, CD-ROM and Option ROM boot. Each is **on** or **off**. At every boot the ones that are on are tried from the top:

- **Floppy A: and hard disk C:** boot if a boot sector can be read. A hard disk also needs the 55AAh signature.
- **CD-ROM:** a bootable disc boots. With no disc, it gives up after about 2 s. A disc still spinning up is waited for, and Esc skips it.
- **Option ROM boot:** the card's own boot, for example the PicoMEM's. When the card hands back to the BIOS, the next place is tried.
- **When everything fails**, the stock boot takes over, with its "insert system disk" prompt.

| Key | Does |
|---|---|
| ↑ ↓ | Select a device |
| + / − (or PgUp / PgDn) | Move the selected device up or down. The selection moves with it. |
| Space or Enter | Turn the selected device on or off (off: listed, but skipped at boot) |
| S | Save (CMOS 4Ah–4Dh, with a check byte) |
| D | Back to the BIOS default |
| Esc | Leave without saving ("Not saved yet" shows while there are changes) |

Until an order is saved, the **BIOS default** applies: an option ROM's own boot first (if a card hooked the boot), then A: and C: as Setup sets them. The order needs a working CMOS battery. Without one it is lost at power-off, and the default applies. The system summary shows the order in use.

### Cards that take over booting (PicoMEM)

Option ROMs such as the PicoMEM's hook the boot (INT 19h) and boot their own way: from their disk images, or straight to the BIOS order. Normally the BIOS would get no say. Now, at the end of POST, the BIOS takes the boot hook back and keeps the card's handler, so:

- **By default nothing changes.** The card's boot runs first, as it is configured. When it falls back to the BIOS (for example with PicoMEM boot switched off in its menu), the BIOS boot order follows.
- **A boot-menu choice always wins.** F8 then 3 boots the CD-ROM, and F8 then 2 boots C:, even with the card installed.
- **A saved boot order** puts the card's boot exactly where you want it, or leaves it out (for example "CD-ROM, Hard disk C:"). F8 then 4 still runs it once.

Notes:
- The PicoMEM normally does its own setup when its ROM starts ("pre-boot", its default), so skipping its boot loses nothing. If its pre-boot setup is turned off, it sets itself up only during its own boot, so choose 4, or the option-ROM-first order, to have it.
- A PicoMEM that emulates a hard disk takes the C: number for its disk image, so "C:" may mean the image rather than the internal disk.

### Hard disk setup (Tools → 7)

For an IDE hard disk, nothing needs setting up: **Automatic** asks the drive for its geometry at every boot, and it is the default. The fixed drive types 4–47 are still in the ROM for MFM/RLL-era drives and for software that reads the table, but you never need to pick one.

The page lists what is on the IDE cable (model, size, geometry, LBA mode). Then:

| Key | Does |
|---|---|
| C / D | Change drive C: or D:: Not installed, Automatic, User type, or the fixed type it had before (if any) |
| U | Type in a user geometry (cylinders, heads, sectors), which is what USERHDD.EXE was for |
| M | Copy the master drive's own geometry into the user type |
| S | Save to CMOS: types, the type-1 table and the checksums. Enter then restarts so POST uses the new settings. |

Use the user type only for a disk that must keep the geometry it was partitioned with elsewhere. Without a CMOS battery the settings are lost at power-off, and the page says so. Automatic still works then, because it is the default.

### Disks over 504 MB

The stock BIOS addresses disks by cylinder/head/sector exactly as the drive does, which ends at 1024/16/63 = 504 MB. Now a disk set to **Automatic** that holds more and supports LBA gets large-disk mode, the way a 1995 Phoenix or Award BIOS does it. That covers every IDE disk from about 1994 on, and CompactFlash cards.

- **Up to 8.4 GB for DOS and FDISK.** The disk shows the standard "LBA-assisted" geometry (32, 64, 128 or 255 heads, 63 sectors, up to 1024 cylinders). A 2 GB disk appears as 1023/64/63.
- **The whole disk, up to 128 GB,** through the INT 13h extensions (41h–48h). Windows 95 OSR2/98, MS-DOS 7.1 and FAT32 use these. A bigger disk works, but only its first 128 GB is reachable.
- **Translated parameter tables** behind INT 41h/46h (A0h signature) for software that reads them.

Tools → Drives marks such a disk "LBA". Smaller disks, disks without LBA, and drives with a fixed or user type stay on the stock code. No base memory is used: the tables sit in the shadowed BIOS segment, as the stock auto-detect's do.

**A disk partitioned with the old 504 MB limit** keeps that layout if you set it to the user type 1024/16/63. Switching an existing disk between the two layouts makes its partitions unreadable until you switch back, as on any BIOS.

### Booting from CD-ROM

1. Put a bootable CD in the IDE CD-ROM drive (master or slave on the motherboard's IDE port).
2. At the end of POST press **F8**, then **3**.
3. The BIOS waits for the disc to spin up (Esc cancels), reads the boot catalog and starts the disc.

| Boot image type | Typical discs | After booting |
|---|---|---|
| Floppy emulation (1.2, 1.44 or 2.88 MB) | DOS and Windows 95/98 boot CDs, most 1990s utility CDs | The image is A: and read-only. A real floppy drive becomes B:. |
| No emulation | ISOLINUX (Linux, FreeDOS 1.x), Windows 2000/XP | The CD is BIOS drive E0h, with the INT 13h extensions the loaders use. |
| Hard-disk emulation | rare | Not supported: the BIOS says so and boots normally. |

If anything fails (no drive, no disc, a data CD), the BIOS prints why and carries on with the normal boot order. The CD service takes 3 KB from the top of base memory (637 KB free), and its code runs from the ROM at E8000.

DOS still needs its own CD-ROM driver (for example OAKCDROM.SYS and MSCDEX) to read the CD as a drive letter.

### EMM386 and other memory managers

The ROM area E8000–EFFFF holds code that runs after boot: large-disk mode and the CD service. Exclude it so no upper memory is mapped over it, for example `DEVICE=EMM386.EXE X=E800-EFFF`.

## Flashing

1. Read the original chip with your programmer. Its SHA-256 must be `f634b7b83cb80fe6f9a6ba17fb40eb79695cce652a6b99e1b5f72ad1b3098e03`. That proves this dump is exact.
2. Program the **original** image into the new chip first and check that it boots. That proves the chip type and programming.
3. Then program `build/NCR3230-203-improved.BIN`, keeping the original chip as a fallback. SHA-256: `db301855e3a9424054c901a82964d6a1e2062d4104dc8bce7b215fca36af2b09`.

The BIOS has no flash-writing code, so plan on an external programmer.

### Which version is in the chip?

The version shows on the boot screen ("Enhanced Edition 1.4"), in the end-of-POST summary, on Setup's title line, and in Tools → System information, with its release date. To make a new version, change `patches/src/version.inc`, add an entry to [CHANGELOG.md](CHANGELOG.md), rebuild, and tag the commit (`git tag v1.1`). The build prints the version with the SHA-256. The NCR BIOS's own version (2.03.00) and date (10/08/93) stay as they are, because DOS-era software reads them.

## USERHDD.EXE

With the improved ROM, Tools → Hard disk setup does this job; USERHDD is for the original ROM. Setup's disk type 1 ("parameter set by USERHDD.EXE") needs a utility that is lost, and `userhdd/dos/userhdd.exe` does the same job. Run it from DOS on the NCR:

    USERHDD                 show the settings, then enter a geometry
    USERHDD 1024 16 63 /C   set the type-1 geometry and make C: type 1
    USERHDD /DETECT /C      read the geometry from the IDE drive (add /SLAVE for the slave)
    USERHDD /SHOW           show the settings only

It needs a working CMOS battery, because the geometry is stored in CMOS.

## Working on it

Requirements:
- Python 3 with `pip install -r requirements.txt` (Capstone, Unicorn)
- [NASM](https://www.nasm.us/) to assemble patches
- Free Pascal with the i8086-msdos target to rebuild USERHDD

```
python tools/build_rom.py --all            # assemble patches/src and build the improved ROM
python tests/run_all.py                    # build, then run every test
python tests/preview_screens.py            # render the screens to build/preview.html
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
| `patches/src/` | Patch sources (NASM). `patches/*.patch` are generated from them. `version.inc` holds the Enhanced Edition version. |
| `tools/` | Disassembler, patch assembler and applier, ROM builder, checksum fixer, emulator (`emu.py`: CPU, CMOS, IDE disks, ATAPI CD-ROM with ISO images, video; `dosemu.py`), `userhdd.py` (DEBUG-script fallback for USERHDD) |
| `tests/` | Emulator tests: `test_patches` (POST fixes), `test_fancy` (boot screen, Setup option), `test_tools` (Tools, summary, boot menu, option ROMs), `test_cdboot` (El Torito ISOs built on the fly by `isotools.py`), `test_bootorder`, `test_hdsetup`, `test_lba` (2 GB and 34 GB disks), `test_userhdd*` |
| `out/` | Disassembly listings of the system BIOS and the Setup module |
| `split/` | The VGA BIOS and system BIOS cut out of the image |
| `docs/` | [BIOS notes](docs/bios-notes.md) (memory map, POST, CMOS, disks, everything the patches add), [hardware notes](docs/hardware-notes.md) (L2 cache, P1 connector, CPU upgrades), and the P1 probe worksheet |

## Copyright

The ROM image, the images derived from it (`split/`, `build/`) and the disassembly listings (`out/`) contain NCR Corporation and Cirrus Logic firmware. They are included for the repair and preservation of these machines, and remain the property of their owners. The tools, patches and documentation are original work by StevenC & Claude.
