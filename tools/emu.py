"""Real-mode test rig for the NCR 3230 BIOS, built on the Unicorn CPU emulator.

It runs pieces of the real ROM code (not re-implementations) against
simulated hardware, so patches can be tested before a chip is flashed:

  * 1 MB address space; the 128 KB image is mapped at E0000-FFFFF.
  * CMOS/RTC (ports 70h/71h) with 128 bytes of RAM.
  * NCR chipset index/data (22h/24h); reg 9Bh bit 0 write-protects F0000-FFFFF.
  * Primary IDE channel (1F0-1F7, 3F6) with master/slave devices:
    None, AtaDisk (geometry, IDENTIFY, READ SECTORS) or Atapi (ISO image,
    PACKET READ(10)/READ CAPACITY/TEST UNIT READY/REQUEST SENSE).
    IRQ 14 is modelled by setting the BIOS "interrupt received" flag 40:8E.
  * Timer (PIT) and port 61h refresh toggle so delay loops terminate.
  * Software interrupts are dispatched through the emulated IVT, except
    vectors given Python stubs (INT 10h teletype capture, INT 16h keys, ...).

Typical use:
    m = Machine()
    m.cmos[0x12] = 0x20
    m.near_call(0xF000, 0x9062)          # run until the routine returns
"""
import os
import struct

from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR, \
    UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_INS_IN, UC_X86_INS_OUT, UC_X86_REG_AX, UC_X86_REG_BX,
                               UC_X86_REG_CX, UC_X86_REG_DX, UC_X86_REG_SI, UC_X86_REG_DI,
                               UC_X86_REG_BP, UC_X86_REG_SP, UC_X86_REG_CS, UC_X86_REG_DS,
                               UC_X86_REG_ES, UC_X86_REG_SS, UC_X86_REG_IP, UC_X86_REG_EFLAGS,
                               UC_X86_REG_EIP)

HERE = os.path.dirname(os.path.abspath(__file__))
ORIGINAL = os.path.join(HERE, "..", "NCR-BIOS-517-0000672-VER2.03.00-U19.BIN")

REGS = {"ax": UC_X86_REG_AX, "bx": UC_X86_REG_BX, "cx": UC_X86_REG_CX, "dx": UC_X86_REG_DX,
        "si": UC_X86_REG_SI, "di": UC_X86_REG_DI, "bp": UC_X86_REG_BP, "sp": UC_X86_REG_SP,
        "cs": UC_X86_REG_CS, "ds": UC_X86_REG_DS, "es": UC_X86_REG_ES, "ss": UC_X86_REG_SS,
        "flags": UC_X86_REG_EFLAGS}
CF, ZF, IF = 0x0001, 0x0040, 0x0200
SENTINEL_FAR = (0x0000, 0x0500)       # far return lands here
SENTINEL_NEAR = 0xFFF8                # near return offset in the routine's segment
SENTINEL_NEAR_F000 = 0xA3F8           # F000: use free space, not the ROM date at FFF5


class StopEmu(Exception):
    pass


# ----------------------------------------------------------------- devices

class AtaDisk:
    """ATA hard disk with a CHS geometry; sectors read back as a pattern."""

    def __init__(self, cyl, heads, spt, model="EMU ATA DISK"):
        self.cyl, self.heads, self.spt, self.model = cyl, heads, spt, model
        self.cur_heads, self.cur_spt = heads, spt
        self.sectors = {}

    def identify(self):
        w = [0] * 256
        w[0] = 0x0040
        w[1], w[3], w[6] = min(self.cyl, 16383), self.heads, self.spt
        m = self.model.ljust(40)[:40].encode()
        for i in range(20):
            w[27 + i] = (m[2 * i] << 8) | m[2 * i + 1]
        w[49] = 0x0200                               # LBA supported
        total = self.cyl * self.heads * self.spt
        w[60], w[61] = total & 0xFFFF, total >> 16
        return struct.pack("<256H", *w)


