# NCR 3230 hardware notes

Findings from the BIOS disassembly plus what we know about the board so far. Items that come from reading code are marked with their ROM address; anything not yet checked on the machine is flagged as such.

## Second-level (L2) cache

What the BIOS does (POST cache test, F000:38C4–3BB1):

- **Runs when enabled.** It runs only when Setup's "Second Level Cache" is on (CMOS 47h bit 2), and not on a warm boot.
- **Test mode.** It sets chipset register 93h = F0h and 92h = 01h (index port 22h, data port 24h).
- **Sizing by aliasing.** It writes 5Ah to 18000h, disables the CPU's internal cache, then reads 58000h, 38000h, 28000h and 10000h (256/128/64/32 KB away). The size is the smallest offset that no longer returns 5Ah. Only a **direct-mapped** cache behaves this way.
- **Size code** in register 93h: F8h = 256 KB, FCh = 128 KB, FEh = 64 KB, FFh = 32 KB. The chipset init table defaults to FEh.
- **Data test and enable.** It fills and verifies 10000h–4FFFFh (256 KB) or 64 KB, then enables the cache with 92h = 21h. On failure it prints "Cache data compare Error" or "Cache Configuration Error", sets 92h = 00h and clears the Setup option.
- **No presence pin.** The BIOS never reads a module ID. "SECOND LEVEL CACHE NOT INSTALLED" only means the Setup option is off.
- **Message bug (cosmetic).** The size message only knows 256 KB and 64 KB, so a 128 KB or 32 KB module would work but print "64 KB".

The cache controller is in the chipset, so a module carries only data SRAM, tag SRAM and possibly a dirty bit. The chipset is not yet identified. It uses registers 80h–9Fh through ports 22h/24h, which is not OPTi's 82C493 (that uses the same ports but registers 20h–2Bh).

### P1 edge connector (CPU card)

The CPU card has gold edge fingers (P1). Traces from P1 run into the area of the empty PQFP footprint (U33), which is where a surface-mount 486SX could be fitted instead of the ZIF socket. Both CPU sites share one bus, so P1 very likely carries the 486 bus and is the cache/processor-bus connector. **Not yet confirmed.**

Mapping it: [`p1-connector-map.html`](p1-connector-map.html) is the bench worksheet. The live copy, with the shared log Claude can read, is at https://claude.ai/artifact/WKATFoimsoxbJn9AcXqG9G (private). Its pin table is Intel's 168-pin PGA cross-reference (Embedded IntelDX2 datasheet, Table 7), checked to cover all 168 holes exactly once.

A 256 KB direct-mapped cache on a 486 needs:
- A2–A17 as index
- A18 and up as tag
- D0–D31
- BE0–3#
- ADS#, W/R#, M/IO#, D/C#, CLK
- BRDY#/RDY#, KEN#, BLAST#
- from the chipset: SRAM chip-select, output-enable and write-enables, plus the tag data lines

### Building a module: conclusions so far

- **Adapter approach.** Use a card-edge socket that mates with P1 on a small PCB carrying the SRAMs directly. First measure P1's finger pitch (across 10 fingers), the count per side, board thickness and the key notch position.
- **No standard module to reuse.** There is no industry-standard 486 cache module. COAST ("cache on a stick", 160-pin) belongs to the Pentium era: pipelined-burst SRAM on a 64-bit bus, which won't work with this chipset's asynchronous 32-bit cache. 486 boards used loose DIP SRAMs.
- **Parts.**
  - Data: 8 × 32K×8 fast 5 V asynchronous SRAM for 256 KB. 15–20 ns is enough at 33 MHz. New parts include the CY7C199 and IS61C256; period UM61256/W24257-class chips also work.
  - Tag: one fast SRAM, 32K×8 for 256 KB. Add a dirty-bit chip if the chipset runs write-back.
- **Two banks.** A 256 KB 486 cache is usually two interleaved 32-bit banks (32K×64 in total). Each bank needs its own output enable or chip select onto the CPU's single 32-bit data bus.
- **Smart "ASYNCH 32Kx64" modules** (eBay 335241730026) are most likely Pentium-era cache sticks despite "486" in the title. Their pinout is unknown and designed for a Pentium chipset, so they're not wireable to P1. They're useful only as a donor of 32K×8 async SRAMs, if that's what they carry.
- **The PicoMEM can't emulate L2.** It sits on the 8-bit ISA bus, which never sees CPU memory cycles, and responds in hundreds of ns against the 15–20 ns a cache needs.
- The deciding input is still the **P1 pinout**. Especially important are the fingers that go to the chipset instead of the CPU: SRAM chip select, output enable, write enables and tag lines.

## CPU upgrades

From the BIOS:
- **No CPU identification.** There's no CPUID and no CPU table, so the BIOS is CPU-agnostic.
- **FPU detected automatically.** It uses FNINIT/FNSTSW (F000:45A1), so SX and DX both work.
- **Write-through internal cache only.** The BIOS uses INVD and the CR0 CD/NW bits and never WBINVD.
- **Timing adapts.** Delays are calibrated against the PIT (F000:3BCA → 40:AE), so faster CPUs don't break them.
- **"PROCESSOR SPEED: xx MHz" is not measured.** It prints CMOS 43h, which neither POST nor Setup writes. It is cosmetic, and shows 00 after the battery has been lost.

Board: the fitted CPU is an i486DX-33 (SX729) in the ZIF socket, so the bus runs at 33 MHz and 5 V, with no jumpers. Suitable upgrades replace that CPU:
- **Intel 486DX2-66**
- **DX2ODPR66**, the DX2 OverDrive (the user has one)
- **DX4ODPR100** (5 V, built-in regulator)
- **AMD 5x86 only on a regulator module** such as Kingston TurboChip, and in write-through mode

Avoid bare 3.3 V parts and the Pentium OverDrive, which needs a 238-pin socket.

## Still to do

- Identify the chipset from its chip markings (U41 reads something like "N91568").
- Finish the P1 continuity map, then derive the pinout and a 256 KB module schematic.
- Optional BIOS patch: show the measured CPU speed instead of CMOS 43h.
