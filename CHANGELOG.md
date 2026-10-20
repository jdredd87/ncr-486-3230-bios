# Changelog

Versions of the NCR 3230 BIOS **Enhanced Edition**. The NCR BIOS underneath stays 517-0000672 v2.03.00 (10/08/93).

The version is set in one place, `patches/src/version.inc`. It shows on the boot screen, the end-of-POST summary, Setup's title line and Tools → System information. Bump it for every build that gets burned, add an entry here, and tag the commit (`v1.0`, `v1.1`, …).

## 1.8 (2026-10-19)

- Fix: the **video memory clock was not kept**. 1.5 stored it in CMOS 53h, but NCR's POST clears 53h on every boot (F000:40FE, when the keyboard controller's input port bit 5 is low, as it is on this board). It is now in CMOS 60h, which nothing else uses. A clock saved with 1.5 to 1.7 is lost: set it again and save.
- New: **Video memory speed test**, V on Tools → 9. It writes and reads 16 KB of video memory at each of the six clocks, timed with the PIT, and shows KB/s for each. The clock goes back to its value from before the test, and nothing is saved. Same numbers at every clock mean the bus is the limit.

## 1.7 (2026-10-19)

- Memory test fix: once more than six errors had been logged, each new entry showed the wrong last four hex digits of its address (the log's scroll overwrote them). This affected data errors since the first version, and parity errors in 1.6.
- The memory test shows the range the parity errors fall in ("Parity errors from … to …"), so many errors in one area read at a glance.

## 1.6 (2026-10-19)

- Tools → 4 **Memory test** now catches **parity errors**. A stick with a bad parity chip reads every data bit back right, so the data compare alone missed it. After each 64 KB checked, the test reads the parity latch (port 61h bit 7). When it is set, the test reads that 64 KB again with the caches emptied first and logs each 16-byte line that fails. An error that does not come back is logged for the whole 64 KB. Parity errors are counted apart from data errors.
- Two more patterns, 01h and FEh bytes, so each byte's parity bit is tested holding both values (00h, FFh, 55h and AAh all give the same parity bit). There are now seven tests in a pass.
- The NMI stays masked during the test, so a parity error is reported by the test instead of halting the machine with NCR's "MAIN BOARD PARITY ERROR AT" message. That message only names an address when the error is in the first 640 KB; above that it stops with the address blank.
- Emulator: a model of the port 61h parity latch.

## 1.5 (2026-10-19)

- New: **Video memory clock** in Tools → 9 Chipset settings, for the Cirrus Logic CL-GD542x video chip: the VGA BIOS's 50.1 MHz, or 53.7, 55.5, 57.3, 59.1 or 60.9 MHz. It is stored in CMOS 53h, applied at the end of POST with the other chipset settings, and covered by the same fail-safe and Shift skip. The row also shows the clock the chip runs at now.
- The Video line in System information and the end-of-POST summary names the Cirrus chip and its video memory, for example "Cirrus CL-GD5426, 1 MB".
- The VGA BIOS itself is unchanged. It sets 50.1 MHz once while it starts, and never again on a mode change, so the new value stays.
- Emulator: a model of the Cirrus extended registers; tests run the real VGA BIOS start-up and mode sets.

## 1.4 (2026-10-06)

- New: **ISA Plug and Play**. At the end of POST the BIOS finds ISA PnP cards, chooses non-conflicting I/O, IRQ and DMA for each logical device (preferred resource set first, then the alternatives), and activates them. An AWE64 is ready for DOS without CTCM.
- New: Tools → P **Plug and Play cards**: the cards and what each device got, the `SET BLASTER=` line for Creative cards, on/off, IRQs/DMA/I/O ranges kept free for non-PnP cards (CMOS 54h–5Fh), and R to configure again. The summary shows a Plug and Play line.
- Emulator: an ISA PnP card model (key, isolation with arbitration, resource data, registers); tests with AWE64-style, modem and conflicting cards (`tests/test_pnp.py`).

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
