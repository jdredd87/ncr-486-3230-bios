"""Recursive-descent disassembler for the NCR 486 system BIOS (F000 segment).

Usage:  python tools/disasm_bios.py [split/system_bios_F000.bin] [out/system_bios_F000.lst]
        python tools/disasm_bios.py --module A400:0003:FA40 split/system_bios_F000.bin out/module_FA40.lst

--module START:ENTRY:SEG disassembles an embedded, separately-ORGed module that
starts at F000:START and is entered at SEG:ENTRY (SEG*16 = F0000h + START).

Follows code from the reset vector, the POST entry, the ROM interrupt vector
table at F000:FEF3 and the IBM-compatible fixed entry points. Anything not
reached is emitted as data (strings, or db rows). Addresses are 16-bit offsets
inside segment F000 and wrap at 64 KB like real-mode IP does.
"""
import re
import struct
import sys
from collections import defaultdict

import capstone
from capstone import x86

args = sys.argv[1:]
MODULE = None
if args and args[0] == "--module":
    MODULE = [int(x, 16) for x in args[1].split(":")]
    args = args[2:]
SRC = args[0] if len(args) > 0 else "split/system_bios_F000.bin"
DST = args[1] if len(args) > 1 else "out/system_bios_F000.lst"
ROM = FULL = open(SRC, "rb").read()
assert len(ROM) == 0x10000
SEGNAME = "F000"
if MODULE:
    MOD_START, MOD_ENTRY, MOD_SEG = MODULE
    assert MOD_SEG * 16 == 0xF0000 + MOD_START
    SEGNAME = "%04X" % MOD_SEG

# Embedded modules with their own segment base; excluded from the main listing.
MODULES = [
    # (start, end, segment, entry, name)
    (0xA400, 0xE000, 0xFA40, 0x0003, "setup_module"),
]

# IBM PC/AT compatibility entry points (fixed offsets in F000).
FIXED = {
    0xE05B: "POST_entry", 0xE2C3: "NMI_int02", 0xE6F2: "INT19_boot",
    0xE739: "INT14_serial", 0xE82E: "INT16_keyboard", 0xE987: "INT09_kbd_irq",
    0xEC59: "INT13_diskette", 0xEF57: "INT0E_fdc_irq", 0xEFD2: "INT17_printer",
    0xF065: "INT10_video", 0xF841: "INT12_memsize", 0xF84D: "INT11_equipment",
    0xF859: "INT15_system", 0xFE6E: "INT1A_timeofday", 0xFEA5: "INT08_timer",
    0xFF53: "dummy_iret", 0xFF54: "INT05_printscreen", 0xFFF0: "reset_vector",
}
DATA_LABELS = {
    0xE729: "baud_rate_table", 0xEFC7: "diskette_param_table",
    0xF0A4: "video_param_table", 0xFA6E: "font_8x8_lower", 0xFEF3: "rom_vector_table",
    0xFFF5: "rom_date", 0xFFFE: "model_byte", 0xFFFF: "rom_checksum",
}
# Known data areas the heuristics must not treat as code or pointer tables.
DATA_RANGES = [
    (0x2224, 0x2247, "chipset_init_table"),   # count word + (index,data) pairs -> ports 22h/24h
    (0xE000, 0xE05B, "copyright_text"),
    (0xE3FE, 0xE6F2, "fixed_disk_param_tables"),
    (0xFA6E, 0xFE6E, "font_8x8_lower"),
]
if MODULE:
    MOD_END = [m[1] for m in MODULES if m[0] == MOD_START][0]
    ROM = ROM[MOD_START:MOD_END] + bytes(0x10000 - (MOD_END - MOD_START))
else:
    for lo, hi, seg, ent, name in MODULES:
        DATA_RANGES.append((lo, hi, "%s_%04X (see out/module_%04X.lst)" % (name, seg, seg)))
VEC_NAMES = ["INT08", "INT09", "INT0A", "INT0B", "INT0C", "INT0D", "INT0E", "INT0F",
             "INT10", "INT11", "INT12", "INT13", "INT14", "INT15", "INT16", "INT17",
             "INT18", "INT19", "INT1A", "INT1B", "INT1C", "INT1D", "INT1E", "INT1F"]

