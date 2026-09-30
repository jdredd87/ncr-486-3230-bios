# NCR 486 BIOS 517-0000672 v2.03.00 (U19): reverse-engineering workspace

The original image `NCR-BIOS-517-0000672-VER2.03.00-U19.BIN` is never modified.
Every build goes to `build/`.

## Image layout (128 KB)

| Image offset  | Runs at         | Contents |
|---------------|-----------------|----------|
| 00000-07FFF   | E000:0000       | Cirrus Logic CL-GD5422/24/26/28 VGA BIOS v1.30 (`55 AA 40`, 32 KB). Checksum byte at 07FFF. |
| 08000-0FFFF   | E800:0000       | **Unused**, all FFh (32 KB). |
| 10000-1FFFF   | F000:0000       | NCR system BIOS, 64 KB. 8-bit sum = 00h, correction byte at F000:FFFF (6Ah). |

Inside the F000 segment:

| F000 range  | What |
|-------------|------|
| 0000-A3FF   | POST, burn-in and diskette diagnostics, INT 13h fixed disk (entry 94E3), INT 16h/09h keyboard, INT 15h, message text |
| A400-DFFF   | **Setup module.** `55 AA 00` header, assembled ORG 0, runs as **FA40:xxxx** (entered by `call far FA40:0003` at F000:47F9). Its data segment is RAM 0070:0000. Title string: "Setup, Version 2.01.00 (3230)". |
| E000-FFFF   | IBM PC/AT-compatible fixed entry points (E05B POST, EC59 INT13 FD, F065 INT10, FE6E INT1A, …), 8x8 font at FA6E, vector table at FEF3/FF23, reset vector FFF0, date "10/08/93", model byte FCh |

## Findings so far

* **Chipset init.** A table at F000:2225 holds a count followed by 16 (index, data) pairs, written to I/O ports **22h / 24h** (registers 81h–9Fh). That fits an OPTi-style 486 chipset, but it is unconfirmed until checked against the chip markings on the board.
* **Hard disk.** The INT 13h fixed-disk handler (F000:94E3) supports functions **00h–15h only**. It has no INT 13h extensions (41h–48h) and no LBA, so drives are limited to CHS, about **504 MB**. Setup does offer "Automatic disk parameter detection" (type 2) and user-defined type 1 (via USERHDD.EXE).
* **Option-ROM scan.** At POST code 74h (F000:4540), the scan covers C000–DFFF. When CMOS 40h bit 0 is set (apparently "Copy Video to C0000"), it covers **C800–EFFF** instead, which includes the unused E8000 area. That could host an extra option ROM (for example an LBA/large-disk BIOS extension). **This needs testing on hardware.**
* **POST codes** go to port 80h, and most are also echoed to the LPT1 data port (378h). A parallel-port LED card works as a POST card.
* The CMOS shutdown-code dispatch table is at F000:4890. Its last entries double as code (`in al,60h; out 0EBh,al`).

## Hard disk, Setup and boot findings

**Drive types (CMOS 12h: high nibble = C, low nibble = D; F = extended type in CMOS 19h/1Ah).**
Types index the table at F000:E401 (16 bytes each).
* **0**: not installed. POST skips hard-disk init completely (F000:90D9).
* **1**: user-defined. Geometry lives in **CMOS 72h–7Ch** and is copied into the table at POST (F000:3C58). `tools/userhdd.py` recreates the lost USERHDD.EXE (it writes a DOS `DEBUG` script).
* **2**: automatic. POST sends IDENTIFY (ECh) and writes C's geometry into slot 2 (E411). For drive D, Setup stores "2" as 3, which uses slot 3 (E421). Cylinders are copied raw, not clamped to 1024.
* **4–47**: fixed types. Useful ones: **33 = 1024/16/63 (504 MB)**, 24 = 702/16/63.

**Why POST can seem to hang.** All IDE waits are loop-count timeouts, but some are long. After reset, POST calls INT 13h AH=10h ("drive ready") up to 31,000 times with a delay each time (F000:9150). An ATAPI CD-ROM, or an empty IDE port, sitting where a drive type is configured never reports ready, so POST can sit there for minutes. Setup/F1 is only reachable *after* this point (F000:478A error prompt, or F1 in the keyboard buffer at F000:47C5).

**Burn-in trap.** If the keyboard interface test fails with code 3 and the clock/data lines aren't idle-high (F000:3E85), POST zeroes 40:12. Then at F000:474C it sets 40:72 = 5678h and reboots into factory burn-in mode. `patches/no_burnin.patch` removes this.