class Atapi:
    """ATAPI CD-ROM backed by an ISO image (bytes)."""

    def __init__(self, iso=b"", model="EMU ATAPI CDROM"):
        self.iso, self.model = iso, model
        self.sense = 0x06            # unit attention after power-on, like real drives

    def identify_packet(self):
        w = [0] * 256
        w[0] = 0x8580                                # ATAPI, CD-ROM, 12-byte packets
        m = self.model.ljust(40)[:40].encode()
        for i in range(20):
            w[27 + i] = (m[2 * i] << 8) | m[2 * i + 1]
        return struct.pack("<256H", *w)

    def read(self, lba, count):
        data = self.iso[lba * 2048:(lba + count) * 2048]
        return data.ljust(count * 2048, b"\0")


class IdeChannel:
    """Primary IDE channel. Absent devices read `float_value` on every port."""

    def __init__(self, machine, master=None, slave=None, float_value=0xFF):
        self.m = machine
        self.dev = [master, slave]
        self.float_value = float_value
        self.regs = {1: 0, 2: 1, 3: 1, 4: 0, 5: 0, 6: 0xA0}
        self.status = [0x50, 0x50]
        self.error = [0, 0]
        self.buf = b""
        self.pos = 0
        self.wbuf = bytearray()
        self.expect_write = 0
        self.packet_mode = False
        self.nien = False
        self.log = []
        self.reset()

    @property
    def sel(self):
        return (self.regs[6] >> 4) & 1

    def cur(self):
        return self.dev[self.sel]

    def signature(self, n):
        d = self.dev[n]
        if isinstance(d, Atapi):
            return (0x14, 0xEB, 0x00)       # ATAPI: DRDY clear after reset
        return (0x00, 0x00, 0x50)

    def reset(self):
        for n in (0, 1):
            self.error[n] = 0x01
            self.status[n] = self.signature(n)[2]
        self.regs.update({2: 1, 3: 1})
        lo, hi, _ = self.signature(self.sel)
        self.regs[4], self.regs[5] = lo, hi
        self.buf, self.pos = b"", 0

    def irq(self):
        if not self.nien:
            flag = self.m.mem_byte(0x48E)
            self.m.write(0x48E, bytes([flag | 0x80]))

    def data_ready(self, data):
        self.buf, self.pos = data, 0
        self.status[self.sel] = 0x58
        self.irq()

    def done(self, err=0):
        n = self.sel
        self.buf, self.pos = b"", 0
        if err:
            self.error[n] = err
            # ATA disks keep DRDY and DSC (seek complete) with ERR: 51h, as real drives do.
            self.status[n] = (0x50 if isinstance(self.cur(), AtaDisk) else 0x00) | 0x01
        else:
            self.error[n] = 0
            self.status[n] = 0x50 if isinstance(self.cur(), AtaDisk) else 0x40
        self.irq()

    # -- port access
    def inp(self, port, size):
        d = self.cur()
        if port == 0x3F6:
            port = 0x1F7                     # alternate status, no IRQ clear
        if d is None:
            if self.dev[0] is None and self.dev[1] is None:
                return self.float_value if size == 1 else self.float_value * 0x101
            if port == 0x1F7:
                return 0x00                  # other device answers; selected one absent
            return self.float_value
        off = port - 0x1F0
        if off == 0:
            if self.pos >= len(self.buf):
                return 0xFFFF if size == 2 else 0xFF
            if size == 2:
                v = self.buf[self.pos] | (self.buf[self.pos + 1] << 8)
                self.pos += 2
            else:
                v = self.buf[self.pos]
                self.pos += 1
            if self.pos >= len(self.buf):
                self.after_read_block()
            return v
        if off == 1:
            return self.error[self.sel]
        if off == 7:
            return self.status[self.sel]
        return self.regs.get(off, 0)

    def after_read_block(self):
        if self.remaining_blocks > 0:
            self.remaining_blocks -= 1
            self.next_block()
        else:
            self.done()

    def outp(self, port, size, value):
        if port == 0x3F6:
            self.nien = bool(value & 2)
            if value & 4:
                self.reset()
            return
        off = port - 0x1F0
        if off == 0:
            if self.expect_write:
                self.wbuf += bytes([value & 0xFF, (value >> 8) & 0xFF]) if size == 2 else bytes([value & 0xFF])
                if len(self.wbuf) >= self.expect_write:
                    data, self.expect_write = bytes(self.wbuf), 0
                    self.wbuf = bytearray()
                    self.on_write_done(data)
            return
        if off == 7:
            self.command(value & 0xFF)
            return
        self.regs[off] = value & 0xFF

    # -- commands
    def command(self, cmd):
        d = self.cur()
        self.log.append((self.sel, cmd))
        if d is None:
            return
        self.remaining_blocks = 0
        if isinstance(d, Atapi):
            if cmd == 0xA1:
                self.data_ready(d.identify_packet())
            elif cmd == 0xA0:
                self.status[self.sel] = 0x58
                self.regs[2] = 0x01          # interrupt reason: CoD=1, IO=0
                self.expect_write, self.on_write_done = 12, self.packet
            elif cmd == 0x08:                # DEVICE RESET
                self.reset()
            elif cmd == 0x90:
                self.error[0], self.error[1] = 0x01, 0x01
                self.irq()
            else:                            # ATA commands are aborted, signature shown
                self.regs[4], self.regs[5] = 0x14, 0xEB
                self.done(err=0x04)
            return
        # ATA disk
        if cmd == 0xEC:
            self.data_ready(d.identify())
        elif cmd == 0x90:                    # EXECUTE DEVICE DIAGNOSTIC
            self.error[0] = 0x01
            self.status[self.sel] = 0x50
            self.irq()
        elif cmd == 0x91:                    # INITIALIZE DEVICE PARAMETERS
            d.cur_heads, d.cur_spt = (self.regs[6] & 0x0F) + 1, self.regs[2]
            self.done()
        elif cmd in (0x20, 0x21):
            self.remaining_blocks = (self.regs[2] or 256) - 1
            self.next_block()
        elif cmd in (0x30, 0x31):
            self.remaining_blocks = (self.regs[2] or 256) - 1
            self.status[self.sel] = 0x58
            self.expect_write, self.on_write_done = 512, self.write_block
        elif cmd in (0x40, 0x41, 0x70, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19,
                     0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0xE5, 0xE0, 0xE1, 0xE2, 0xE3, 0xEF, 0xC6):
            self.done()
        else:
            self.done(err=0x04)

    def chs_lba(self):
        d = self.cur()
        if self.regs[6] & 0x40:
            return ((self.regs[6] & 0x0F) << 24) | (self.regs[5] << 16) | (self.regs[4] << 8) | self.regs[3]
        cyl = self.regs[4] | (self.regs[5] << 8)
        head = self.regs[6] & 0x0F
        sec = self.regs[3]
        return (cyl * d.cur_heads + head) * d.cur_spt + sec - 1

    def next_block(self):
        d = self.cur()
        lba = self.chs_lba()
        data = d.sectors.get(lba, struct.pack("<I", lba) * 128)
        self.advance()
        self.data_ready(data)

    def advance(self):
        d = self.cur()
        if self.regs[6] & 0x40:
            lba = self.chs_lba() + 1
            self.regs[3], self.regs[4], self.regs[5] = lba & 0xFF, (lba >> 8) & 0xFF, (lba >> 16) & 0xFF
            return
        sec = self.regs[3] + 1
        if sec > d.cur_spt:
            sec = 1
            head = (self.regs[6] & 0x0F) + 1
            if head >= d.cur_heads:
                head = 0
                cyl = (self.regs[4] | (self.regs[5] << 8)) + 1
                self.regs[4], self.regs[5] = cyl & 0xFF, cyl >> 8
            self.regs[6] = (self.regs[6] & 0xF0) | head
        self.regs[3] = sec

    def write_block(self, data):
        d = self.cur()
        d.sectors[self.chs_lba()] = data
        self.advance()
        if self.remaining_blocks > 0:
            self.remaining_blocks -= 1
            self.expect_write, self.on_write_done = 512, self.write_block
            self.irq()
        else:
            self.done()

    def packet(self, pkt):
        d = self.cur()
        op = pkt[0]
        self.log.append((self.sel, "pkt", pkt.hex()))
        if op == 0x28:                       # READ(10)
            lba = struct.unpack(">I", pkt[2:6])[0]
            cnt = struct.unpack(">H", pkt[7:9])[0]
            if d.sense == 0x06:
                d.sense = 0
                return self.check_condition()
            if (lba + cnt) * 2048 > len(d.iso) + 2048 * 16:
                d.sense = 0x05
                return self.check_condition()
            self.packet_data(d.read(lba, cnt))
        elif op == 0x25:                     # READ CAPACITY
            last = max(len(d.iso) // 2048 - 1, 0)
            self.packet_data(struct.pack(">II", last, 2048))
        elif op == 0x00:                     # TEST UNIT READY
            if d.sense == 0x06:
                d.sense = 0
                return self.check_condition()
            self.packet_done()
        elif op == 0x03:                     # REQUEST SENSE
            s = bytearray(18)
            s[0], s[2], s[7] = 0x70, d.sense, 10
            d.sense = 0
            self.packet_data(bytes(s[:pkt[4] or 18]))
        elif op == 0x1B:                     # START STOP UNIT
            self.packet_done()
        else:
            d.sense = 0x05
            self.check_condition()

    def packet_data(self, data):
        # One DRQ block of the whole transfer, byte count in cylinder regs.
        n = len(data)
        limit = self.regs[4] | (self.regs[5] << 8)
        if limit == 0 or limit > 0xFFFE:
            limit = 0xFFFE
        chunk = min(n, limit & ~1)
        self._pending = data[chunk:]
        self.regs[4], self.regs[5] = chunk & 0xFF, chunk >> 8
        self.regs[2] = 0x02                  # IO=1, CoD=0
        self.buf, self.pos = data[:chunk], 0
        self.status[self.sel] = 0x58
        self.remaining_blocks = 0
        self.after_read_block = self._packet_next
        self.irq()

    def _packet_next(self):
        self.after_read_block = IdeChannel.after_read_block.__get__(self)
        if self._pending:
            self.packet_data(self._pending)
        else:
            self.packet_done()

    def packet_done(self):
        self.regs[2] = 0x03                  # IO=1, CoD=1: command complete
        self.buf, self.pos = b"", 0
        self.error[self.sel] = 0
        self.status[self.sel] = 0x40
        self.irq()

    def check_condition(self):
        d = self.cur()
        self.regs[2] = 0x03
        self.error[self.sel] = (d.sense or 0x02) << 4
        self.status[self.sel] = 0x41
        self.irq()


# ----------------------------------------------------------------- machine

class Machine:
    def __init__(self, image=ORIGINAL, ram_kb=640):
        img = open(image, "rb").read() if isinstance(image, str) else bytes(image)
        assert len(img) == 0x20000
        self.image = img
        self.uc = Uc(UC_ARCH_X86, UC_MODE_16)
        self.uc.mem_map(0, 0x120000)                 # 1 MB + HMA wrap area
        self.uc.mem_write(0xE0000, img)
        self.ram_kb = ram_kb
        self.cmos = bytearray(128)
        self.cmos[0x0A], self.cmos[0x0B], self.cmos[0x0D] = 0x26, 0x02, 0x80
        self.cmos_index = 0
        self.chipset = {0x9B: 0x01}
        self.chip_index = 0
        self.ide = IdeChannel(self)
        self.port80 = []
        self.ports_log = []
        self.log_ports = False
        self.io_count = 0
        self.screen = []
        self.keys = []
        self.pit = 0
        self.refresh = 0
        self.stubs = {0x10: self._int10, 0x16: self._int16, 0x15: self._int15}
        self.ints = []
        self.rom_writes = []
        self.uc.hook_add(UC_HOOK_INSN, self._in, None, 1, 0, UC_X86_INS_IN)
        self.uc.hook_add(UC_HOOK_INSN, self._out, None, 1, 0, UC_X86_INS_OUT)
        self.uc.hook_add(UC_HOOK_INTR, self._intr)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._romwrite, begin=0xF0000, end=0xFFFFF)
        self.uc.mem_write(0x500, b"\xF4")            # far sentinel: HLT
        # BIOS data area basics
        self.write(0x413, struct.pack("<H", ram_kb))
        self.write(0x4AE, struct.pack("<H", 40))     # delay calibration used by some loops

    # -- memory
    def write(self, addr, data):
        self.uc.mem_write(addr, bytes(data))

    def read(self, addr, n):
        return bytes(self.uc.mem_read(addr, n))

    def mem_byte(self, addr):
        return self.read(addr, 1)[0]

    def mem_word(self, addr):
        return struct.unpack("<H", self.read(addr, 2))[0]

    def set_vector(self, n, seg, off):
        self.write(n * 4, struct.pack("<HH", off, seg))

    def vector(self, n):
        off, seg = struct.unpack("<HH", self.read(n * 4, 4))
        return seg, off

    def install_rom_vectors(self):
        """Point INT 08h-1Fh / 70h-77h at the ROM handlers from F000:FEF3 / FF23,
        and add the BIOS's own INT 13h fixed-disk handler with INT 40h = diskette."""
        for k in range(24):
            off = struct.unpack_from("<H", self.image, 0x1FEF3 + 2 * k)[0]
            if off:
                self.set_vector(8 + k, 0xF000, off)
        for k in range(8):
            off = struct.unpack_from("<H", self.image, 0x1FF23 + 2 * k)[0]
            self.set_vector(0x70 + k, 0xF000, off)
        self.set_vector(0x40, 0xF000, 0xEC59)
        self.set_vector(0x13, 0xF000, 0x94E3)
        self.set_vector(0x76, 0xF000, 0x9B61)

    # -- registers
    def reg(self, name):
        return self.uc.reg_read(REGS[name])

    def set_regs(self, **kw):
        for k, v in kw.items():
            self.uc.reg_write(REGS[k], v)

    # -- ports
    def _in(self, uc, port, size, user):
        v = self.port_in(port, size)
        self.io_count += 1
        if self.log_ports:
            self.ports_log.append(("in", port, v))
        return v

    def _out(self, uc, port, size, value, user):
        self.io_count += 1
        if self.log_ports:
            self.ports_log.append(("out", port, value))
        self.port_out(port, size, value)

    def est_seconds(self):
        """Rough real-hardware time: ~1 us per ISA I/O access dominates these loops."""
        return self.io_count * 1.0e-6

    def port_in(self, port, size):
        if port == 0x71:
            i = self.cmos_index & 0x7F
            v = self.cmos[i]
            if i == 0x0A:
                v &= 0x7F                            # UIP never stuck
            if i == 0x0C:
                self.cmos[0x0C] = 0
            return v
        if port == 0x70:
            return self.cmos_index
        if port == 0x24:
            return self.chipset.get(self.chip_index, 0)
        if 0x1F0 <= port <= 0x1F7 or port == 0x3F6:
            return self.ide.inp(port, size)
        if port in (0x40, 0x41, 0x42):
            self.pit = (self.pit - 37) & 0xFFFF
            return self.pit & 0xFF
        if port == 0x61:
            self.refresh ^= 0x10
            return 0x20 | self.refresh
        if port == 0x64:
            return 0x1C
        if port == 0x60:
            return 0x00
        if port in (0x21, 0xA1):
            return 0x00
        return 0xFF

    def port_out(self, port, size, value):
        if port == 0x70:
            self.cmos_index = value & 0xFF
        elif port == 0x71:
            self.cmos[self.cmos_index & 0x7F] = value & 0xFF
        elif port == 0x22:
            self.chip_index = value & 0xFF
        elif port == 0x24:
            self.chipset[self.chip_index] = value & 0xFF
        elif port == 0x80:
            self.port80.append(value & 0xFF)
        elif 0x1F0 <= port <= 0x1F7 or port == 0x3F6:
            self.ide.outp(port, size, value)

    def _romwrite(self, uc, access, address, size, value, user):
        self.rom_writes.append((address, size, value, self.chipset.get(0x9B, 0) & 1))

    # -- interrupts
    def _intr(self, uc, intno, user):
        ip = uc.reg_read(UC_X86_REG_IP)
        cs = uc.reg_read(UC_X86_REG_CS)
        self.ints.append((intno, self.reg("ax")))
        if intno in self.stubs:
            self.stubs[intno]()
            return
        seg, off = self.vector(intno)
        if seg == 0 and off == 0:
            raise StopEmu("INT %02Xh has no handler (at %04X:%04X)" % (intno, cs, ip))
        flags = uc.reg_read(UC_X86_REG_EFLAGS)
        sp = (uc.reg_read(UC_X86_REG_SP) - 6) & 0xFFFF
        ss = uc.reg_read(UC_X86_REG_SS)
        self.write(ss * 16 + sp, struct.pack("<HHH", ip, cs, flags & 0xFFFF))
        uc.reg_write(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_EFLAGS, flags & ~(IF | 0x100))
        uc.reg_write(UC_X86_REG_CS, seg)
        uc.reg_write(UC_X86_REG_EIP, off)

    def _setflag(self, mask, on):
        f = self.uc.reg_read(UC_X86_REG_EFLAGS)
        self.uc.reg_write(UC_X86_REG_EFLAGS, (f | mask) if on else (f & ~mask))

    def _int10(self):
        ah = self.reg("ax") >> 8
        if ah == 0x0E:
            self.screen.append(chr(self.reg("ax") & 0xFF))
        elif ah == 0x0F:
            self.set_regs(ax=0x5003, bx=0)

    def _int16(self):
        ah = self.reg("ax") >> 8
        if ah in (0x00, 0x10):
            if not self.keys:
                raise StopEmu("INT 16h wait for key with no key queued")
            self.set_regs(ax=self.keys.pop(0))
        elif ah in (0x01, 0x11):
            if self.keys:
                self.set_regs(ax=self.keys[0])
                self._setflag(ZF, False)
            else:
                self._setflag(ZF, True)

    def _int15(self):
        ah = self.reg("ax") >> 8
        if ah in (0x90, 0x91):
            self._setflag(CF, False)
            self.set_regs(ax=self.reg("ax") & 0x00FF)
        else:
            self._setflag(CF, True)

    def text(self):
        return "".join(self.screen)

    # -- running
    def _run(self, seg, off, until, max_insns):
        self.uc.reg_write(UC_X86_REG_CS, seg)
        self.uc.reg_write(UC_X86_REG_EIP, off)
        try:
            self.uc.emu_start(seg * 16 + off, until, count=max_insns)
        except UcError as e:
            cs, ip = self.reg("cs"), self.uc.reg_read(UC_X86_REG_IP)
            raise StopEmu("CPU error %s at %04X:%04X" % (e, cs, ip))
        cs, ip = self.reg("cs"), self.uc.reg_read(UC_X86_REG_IP)
        if cs * 16 + ip != until:
            raise StopEmu("did not return within %d instructions (at %04X:%04X)" % (max_insns, cs, ip))

    def stack(self, ss=0x0000, sp=0x7000):
        self.set_regs(ss=ss, sp=sp)

    def run_steps(self, seg, off, n, **regs):
        """Execute exactly n instructions from seg:off; return (cs, ip) after them."""
        if "sp" not in regs:
            self.stack()
        self.set_regs(**regs)
        self.uc.reg_write(UC_X86_REG_CS, seg)
        self.uc.reg_write(UC_X86_REG_EIP, off)
        self.uc.emu_start(seg * 16 + off, 0xFFFFFFFF, count=n)
        return self.reg("cs"), self.uc.reg_read(UC_X86_REG_IP)

    def near_call(self, seg, off, max_insns=20_000_000, **regs):
        """Call seg:off as a near subroutine; returns when it RETs."""
        if "sp" not in regs:
            self.stack()
        self.set_regs(**regs)
        ret = SENTINEL_NEAR_F000 if seg == 0xF000 else SENTINEL_NEAR
        self.write(seg * 16 + ret, b"\xF4")
        sp = (self.reg("sp") - 2) & 0xFFFF
        self.write(self.reg("ss") * 16 + sp, struct.pack("<H", ret))
        self.set_regs(sp=sp)
        self._run(seg, off, seg * 16 + ret, max_insns)

    def far_call(self, seg, off, max_insns=20_000_000, **regs):
        if "sp" not in regs:
            self.stack()
        self.set_regs(**regs)
        sp = (self.reg("sp") - 4) & 0xFFFF
        self.write(self.reg("ss") * 16 + sp, struct.pack("<HH", SENTINEL_FAR[1], SENTINEL_FAR[0]))
        self.set_regs(sp=sp)
        self._run(seg, off, SENTINEL_FAR[0] * 16 + SENTINEL_FAR[1], max_insns)

    def run_until(self, seg, off, stop_seg, stop_off, max_insns=20_000_000, **regs):
        """Run from seg:off until execution reaches stop_seg:stop_off."""
        if "sp" not in regs:
            self.stack()
        self.set_regs(**regs)
        self._run(seg, off, stop_seg * 16 + stop_off, max_insns)

    def int_call(self, n, max_insns=20_000_000, **regs):
        """Invoke INT n through the IVT, as `int n` from a caller would."""
        seg, off = self.vector(n)
        if "sp" not in regs:
            self.stack()
        self.set_regs(**regs)
        flags = self.reg("flags") | IF
        sp = (self.reg("sp") - 6) & 0xFFFF
        self.write(self.reg("ss") * 16 + sp, struct.pack("<HHH", SENTINEL_FAR[1], SENTINEL_FAR[0], flags))
        self.set_regs(sp=sp)
        self._run(seg, off, SENTINEL_FAR[0] * 16 + SENTINEL_FAR[1], max_insns)

    def cf(self):
        return bool(self.reg("flags") & CF)

    def zf(self):
        return bool(self.reg("flags") & ZF)

    def tick_at(self, linear):
        """Advance the BIOS tick count (40:6C) each time `linear` executes."""
        def hook(uc, address, size, user):
            t = self.mem_word(0x46C)
            self.write(0x46C, struct.pack("<H", (t + 1) & 0xFFFF))
            self.ticks_advanced = getattr(self, "ticks_advanced", 0) + 1
        self.uc.hook_add(UC_HOOK_CODE, hook, begin=linear, end=linear)


def cmos_checksum(cmos):
    """Fix the standard checksum (10h-2Dh -> 2Eh hi / 2Fh lo) in a CMOS bytearray."""
    s = sum(cmos[0x10:0x2E]) & 0xFFFF
    cmos[0x2E], cmos[0x2F] = s >> 8, s & 0xFF
