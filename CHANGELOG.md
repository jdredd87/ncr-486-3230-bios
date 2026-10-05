# Changelog

Versions of the NCR 3230 BIOS **Enhanced Edition**. The NCR BIOS underneath stays 517-0000672 v2.03.00 (10/08/93).

The version is set in one place, `patches/src/version.inc`. It shows on the boot screen, the end-of-POST summary, Setup's title line and Tools → System information. Bump it for every build that gets burned, add an entry here, and tag the commit (`v1.0`, `v1.1`, …).

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
