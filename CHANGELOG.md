# Changelog

Versions of the NCR 3230 BIOS **Enhanced Edition**. The NCR BIOS underneath stays 517-0000672 v2.03.00 (10/08/93).

The version is set in one place, `patches/src/version.inc`. It shows on the boot screen, the end-of-POST summary, Setup's title line and Tools → System information. Bump it for every build that gets burned, add an entry here, and tag the commit (`v1.0`, `v1.1`, …).

## 1.3 (2026-10-05)

- The chipset is identified: **UMC 82C480** (UM82C481BF, UM82C482AF, UM82C206F; SMC FDC37C661 for the I/O ports). Its registers are decoded from an AMI BIOS for another UMC 480 board; see [docs/chipset-umc480.md](docs/chipset-umc480.md).
- New: Tools → 9 **Chipset settings**: ISA bus clock, I/O recovery time, DRAM read and write wait states, L2 cache read burst and write wait states. They are saved in CMOS 4Eh–51h and applied at the end of POST. NCR's values stay unless you change them.
- Fail-safe: a boot with new settings that never reaches booting or Tools makes the next boot skip them (CMOS 52h). Shift held at the end of POST skips them once.
- The register viewer moved under the settings page (R) and now names the bits. The summary shows the chipset timing state.

## 1.2 (2026-10-05)

- New: Tools → 9 **Chipset registers**. A read-only view of the chipset's registers 80h–9Fh, in hex and binary, beside the value POST's table writes to each one. Registers that differ are yellow, and the known ones are labelled (L2 cache, shadow). Setup's option bytes, CMOS 44h–47h, are shown too, and R reads everything again. It is for identifying the chipset and finding what each Setup option changes: photograph it, change an option, reboot, and compare.
- The Tools menu's "Continue booting" moved to key 0. Esc still works the same. Items 1–8 are unchanged.

## 1.1 (2026-10-05)

- Fix: "INTERRUPT CONTROLLERS" in the POST test list showed in red, as if it were an error. The colouring matched "rr" anywhere. It now looks for "rro" ("Error", "ERROR") or "ilu"/"ILU" ("failure"), so test names such as INTERRUPT stay grey. The two "** … not Correct" messages now show as yellow warnings, like the other "**" messages.

## 1.0 (2026-10-05)

The first numbered release. It covers everything built so far.

**POST and booting**
- Boots without a hard disk, without a CMOS battery, and with a CD-ROM attached (`ide_nodrive_fast`, `ide_atapi_skip`). A certain keyboard failure no longer drops into NCR's factory burn-in mode (`no_burnin`).
- Error prompts continue after a countdown (`error_prompts`).
- Blue boot screen, coloured messages, credits and a start-up chime. Setup's F2 screen can switch the screen off (`fancy_boot`).
- System summary at the end of POST, shown for 8 s with a countdown. Space holds it.
- F8 boot menu: A:, C:, CD-ROM, or an option ROM's own boot, once.
- Saved boot order (F8 → O): all four devices listed, moved with +/−, each switched on or off.
- CD-ROM boot (El Torito): floppy emulation and no emulation.
- Option ROMs that take over booting, such as the PicoMEM: the BIOS keeps control and calls the card's boot when wanted.

**Hard disks**
- Automatic by default, even after lost settings. Absent drives are skipped quietly (`hdd_auto`).
- Tools → Hard disk setup replaces USERHDD.EXE.
- Large-disk (LBA) mode for disks over 504 MB: up to 8.4 GB through CHS, and up to 128 GB through the INT 13h extensions.

**Tools (F10)**
- System information with the measured clock, drives, memory map with option ROMs, memory test, CMOS viewer, and NCR's floppy drive test.
- Setup accepts two-digit years 00–79 (`setup_year`).

Confirmed on the real machine: POST, boot, Tools, summary, CD-ROM boot. Emulator only so far: large-disk mode, Hard disk setup, the PicoMEM handling, the boot order.
