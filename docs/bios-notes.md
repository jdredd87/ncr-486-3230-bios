# NCR 3230 BIOS notes

Technical findings from the disassembly of BIOS 517-0000672 v2.03.00 (U19, dated 10/08/93). Addresses are `segment:offset` as the CPU sees them. Everything here comes from reading and emulating the ROM code; nothing has been confirmed on the real board unless stated.

## Image layout (128 KB)

| Image offset | Runs at   | Contents |
|--------------|-----------|----------|
| 00000–07FFF  | E000:0000 | Cirrus Logic CL-GD5422/24/26/28 VGA BIOS v1.30 (`55 AA 40`, 32 KB). Checksum byte at 07FFF. |
| 08000–0FFFF  | E800:0000 | Unused, all FFh (32 KB). |
| 10000–1FFFF  | F000:0000 | NCR system BIOS, 64 KB. 8-bit sum = 00h; correction byte at F000:FFFF. |

Inside the F000 segment:

| F000 range | Contents |
|------------|----------|
| 0000–A3FF  | POST, burn-in and diskette diagnostics, INT 13h fixed disk (entry 94E3), keyboard (INT 16h/09h), INT 15h, message text |
| A400–DFFF  | **Setup module.** It has a `55 AA 00` header, is assembled ORG 0 and runs as **FA40:xxxx**. It is entered by `call far FA40:0003` at F000:47F9, and its data segment is RAM 0070:0000. Title: "Setup, Version 2.01.00 (3230)". |
| E000–FFFF  | IBM PC/AT fixed entry points (E05B POST, EC59 INT 13h diskette, F065 INT 10h, FE6E INT 1Ah, …), 8×8 font at FA6E, vector tables at FEF3/FF23, reset vector FFF0, date "10/08/93", model byte FCh |

## Chipset

- **Configuration ports.** The chipset is configured through **index port 22h, data port 24h**, using registers 80h–9Fh. It is not yet identified. It is not OPTi's 82C493, which uses the same ports with registers 20h–2Bh.
- **Init table.** POST programs 16 registers (81h–9Fh) from a table at F000:2225: a count word followed by (index, data) pairs.
- **Known registers:**
  - 92h = L2 cache enable (see [hardware-notes.md](hardware-notes.md))
  - 93h = L2 cache size
  - 9Bh bit 0 = write-protect of the shadowed F000 BIOS. POST clears it while writing the drive table.

## POST

- **POST codes** go to port 80h, and most are also echoed to the LPT1 data port (378h), so a parallel-port LED card works as a POST card.
- **ROM-stack calls.** Before RAM is tested, POST calls subroutines with `mov sp, X` / `jmp`; each subroutine's `ret` pops a continuation address stored at X.
- **Shutdown table.** The CMOS shutdown-code dispatch table is at F000:4890. Its last entries double as code (`in al,60h; out 0EBh,al`).
- **Option-ROM scan** (POST code 74h, F000:4540). It covers C000–DFFF. When CMOS 40h bit 0 is set (apparently "Copy Video to C0000") it covers C800–EFFF instead, which includes the unused E8000 area. That could hold an extra option ROM. **Untested on hardware.**
- **Setup entry.** Setup is reachable in only two places, both after the hard-disk init:
  - the error prompt at F000:478A (F1 or Enter);
  - F1 already in the keyboard buffer when POST checks it at F000:47C5.

### CMOS and the battery

- **Validity checks** at F000:2081:
  - RTC register D (VRT, battery valid);
  - the standard checksum at 2Eh/2Fh over 10h–2Dh;
  - the NCR checksum at 7Eh/7Fh over 44h–47h.
- **Defaults.** If any check fails, F000:217F loads defaults:
  - 10h–47h are cleared;
  - base memory = 640 KB;
  - A: = 1.44 MB (10h = 40h);
  - no hard disks;
  - 44h = E5h, 47h = 4Eh (bit 6 = boot from floppy).
