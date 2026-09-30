# NCR 3230 BIOS

Reverse-engineering, fixes and tools for the system BIOS of the **NCR System 3230** (486, BIOS 517-0000672 v2.03.00, chip U19, dated 10/08/93).

- **`NCR-BIOS-517-0000672-VER2.03.00-U19.BIN`** is the original ROM dump. It is never modified.
- **`build/NCR3230-203-improved.BIN`** is the improved ROM, ready to program into a chip.
- **`userhdd/dos/userhdd.exe`** replaces NCR's lost USERHDD.EXE.

## Improved ROM

| Patch | What it fixes |
|---|---|
| `no_burnin` | A certain keyboard failure no longer reboots into NCR's factory burn-in mode, where F1 does nothing |
| `battery_prompt` | "Battery Power Lost" style prompts continue after about 3 s instead of waiting forever. F1 still enters Setup. |
| `ide_nodrive_fast` | A drive type set with nothing connected: POST waits about 0.05 s instead of about 16 s |
| `ide_atapi_skip` | A CD-ROM where a drive type is set is skipped in about 1 s with a note, instead of about 32 s plus a phantom hard disk |
| `setup_year` | Setup accepts two-digit years 00–79 as 2000–2079 |

Each patch is NASM source in `patches/src/` and checks the original bytes it replaces. They are tested by running the real ROM code in an emulator, original against improved. **None of this has run on the real board yet.**

### Flashing

1. Read the original chip with your programmer. Its SHA-256 must be `f634b7b83cb80fe6f9a6ba17fb40eb79695cce652a6b99e1b5f72ad1b3098e03`. That proves this dump is exact.
2. Program the **original** image into the new chip first and check that it boots. That proves the chip type and programming.
3. Then program `build/NCR3230-203-improved.BIN`, keeping the original chip as a fallback. SHA-256: `8500f9736530436586f6a667cc7a396a495d8e8c133680a69b1433b4443004bf`.

The BIOS has no flash-writing code, so plan on an external programmer.

## USERHDD.EXE

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
