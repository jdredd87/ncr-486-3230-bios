# The UMC 82C480 chipset

The NCR 3230's CPU board uses UMC's 82C480 chip set:

| Chip | Board | Job |
|---|---|---|
| UM82C481BF | U41 | Integrated Memory Controller: L2 cache controller (direct-mapped, write-back), DRAM controller, shadow RAM |
| UM82C482AF | U9 | Integrated System Controller: AT bus, CPU/ISA/keyboard clock dividers, DMA and refresh, parity |
| UM82C206F | U17 | Integrated Peripheral Controller: the AT DMA, interrupt controllers, timer and real-time clock |
| SMC FDC37C661 | U15 | Floppy, IDE, serial and parallel ports. It is configured through ports 3F0h/3F1h, which is the code at F000:4FDC/4FEF. |

Clocks: a socketed 33.3 MHz oscillator drives the CPU and the bus (the 486 runs at 1× bus clock; a DX2 doubles it inside). A separate 14.318 MHz oscillator drives the timer and the real-time clock.

The chipset's registers are reached through **index port 22h, data port 24h**.

## Where the register map comes from

UMC's published documents ([UM82C480 overview](https://theretroweb.com/chipset/documentation/um82c480-6373dc8cd1749300358557.pdf), [UM82C481 overview](https://theretroweb.com/chip/documentation/um82c481-6373dcabc8c02349458608.pdf)) list the features but not the registers. The map below is decoded from an **AMI BIOS dated 06/06/92 for another UMC 480 board** (the "486UL", POST string `40-0200-006105-00101111-060692-UMC480`, [The Retro Web](https://theretroweb.com/motherboards/s/unknown-486ul-ver-2)). That BIOS has an Advanced Chipset Setup screen:

- **Setup items.** Each item is its name followed by a record: CMOS byte, bit mask, flags, number of choices, and choice-string IDs. The IDs index a packed string list at offset B409h.
- **Register mapping.** At boot, AMI copies its CMOS bytes into the chipset with **register = CMOS address + 30h**. Its routine at offset 8FD6h does exactly `sub al, 30h`. So CMOS 61h holds register 91h.
- **Cross-checks.** The help texts confirm the mapping ("DRAM Read WS ... controlled by bits 3-2 of register 91H"). So does the code that applies each option, for example at offset 1B95h: CMOS 51h bits 0-2 and 4 go to register 81h.

**Confidence.** The fields below are confirmed by that BIOS. Their exact effect on *this* board has not been measured.

## Registers

The NCR value is what POST's table at F000:2225 writes. Some registers are changed later in POST, for cache and shadowing.

| Reg | Bits | Meaning (AMI's option and choices) | NCR value |
|---|---|---|---|
| 81h | 2-0 | **AT (ISA) bus clock**: 0 = CPUCLK/6, 1 = /5, 2 = /4, 3 = /3, 4 = /2, 7 = /8 (5, 6 reserved) | 31h: **/5** = 6.7 MHz at a 33 MHz bus |
| 81h | 4 | DMA address/data hold time: 0 = 1–2 T, 1 = 2–3 T | 1 (2–3 T) |
| 81h | 5 | Keyboard clock, together with 82h bits 7-6 (AMI sets it when its keyboard clock is not "Keyboard") | 1 |
| 82h | 1-0 | **I/O recovery time**: 0 = 2, 1 = 4, 2 = 8, 3 = 12 bus clocks | 54h: 2 bus clocks |
| 82h | 2 | Set by AMI from its CMOS 36h bit 0 (A20/keyboard related) | 1 |
| 82h | 7-6 | Keyboard clock select (CPUCLK/6, /4, /3, /2, 7.2 MHz) | 01 |
| 91h | 7-6 | **L2 cache read-hit burst**: 0 = 3-1-1-1, 1 = 3-2-2-2, 2 = 2-1-1-1 | 0Ah: 3-1-1-1 |
| 91h | 5-4 | **L2 cache write-hit wait states** (486 only): 0 = 1 WS, 1 = 2 WS, 2 = 0 WS (chip revision B only) | 1 WS |
| 91h | 3-2 | **DRAM read wait states**: 0 = 3, 1 = 2, 2 = 1, 3 = 0 WS (revision B). On revisions 0/A, bit 2 is fast page mode instead. | 1 WS |
| 91h | 1-0 | **DRAM write wait states** (revisions 0/A: read and write): 0 = 3 WS (2 on 0/A), 1 = 2 WS (reserved on 0/A), 2 = 1 WS, 3 = 0 WS | 1 WS |
| 92h | 0 | L2 cache enable | set by POST |
| 92h | 4 | Local bus ready delay: 0 = enabled, 1 = disabled | 0 |
| 92h | 6, 7 | Non-cacheable block 1 / block 2 enable | 0 |
| 93h | 7 | Memory above 16 MB cacheable | 1 |
| 93h | 6 | Coprocessor READY# delay: 0 = enabled, 1 = disabled | 1 |
| 93h | 5 | ELBA# sampled in T1 / T2 | 1 (T2) |
| 93h | 4-0 | L2 cache size code (F8h = 256 KB, FCh = 128 KB, FEh = 64 KB, FFh = 32 KB) | FEh, then set by POST |
| 97h | 7 | DMA CAS timing delay (CAS delayed by 1 T-state) | 1 |
| 97h | 6 | E0000 ROM belongs to the AT bus | 0 |
| 97h | 5 | A time-out option (AMI: "... Time Out") | 1 |
| 97h | 4 | DRAM page mode | 1 |
| 97h | 2 | Force the cache ALT bit active when turbo is off | 0 |
| 9Bh | 7 | Memory remapping (A0000–FFFFF to the top of DRAM) | 0 |
| 9Bh | 5 | E0000–EFFFF cacheable | 0 |
| 9Bh | 2 | F0000–FFFFF cacheable | 0 |
| 9Bh | 0 | F000 shadow write-protect (from the NCR BIOS) | 1 |
| 9Ch | 7-0 | C0000–DFFFF cacheable, one bit per 16 KB (bit 0 = C0000) | 0 |
| 9Dh, 9Eh | | Shadow RAM control (from the NCR BIOS) | |
| 01h | 0 | DMA clock: SCLK/2 or SCLK (AMI maps "register 1" to its CMOS 41h; probably in the UM82C206) | |

AMI's "Low Speed CPU Clock Select" (CLKIN, /2, /3, /4, used when turbo is off) and the keyboard clock come from its CMOS 4Fh through code that wasn't fully traced. The 82C482 has a TURBO input pin, and its datasheet lists a CPU clock divider of 1, 2, 3 or 4.

## What the improved BIOS does with it

- **Tools → 9 Chipset settings.** The ISA bus clock, I/O recovery time, DRAM read and write wait states, and L2 read burst and write wait states. Each is shown as the saved setting beside what is in the chip now. R shows all registers 80h–9Fh with the bits named.
- **Applied at the end of POST.** Settings are stored in CMOS 4Eh–51h and applied at the end of every POST (`chip_apply`). Without saved settings, nothing is written.
- **Fail-safe.** CMOS 52h is set to `P` before applying, and cleared when the boot reaches INT 19h or Tools. If it is still `P` on the next boot, the settings are marked failed (`F`) and skipped until they are saved again. A Shift key held at the end of POST skips them once.