- **RTC setup.** RTC register B is sanitized at F000:2258 and register A is set to 26h at F000:2BBA. The time-of-day conversion (F000:8192) range-checks every field. A battery-less boot is safe, but the stock BIOS stops at "Battery Power Lost … Press <F1> or <ENTER>". The `error_prompts` patch makes that prompt, and the "Press <ENTER> to continue" prompt for other errors, count down and continue.
- **CMOS 48h** is unused by the stock BIOS (POST's defaults clear only 10h–47h). The `fancy_boot` patch uses it as the boot-screen switch: A5h means off, and anything else means on. Setup's F2 screen toggles it with F3.
- **Date.** INT 1Ah AH=04h/05h use the century byte (32h), so there is no Y2K bug there. Setup accepts years 1980–2099 with correct leap years. Unpatched, two-digit years 00–79 are rejected (the `setup_year` patch fixes that).
- **CPU speed.** "PROCESSOR SPEED: xx MHz" prints CMOS 43h, which neither POST nor Setup writes.

### Burn-in trap

If the keyboard interface test returns code 3 and the keyboard clock/data lines don't read idle-high (F000:3E85), POST zeroes 40:12. At F000:474C a zero sets 40:72 = 5678h and reboots into NCR's factory burn-in mode, where F1 does nothing. The `no_burnin` patch removes this.

## Hard disks

- **INT 13h handler.** The fixed-disk handler is at F000:94E3, installed at F000:907B. It supports functions **00h–15h only**: no INT 13h extensions, no LBA, CHS only, which means about **504 MB**.
- **Drive types.** CMOS 12h holds C (high nibble) and D (low nibble); F means an extended type in 19h/1Ah. Types index the table at F000:E401, 16 bytes each.
  - **0 = not installed.** POST skips the hard-disk init entirely (F000:90D9).
  - **1 = user-defined.** The geometry is in CMOS 72h–7Bh with a checksum in 7Ch, copied into the table at POST (F000:3C58). Setup refuses type 1 unless that checksum is valid (FA40:1227). `userhdd/userhdd.exe` writes it.
  - **2 = automatic.** POST sends IDENTIFY and writes the geometry into slot 2 (E411). For D:, Setup stores "2" as 3, which uses slot 3 (E421). Drives over 1024/16/63 are fitted down to at most 1024/16/63 (F000:92D3).
  - **4–47 = fixed types.** Useful ones: 33 = 1024/16/63 (504 MB), 24 = 702/16/63.
- **Why POST can appear to hang.** All IDE waits are loop-count timeouts, but some are long. After a reset, POST retries INT 13h AH=10h ("drive ready") up to 31,000 times with about 1 ms between tries (F000:9150). Measured in the emulator (`tests/hdinit.py`):
  - a CD-ROM where a drive type is set takes about 32 s and still counts as a hard disk;
  - a drive type set with nothing connected takes about 16 s.

  The `ide_atapi_skip` and `ide_nodrive_fast` patches fix both.
- **Boot order** (INT 19h, F000:E169). If CMOS 47h bit 6 ("Boot from Flex Disk") is set, POST tries A: then C:. With nothing bootable it shows "DISK ERROR, INSERT SYSTEM DISK" and retries after a key press. There is no CD-ROM boot; the BIOS predates El Torito.

## Free space for patches

Zero-filled areas in the F000 segment:

| F000 range | Bytes | Notes |
|------------|------:|-------|
| 9ED3–A3FF  | 1325  | Used: 9F30–9F5A `ide_nodrive_fast`, A000–A109 `ide_atapi_skip`, A140–A203 `error_prompts`, A240–A2D6 and A300–A3F7 `fancy_boot`. Still free: 9ED3–9F2F, 9F5B–9FFF, A10A–A13F, A204–A23F, A2D7–A2FF. |
| EC5C–EF56  | 763   | Between fixed entry points (keep EF57). Used: EC60–EDF9 `fancy_boot`. Still free: EDFA–EF56. |
| F85C–FA6D  | 530   | Before the font (keep FA6E) |
| E831–E986  | 342   | Keep E987 |
| F738–F840  | 265   | Keep F841 |
| E73C–E82D  | 242   | Keep E82E |
| DF71–DFFF  | 143   | Inside the Setup module (FA40:3B71–3BFF). Used: FA40:3B71–3B90 and 3BA0–3BED `fancy_boot`. |
| 0006–00A5  | 160   | Purpose not confirmed; avoid |

Never move the IBM fixed entry points (E05B, E2C3, E6F2, E739, E82E, E987, EC59, EF57, EFC7, EFD2, F065, F0A4, F841, F84D, F859, FA6E, FE6E, FEA5, FEF3, FF23, FF53, FF54, FFF0). DOS-era software jumps to them directly.

## The disassembler

`tools/disasm_bios.py` is a recursive-descent disassembler built on Capstone. It follows:
- the reset vector and the fixed entry points;
- the ROM vector tables and the ISRs installed into the vector table;
- ROM-stack calls;
- table dispatch (table size from `cmp` limits or count words);
- far calls;
- inline-argument calls (for example FA40:1A90, which prints the string whose offset follows the call, relative to 20B0h).

Labels `*_handler`, `isr_*` and `romret_*` come from certain evidence. `ptr_*` labels come from a heuristic pointer-table scan and are *probably* code. Unreached bytes appear as `db` or strings.

## Patch file format

```
F000:9EE0  00 00 00  ->  B8 34 12     ; system BIOS address
FA40:3A99  33 32 33 30 -> 4D 4F 44 31 ; Setup-module address
IMG:1FFA0  4E  ->  6E                 ; raw image offset
```

The bytes left of `->` must match the image, or nothing is written. The files in `patches/*.patch` are generated from `patches/src/*.asm` by `tools/asm2patch.py`, so edit the `.asm`, not the `.patch`. `patches/examples/setup_title_demo.patch` is a hand-written example that changes the Setup title "(3230)" to "(MOD1)".