**Boot (INT 19h at F000:E169).** If CMOS 47h bit 6 ("Boot from Flex Disk") is set, POST tries A: first, then C:. With no bootable disk it shows "DISK ERROR, INSERT SYSTEM DISK" and retries after a key press. Booting from floppy with no hard disk is supported. There is **no CD-ROM boot** (the BIOS predates El Torito); a CD-ROM is used from DOS with a driver.

**No CMOS battery.** At F000:2081 POST checks RTC register D (VRT), the checksum at CMOS 2Eh/2Fh over 10h–2Dh, and the NCR checksum at 7Eh/7Fh over 44h–47h. If any check fails, F000:217F loads defaults: 10h–47h are cleared, then base memory is 640 KB, A: = 1.44 MB (10h = 40h), no hard disks, 44h = E5h and 47h = 4Eh (bit 6 = boot from floppy). RTC register B is sanitized at F000:2258 and register A is set to 26h at F000:2BBA. Time-of-day conversion (F000:8192) range-checks every field. So a battery-less boot is safe, but it always stops at "Battery Power Lost … Press <F1> or <ENTER>".

`patches/no_battery_no_hdd.patch` = no_burnin + a timed prompt: new routine at F000:9F00 (beep, wait ≤ 3 s or keypress, continue). F1 still enters Setup via the type-ahead check at F000:47C5. Prompts for other errors are unchanged.

## Free space for patches (zero-filled)

(F000:9F00–9F23 is now used by no_battery_no_hdd.patch.)


| F000 range   | Bytes | Notes |
|--------------|------:|-------|
| 9ED3-A3FF    | 1325  | Largest block, just before the Setup module |
| EC5C-EF56    | 763   | Padding between fixed entry points (keep EF57 intact) |
| F85C-FA6D    | 530   | Padding before the font (keep FA6E intact) |
| E831-E986    | 342   | Keep E987 intact |
| F738-F840    | 265   | Keep F841 intact |
| E73C-E82D    | 242   | Keep E82E intact |
| DF71-DFFF    | 143   | Inside the Setup module (FA40:3B71-3BFF) |
| 0006-00A5    | 160   | Purpose not yet confirmed; avoid for now |

Never move the IBM fixed entry points (E05B, E2C3, E6F2, E739, E82E, E987, EC59, EF57, EFC7, EFD2, F065, F0A4, F841, F84D, F859, FA6E, FE6E, FEA5, FEF3, FF23, FF53, FF54, FFF0). DOS-era software jumps to them directly.

## Tools

```
python tools/disasm_bios.py                  # -> out/system_bios_F000.lst
python tools/disasm_bios.py --module A400:0003:FA40 split/system_bios_F000.bin out/module_FA40.lst
python tools/apply_patch.py patches/NAME.patch   # -> build/NAME.BIN, checksums fixed
python tools/fix_checksum.py IMAGE.BIN [OUT.BIN]
```

`disasm_bios.py` is a recursive-descent disassembler built on Capstone. It follows the reset vector, the fixed entry points, the ROM vector tables and ISRs installed into the vector table. It also handles:

* ROM-stack calls: `mov sp, X` / `jmp`, which POST uses before RAM exists.
* Table dispatch, with the table size taken from `cmp` limits or count words.
* Far calls.
* Inline-argument calls. `FA40:1A90` is a print routine that takes a string offset in the 2 bytes after the call, relative to base 20B0h; the listing resolves these to their text.

Labels ending in `_handler` or `isr_` and `romret_` come from certain evidence. `ptr_` labels come from a heuristic pointer-table scan and are *probably* code. Bytes not reached are shown as `db` or strings.

Coverage: about 72% of the non-Setup code/data area is decoded as code in the main listing, and the rest is mostly text, tables and fonts. About half of the Setup module is decoded as code, and the rest is its screen text.

### Patch format

```
F000:9EE0  00 00 00  ->  B8 34 12     ; system BIOS address
FA40:3A99  33 32 33 30 -> 4D 4F 44 31 ; Setup-module address
IMG:1FFA0  4E  ->  6E                 ; raw image offset
```

The original bytes must match, or nothing is written. `patches/example_setup_title.patch` is a tested, harmless example that changes the Setup title "(3230)" to "(MOD1)".

## Before flashing anything

Keep the original chip, or a verified dump of it, and have a way to reprogram it (an EPROM/flash programmer). A bad BIOS will not POST. Test cosmetic patches first.

## Copyright

The ROM image, the images derived from it (`split/`, `build/`) and the disassembly listings (`out/`) contain NCR Corporation and Cirrus Logic firmware. They are kept here for personal repair and preservation of this machine; this repository is private. The tools and patch files are original work.