PORTS = {
    0x20: "PIC1 cmd", 0x21: "PIC1 mask", 0xA0: "PIC2 cmd", 0xA1: "PIC2 mask",
    0x40: "PIT ch0", 0x41: "PIT ch1", 0x42: "PIT ch2", 0x43: "PIT mode",
    0x60: "KBC data", 0x61: "port B / NMI ctl", 0x64: "KBC status/cmd",
    0x70: "CMOS index/NMI", 0x71: "CMOS data", 0x80: "POST code",
    0x92: "fast A20/reset", 0xF0: "FPU clear busy", 0xF1: "FPU reset",
    0x22: "chipset index", 0x23: "chipset data?", 0x24: "chipset data (see chipset_init_table)",
    0x3F2: "FDC DOR", 0x3F4: "FDC MSR", 0x3F5: "FDC data", 0x3F7: "FDC DIR/CCR",
    0x1F0: "IDE data", 0x1F1: "IDE err/feat", 0x1F2: "IDE seccnt", 0x1F3: "IDE sector",
    0x1F4: "IDE cyl lo", 0x1F5: "IDE cyl hi", 0x1F6: "IDE drv/head", 0x1F7: "IDE status/cmd",
    0x3F6: "IDE dev ctl", 0x3D4: "CRTC idx (color)", 0x3B4: "CRTC idx (mono)",
    0x378: "LPT1", 0x278: "LPT2", 0x3F8: "COM1", 0x2F8: "COM2",
}
for i in range(0x00, 0x10):
    PORTS.setdefault(i, "DMA1")
for i in range(0x81, 0x90):
    PORTS.setdefault(i, "DMA page")
for i in range(0xC0, 0xE0):
    PORTS.setdefault(i, "DMA2")

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
md.detail = True

insns = {}                 # offset -> capstone insn
labels = {}                # offset -> name
xrefs = defaultdict(set)   # target -> {from}
calls = set()
jump_tables = {}           # table offset -> count
work = []


def add_code(target, frm=None, is_call=False, name=None):
    target &= 0xFFFF
    if frm is not None:
        xrefs[target].add(frm)
    if is_call:
        calls.add(target)
    if name:
        labels[target] = name
    if target not in insns:
        work.append(target)


def decode_at(off):
    # Decode from a 16-byte window; a window crossing FFFF is wrapped.
    window = (ROM + ROM[:16])[off:off + 16]
    for i in md.disasm(window, off, 1):
        return i
    return None


_inline_cache = {}
_inline_base = {}     # callee -> constant added to its inline word (e.g. string table base)
inline_str_base = {}  # inline operand offset -> that constant


def inline_arg_size(callee):
    """Bytes of inline data a callee skips after its call site.

    Recognises prologues like `pusha; push ds; push es; mov bp, sp; ...;
    add word ptr [bp + 14h], 2` that bump their own return address."""
    if callee in _inline_cache:
        return _inline_cache[callee]
    size, depth, bp_depth, a, str_base = 0, 0, None, callee, None
    for _ in range(24):
        ins = decode_at(a)
        if ins is None:
            break
        t = "%s %s" % (ins.mnemonic, ins.op_str)
        if ins.mnemonic in ("pushaw", "pusha"):
            depth += 16
        elif ins.mnemonic in ("push", "pushfw", "pushf") and bp_depth is None:
            depth += 2
        elif t == "mov bp, sp":
            bp_depth = depth
        elif re.match(r"add si, 0x[0-9a-f]+$", t) and bp_depth is not None:
            str_base = int(t[8:], 16)
        elif bp_depth is not None:
            m = re.match(r"(add|inc) word ptr \[bp(?: \+ (0x[0-9a-f]+|\d+))?\](?:, (0x[0-9a-f]+|\d+))?$", t)
            if m and int(m.group(2) or "0", 0) == bp_depth:
                size = 1 if m.group(1) == "inc" else int(m.group(3), 0)
                break
        if ins.mnemonic in ("ret", "retf", "iret", "jmp"):
            break
        a = (a + ins.size) & 0xFFFF
    _inline_cache[callee] = size
    _inline_base[callee] = str_base
    return size


def branch_target(i):
    op = i.operands[0] if i.operands else None
    if op is not None and op.type == x86.X86_OP_IMM:
        return op.imm & 0xFFFF
    return None


def lookback(addr, count=10):
    """Previous instructions in straight-line order (best effort)."""
    seq = []
    for _ in range(count):
        prev = [a for a in range(max(0, addr - 8), addr) if a in insns and a + insns[a].size == addr]
        if not prev:
            break
        addr = prev[0]
        seq.append(insns[addr])
    return seq


