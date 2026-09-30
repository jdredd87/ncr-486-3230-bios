"""Minimal DOS environment on top of emu.Machine, enough to run small real-mode
EXE tools (Free Pascal i8086-msdos) against the emulated NCR hardware.

    d = DosMachine()
    rc = d.run_exe("userhdd/dos/userhdd.exe", "/SHOW", stdin="")
    print(d.stdout)
"""
import struct

from emu import Machine, StopEmu, CF

PSP_SEG = 0x1000
TOP_SEG = 0x9FC0


class DosExit(Exception):
    def __init__(self, code):
        self.code = code


class DosMachine(Machine):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.stubs[0x21] = self._int21
        self.stubs[0x20] = lambda: self._exit(0)
        self.stdout = ""
        self.stdin = ""
        self.unknown = []
        self.install_rom_vectors()
        self.set_vector(0x21, 0, 0)
        # The BIOS tick counter must advance for timeouts; run_exe bumps it
        # every 64 IDE status reads.
        self._status_reads = 0

    def _tick(self):
        t = self.mem_word(0x46C)
        self.write(0x46C, struct.pack("<H", (t + 1) & 0xFFFF))

    def _exit(self, code):
        raise DosExit(code)

    def _int21(self):
        ax = self.reg("ax")
        ah, al = ax >> 8, ax & 0xFF
        ok = lambda: self._setflag(CF, False)
        if ah == 0x30:
            self.set_regs(ax=0x0006, bx=0)                 # DOS 6.00
        elif ah == 0x4A:                                   # resize block
            ok()
        elif ah == 0x48:                                   # allocate
            self.set_regs(ax=0x8000)
            ok()
        elif ah == 0x49:
            ok()
        elif ah == 0x35:
            seg, off = self.vector(al)
            self.set_regs(es=seg, bx=off)
        elif ah == 0x25:
            self.set_vector(al, self.reg("ds"), self.reg("dx"))
        elif ah == 0x62 or ah == 0x51:
            self.set_regs(bx=PSP_SEG)
        elif ah == 0x44:                                   # IOCTL
            if al == 0x00:
                bx = self.reg("bx")
                self.set_regs(dx=0x80D3 if bx <= 2 else 0x0002)   # char device
                ok()
            else:
                ok()
        elif ah == 0x40:                                   # write
            bx, cx = self.reg("bx"), self.reg("cx")
            data = self.read(self.reg("ds") * 16 + self.reg("dx"), cx)
            if bx in (1, 2):
                self.stdout += data.decode("latin1")
            self.set_regs(ax=cx)
            ok()
        elif ah == 0x3F:                                   # read
            cx = self.reg("cx")
            line, self.stdin = self.stdin[:cx], self.stdin[cx:]
            if "\n" in line:
                i = line.index("\n") + 1
                self.stdin = line[i:] + self.stdin
                line = line[:i - 1] + "\r\n"
            self.write(self.reg("ds") * 16 + self.reg("dx"), line.encode("latin1"))
            self.set_regs(ax=len(line))
            ok()
        elif ah == 0x4C:
            raise DosExit(al)
        elif ah == 0x2C:                                   # get time
            self.set_regs(cx=0x0C00, dx=0)
        elif ah == 0x2A:
            self.set_regs(cx=1993, dx=0x0A08)
        elif ah == 0x19:
            self.set_regs(ax=(ax & 0xFF00) | 2)
        elif ah == 0x0B:
            self.set_regs(ax=ax & 0xFF00)
        elif ah == 0x3E:
            ok()
        elif ah == 0x33:
            self.set_regs(dx=0)
        elif ah == 0x29:
            self.set_regs(ax=ax & 0xFF00)
        elif ah == 0x1A or ah == 0x2F or ah == 0x0E or ah == 0x3B or ah == 0x47:
            ok()
        else:
            self.unknown.append(ax)
            self._setflag(CF, True)
            self.set_regs(ax=0x0001)

    def load_exe(self, path, args=""):
        data = open(path, "rb").read()
        assert data[:2] in (b"MZ", b"ZM")
        last, pages, nrel, hdr, minalloc, maxalloc, ss, sp, _, ip, cs, relo = \
            struct.unpack_from("<HHHHHHHHHHHH", data, 2)
        size = pages * 512 - (512 - last if last else 0)
        image = data[hdr * 16:size]
        load = PSP_SEG + 0x10
        self.write(load * 16, image)
        for i in range(nrel):
            off, seg = struct.unpack_from("<HH", data, relo + 4 * i)
            a = (load + seg) * 16 + off
            w = self.mem_word(a)
            self.write(a, struct.pack("<H", (w + load) & 0xFFFF))
        psp = bytearray(256)
        psp[0:2] = b"\xCD\x20"
        struct.pack_into("<H", psp, 2, TOP_SEG)
        tail = (" " + args if args else "").encode()
        psp[0x80] = len(tail)
        psp[0x81:0x81 + len(tail)] = tail
        psp[0x81 + len(tail)] = 0x0D
        struct.pack_into("<H", psp, 0x2C, 0x0F00)          # environment segment
        self.write(PSP_SEG * 16, bytes(psp))
        env = b"COMSPEC=C:\\COMMAND.COM\0\0\x01\0C:\\USERHDD.EXE\0"
        self.write(0x0F00 * 16, env)
        return load + cs, ip, load + ss, sp

    def run_exe(self, path, args="", stdin="", max_insns=50_000_000):
        cs, ip, ss, sp = self.load_exe(path, args)
        self.stdin = stdin
        self.set_regs(ss=ss, sp=sp, ds=PSP_SEG, es=PSP_SEG, ax=0, bx=0)
        self.uc.reg_write(__import__("unicorn").x86_const.UC_X86_REG_CS, cs)
        # Advance the BIOS tick on every IDE status read so timeouts can expire.
        orig = self.ide.inp

        def inp(port, size, _orig=orig):
            if port == 0x1F7:
                self._status_reads += 1
                if self._status_reads % 64 == 0:
                    self._tick()
            return _orig(port, size)
        self.ide.inp = inp
        try:
            self.uc.emu_start(cs * 16 + ip, 0xFFFFFFFF, count=max_insns)
        except DosExit as e:
            return e.code
        except Exception as e:  # unicorn surfaces hook exceptions as UcError
            cause = e.__context__ if isinstance(e.__context__, DosExit) else None
            if cause is not None:
                return cause.code
            raise StopEmu("DOS program stopped: %r at %04X:%04X (unknown int21: %s)"
                          % (e, self.reg("cs"), self.uc.reg_read(
                              __import__("unicorn").x86_const.UC_X86_REG_IP),
                             [hex(x) for x in self.unknown]))
        raise StopEmu("DOS program did not exit")