def try_jump_table(i):
    """Handle `jmp/call word ptr cs:[reg+table]` style dispatch."""
    if not i.operands or i.operands[0].type != x86.X86_OP_MEM:
        return
    m = i.operands[0].mem
    if i.operands[0].size != 2 or m.base == 0 and m.index == 0:
        return
    if m.segment != x86.X86_REG_CS:
        return
    tbl = m.disp & 0xFFFF
    limit = None
    reg = i.reg_name(m.base) if m.base else i.reg_name(m.index)
    for p in lookback(i.address):
        ops = p.operands
        if p.mnemonic in ("mov", "add") and len(ops) == 2 and ops[0].type == x86.X86_OP_REG                 and p.reg_name(ops[0].reg) == reg and ops[1].type == x86.X86_OP_IMM and tbl == 0:
            tbl = ops[1].imm & 0xFFFF
        if p.mnemonic == "cmp" and len(ops) == 2 and ops[1].type == x86.X86_OP_IMM and limit is None:
            limit = ops[1].imm + 1
        # `mov cx, word ptr cs:[count]` feeding a scan that indexes the table
        m_cnt = re.match(r"mov cx, word ptr cs:\[0x([0-9a-f]+)\]$", "%s %s" % (p.mnemonic, p.op_str))
        if m_cnt and limit is None:
            cnt = struct.unpack_from("<H", ROM, int(m_cnt.group(1), 16))[0]
            if 0 < cnt <= 64:
                limit = cnt
    if not (0x100 <= tbl <= 0xFFF0):
        return
    n = 0
    while n < (limit if limit and limit <= 64 else 64):
        p = tbl + 2 * n
        if p + 2 > 0x10000 or p in insns:
            break
        tgt = struct.unpack_from("<H", ROM, p)[0]
        if tgt < 0x0100 or tgt in (0xFFFF, 0x0000):
            break
        # Stop when entries stop looking like plausible code.
        probe = decode_at(tgt)
        if probe is None:
            break
        n += 1
    if n >= 2:
        jump_tables[tbl] = n
        for k in range(n):
            add_code(struct.unpack_from("<H", ROM, tbl + 2 * k)[0], i.address)


def run():
    while work:
        off = work.pop()
        while off not in insns:
            if any(lo <= off < hi for lo, hi, _ in DATA_RANGES):
                flow_into_data.add(off)
                break
            i = decode_at(off)
            if i is None:
                labels.setdefault(off, "bad_decode_%04X" % off)
                break
            insns[off] = i
            nxt = (off + i.size) & 0xFFFF
            g = set(i.groups)
            mn = i.mnemonic
            if mn.startswith("loop") and capstone.CS_GRP_JUMP not in g:
                t = branch_target(i)
                if t is not None:
                    add_code(t, off)
                off = nxt
            elif capstone.CS_GRP_JUMP in g and not (mn == "ljmp" and len(i.operands) == 2):
                t = branch_target(i)
                if t is not None:
                    add_code(t, off)
                else:
                    try_jump_table(i)
                if mn in ("jmp", "ljmp"):
                    break
                off = nxt
            elif capstone.CS_GRP_CALL in g and mn != "lcall":
                t = branch_target(i)
                if t is not None:
                    add_code(t, off, is_call=True)
                    n_inline = inline_arg_size(t)
                    if n_inline:
                        inline_args[nxt] = n_inline
                        if _inline_base.get(t) is not None:
                            inline_str_base[nxt] = _inline_base[t]
                        nxt = (nxt + n_inline) & 0xFFFF
                else:
                    try_jump_table(i)
                off = nxt
            elif mn in ("ljmp", "lcall") and len(i.operands) == 2:
                # Immediate far pointer seg:off -> offset in our segment if it lands here.
                seg, fo = i.operands[0].imm, i.operands[1].imm
                lin = seg * 16 + fo - (MOD_SEG * 16 if MODULE else 0xF0000)
                far_refs[off] = "%04X:%04X" % (seg, fo)
                if 0 <= lin < 0x10000:
                    add_code(lin, off, is_call=(mn == "lcall"))
                if mn == "ljmp":
                    break
                off = nxt
            elif mn in ("ret", "retf", "iret", "iretd", "hlt") or mn.startswith("ret"):
                break
            else:
                # ROM-stack call: `mov sp, X` then `jmp sub`; sub's RET pops [X].
                # Constant stored into an interrupt-vector slot -> ISR entry point.
                m_iv = re.match(r"mov word ptr (?:[a-z]s:)?\[0x([0-9a-f]+)\], 0x([0-9a-f]+)$", mn + " " + i.op_str)
                if m_iv:
                    slot, tgt = int(m_iv.group(1), 16), int(m_iv.group(2), 16)
                    if slot < 0x400 and slot % 4 == 0 and 0x100 <= tgt < 0xFFF0                             and not any(lo <= tgt < hi for lo, hi, _ in DATA_RANGES):
                        add_code(tgt, off)
                        labels.setdefault(tgt, "isr_INT%02X_%04X" % (slot // 4, tgt))
                m_sp = re.match(r"(?:mov sp, |lea sp, \[)0x([0-9a-f]+)\]?$", mn + " " + i.op_str)
                if m_sp:
                    x = int(m_sp.group(1), 16) & 0xFFFF
                    if 0x100 <= x < 0xFFFE:
                        ret = struct.unpack_from("<H", ROM, x)[0]
                        if ret == x + 2:
                            rom_stack[x] = ret
                            add_code(ret, off, name="romret_%04X" % ret)
                off = nxt


rom_stack = {}
far_refs = {}
inline_args = {}          # offset -> size of inline operand following a call
flow_into_data = set()

# Seeds.
if MODULE:
    FIXED, VEC_NAMES, DATA_LABELS = {MOD_ENTRY: "module_entry"}, [], {0: "module_header"}
    DATA_RANGES = [(0, 3, "module_header"), (MOD_END - MOD_START, 0x10000, "outside_module")]
for off, name in FIXED.items():
    if ROM[off] != 0x00:
        add_code(off, name=name)
for k, name in enumerate(VEC_NAMES):  # noqa: B007
    tgt = struct.unpack_from("<H", ROM, 0xFEF3 + 2 * k)[0]
    if tgt:
        add_code(tgt)
        labels.setdefault(tgt, name + "_handler")
# AT slave-PIC vector table (INT 70h-77h) at F000:FF23.
for k in range(0 if MODULE else 8):
    tgt = struct.unpack_from("<H", ROM, 0xFF23 + 2 * k)[0]
    if tgt:
        add_code(tgt)
        labels.setdefault(tgt, "INT%02X_handler" % (0x70 + k))
run()


def build_owner():
    own = [None] * 0x10000
    for lo, hi, _ in DATA_RANGES:
        for a in range(lo, hi):
            own[a] = -1
    for a, ins in insns.items():
        for k in range(ins.size):
            own[(a + k) & 0xFFFF] = a
    return own


def trial_decode(tgt, own):
    """Return the list of instruction starts if tgt looks like real code: it
    decodes cleanly up to a RET/JMP (or into already-known code) without
    landing mid-instruction. Returns None otherwise."""
    a, path = tgt, []
    while len(path) < 80:
        if own[a] is not None:
            return path if own[a] == a and path else None
        if any(lo <= a < hi for lo, hi, _ in DATA_RANGES):
            return None
        ins = decode_at(a)
        if ins is None or ins.mnemonic in ("arpl", "bound", "into", "hlt", "lock", "wait", "int3",
                                            "les", "lds", "insb", "insw", "outsb", "outsw", "salc"):
            return None
        for k in range(1, ins.size):
            if own[(a + k) & 0xFFFF] is not None:
                return None
        path.append(a)
        if ins.mnemonic in ("ret", "retf", "iret", "jmp", "ljmp"):
            return path if len(path) >= 3 else None
        a = (a + ins.size) & 0xFFFF
    return None


# Pointer tables living in data: runs of >=3 words that each point at clean code.
ptr_tables = {}
while True:
    owner = build_owner()
    found = []
    p = 0x100
    while p < 0xFFF0:
        if owner[p] is not None or p in rom_stack:
            p += 1
            continue
        run_len, q, paths = 0, p, []
        while q < 0xFFF0 and owner[q] is None and owner[q + 1] is None:
            tgt = struct.unpack_from("<H", ROM, q)[0]
            path = trial_decode(tgt, owner) if 0x200 <= tgt < 0xFFF0 else None
            if path is None:
                break
            paths.append(path)
            run_len += 1
            q += 2
        # Entries of a real handler table don't fall through into each other.
        starts = {pa[0] for pa in paths}
        if any(a in starts for pa in paths for a in pa[1:]):
            run_len = 0
        if run_len >= 3:
            found.append((p, run_len))
            p = q
        else:
            p += 1
    new = [(t, n) for t, n in found if t not in ptr_tables]
    if not new:
        break
    for t, n in new:
        ptr_tables[t] = n
        for k in range(n):
            tgt = struct.unpack_from("<H", ROM, t + 2 * k)[0]
            add_code(tgt, t + 2 * k)
            labels.setdefault(tgt, "ptr_%04X" % tgt)
    run()
    # A table may have been swallowed by newly found code; drop those.
    owner = build_owner()
    for t in list(ptr_tables):
        if any(owner[t + k] is not None for k in range(2 * ptr_tables[t])):
            del ptr_tables[t]
jump_tables.update(ptr_tables)

owner = [None if o == -1 else o for o in build_owner()]
for lo, hi, name in DATA_RANGES:
    DATA_LABELS.setdefault(lo, name)
if not MODULE:
    for lo, hi, seg, ent, name in MODULES:
        labels[lo + ent] = "%s_entry" % name
for t in xrefs:
    if t not in labels:
        labels[t] = ("sub_%04X" if t in calls else "loc_%04X") % t
labels.update({k: v for k, v in DATA_LABELS.items()})
for x in rom_stack:
    labels.setdefault(x, "romstack_%04X" % x)
for tbl, n in jump_tables.items():
    labels.setdefault(tbl, "jumptable_%04X" % tbl)

# Immediate operands that point at printable strings -> annotate.
STR_RE = re.compile(rb"[\x20-\x7e\r\n]{4,}")


def string_at(off):
    m = STR_RE.match(ROM, off)
    if m and len(m.group().strip()) >= 4:
        s = m.group().decode("ascii").replace("\r", "\\r").replace("\n", "\\n")
        return s[:60]
    return None


def comment_for(i):
    notes = []
    mn = i.mnemonic
    if mn in ("in", "out"):
        imm = [o.imm for o in i.operands if o.type == x86.X86_OP_IMM]
        if imm and imm[0] in PORTS:
            notes.append("port %02Xh: %s" % (imm[0], PORTS[imm[0]]))
        elif "dx" in i.op_str:
            notes.append("port in DX")
    if mn == "int":
        notes.append("BIOS/DOS service INT %s" % i.op_str)
    # String hints only where the immediate is plausibly a pointer (not a segment/count).
    ptr_dst = mn == "mov" and re.match(r"(si|di|bp), 0x", i.op_str)
    for o in i.operands if ptr_dst else ():
        if o.type == x86.X86_OP_IMM and o.size == 2 and 0x100 <= o.imm < 0xFFF0:
            s = string_at(o.imm)
            if s:
                notes.append('-> "%s"' % s)
    return "; ".join(notes)


def fmt_insn(i):
    text = "%s %s" % (i.mnemonic, i.op_str)
    if i.address in far_refs:
        lin = (int(far_refs[i.address][:4], 16) * 16 + int(far_refs[i.address][5:], 16)
               - (MOD_SEG * 16 if MODULE else 0xF0000))
        return "%s far %s   ; %s" % (i.mnemonic, labels.get(lin, far_refs[i.address]) if 0 <= lin < 0x10000 else far_refs[i.address], far_refs[i.address])
    t = branch_target(i) if (capstone.CS_GRP_JUMP in i.groups or capstone.CS_GRP_CALL in i.groups
                             or i.mnemonic.startswith("loop")) else None
    if t is not None and t in labels:
        text = "%s %s" % (i.mnemonic, labels[t])
    return text.strip()


out = []
code_bytes = sum(i.size for i in insns.values())
seg_size = (MOD_END - MOD_START) if MODULE else 0x10000
if MODULE:
    out.append("; NCR 486 BIOS embedded Setup module, F000:%04X-%04X, assembled ORG 0, runs as %04X:xxxx"
               % (MOD_START, MOD_END - 1, MOD_SEG))
    out.append("; Entered by far call %04X:%04X from POST; data segment is RAM 0070:0000."
               % (MOD_SEG, MOD_ENTRY))
else:
    out.append("; NCR 486 system BIOS, segment F000 (from image offset 10000h)")
out.append("; Image: ROM date %s, model byte %02Xh, checksum byte %02Xh (64K sum must be 00h)"
           % (FULL[0xFFF5:0xFFFD].decode(), FULL[0xFFFE], FULL[0xFFFF]))
out.append("; %d instructions, %d code bytes identified (%.1f%% of segment)"
           % (len(insns), code_bytes, 100.0 * code_bytes / seg_size))
out.append("; Columns: segment:offset  bytes  instruction  ; comment")
out.append("")

off = 0
while off < seg_size:
    if off in labels:
        refs = sorted(xrefs.get(off, ()))
        rs = ""
        if refs:
            rs = "   ; xref " + " ".join("%04X" % r for r in refs[:8]) + (" ..." if len(refs) > 8 else "")
        out.append("")
        out.append("%s:%s" % (labels[off], rs))
    if owner[off] == off:
        i = insns[off]
        c = comment_for(i)
        line = "%s:%04X  %-20s %-40s" % (SEGNAME, off, i.bytes.hex(), fmt_insn(i))
        out.append(line + ("; " + c if c else ""))
        off += i.size
        continue
    if owner[off] is not None:   # overlapping decode; skip byte
        off += 1
        continue
    # Data run: until next code byte or label.
    end = off + 1
    while end < seg_size and owner[end] is None and end not in labels:
        end += 1
    if off in inline_args and owner[off] is None:
        n = inline_args[off]
        val = int.from_bytes(ROM[off:off + n], "little")
        note = ""
        if n == 2 and inline_str_base.get(off):
            sa = (val + inline_str_base[off]) & 0xFFFF
            note = "  -> %04Xh" % sa
            s_ = string_at(sa) or string_at(sa + 1) or string_at(sa + 2) or string_at(sa + 3)
            if s_:
                note += ' "%s"' % s_
        out.append("%s:%04X  %s %0*Xh   ; inline argument%s" % (SEGNAME, off, "dw" if n == 2 else "db", 2 * n, val, note))
        off += n
        continue
    if off in rom_stack:
        out.append("%s:%04X  dw %s   ; ROM-stack return address" % (SEGNAME, off, labels[rom_stack[off]]))
        off += 2
        continue
    if off in jump_tables:
        k = 0
        while k < jump_tables[off] and owner[off + 2 * k] is None and owner[off + 2 * k + 1] is None:
            tgt = struct.unpack_from("<H", ROM, off + 2 * k)[0]
            out.append("%s:%04X  dw %s" % (SEGNAME, off + 2 * k, labels.get(tgt, "%04Xh" % tgt)))
            k += 1
        if k:
            off += 2 * k
            continue
    p = off
    while p < end:
        m = STR_RE.match(ROM, p, end)
        if m and len(m.group()) >= 6:
            s = m.group().decode("ascii").replace("\r", "\\r").replace("\n", "\\n")
            out.append('%s:%04X  db "%s"' % (SEGNAME, p, s.replace('"', '\\"')))
            p = m.end()
            continue
        if ROM[p] == 0x00 or ROM[p] == 0xFF:
            q = p
            while q < end and ROM[q] == ROM[p]:
                q += 1
            if q - p >= 16:
                out.append("%s:%04X  db %d dup(%02Xh)   ; free/padding?" % (SEGNAME, p, q - p, ROM[p]))
                p = q
                continue
        q = min(p + 16, end)
        m = STR_RE.search(ROM, p, q)
        if m and m.start() > p and len(m.group()) >= 6:
            q = m.start()
        out.append("%s:%04X  db %s" % (SEGNAME, p, ",".join("%02Xh" % b for b in ROM[p:q])))
        p = q
    off = end

import os
os.makedirs(os.path.dirname(DST) or ".", exist_ok=True)
open(DST, "w").write("\n".join(out) + "\n")
module_entries = {lo + ent: name for lo, hi, seg, ent, name in MODULES} if not MODULE else {}
for a in sorted(flow_into_data):
    if a in module_entries:
        continue
    print("warning: code flow reaches known data at %04X (from %s)"
          % (a, " ".join("%04X" % r for r in sorted(xrefs.get(a, ())))))
print("%d instructions, %d code bytes (%.1f%%), %d labels, %d jump tables -> %s"
      % (len(insns), code_bytes, 100.0 * code_bytes / seg_size, len(labels), len(jump_tables), DST))
