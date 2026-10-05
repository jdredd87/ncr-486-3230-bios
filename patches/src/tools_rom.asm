; NCR 3230 Tools: a utilities extension in the unused 32 KB at E800:0000,
; plus the small hooks in the system BIOS that use it.
;
; The extension lives in the ROM chip's otherwise empty E8000-EFFFF area
; (image offset 08000h). Before using it, the BIOS checks for the "NCRX"
; signature and a 16-bit checksum over the whole extension; if the board
; does not map that area, every feature below simply stays off and POST
; behaves as before.
;
; At the end of POST:
;   * F10 opens the Tools menu, F8 opens the boot menu (type-ahead, like F1).
;   * With the fancy boot screen on: a start-up chime instead of the single
;     beep, and a system summary box for 3 s (any key skips it).
; During POST: "PROCESSOR SPEED" shows the measured clock instead of the
; never-written CMOS byte 43h.
; INT 19h (boot): a one-shot boot device chosen in the boot menu: A:, C:,
; or a bootable (El Torito) CD-ROM, with its own ATAPI driver and INT 13h.
;
; Tools menu: system information, drives (IDE model names for disks and
; CD-ROMs), memory map with option ROMs, memory test (conventional and all
; extended memory, flat real mode), CMOS viewer, NCR's built-in floppy
; drive test (hidden behind Ctrl-D in the stock BIOS), boot menu.

; ------------------------------------------------------------------ addresses

EXT_SEG     equ 0xE800
VARSEG      equ 0x0500              ; RAM for variables/buffers: linear 05000-055FF
STACK_TOP   equ 0x7000              ; private stack 0000:7000 (pre-boot RAM)
G_BASE      equ 0xF860              ; glue jump table in F000
G_FDTEST    equ G_BASE              ; far: NCR floppy drive test
G_POSTEND   equ G_BASE + 3
G_KEYS      equ G_BASE + 6
G_MHZ       equ G_BASE + 9
G_BOOT      equ G_BASE + 12
G_HDINIT    equ G_BASE + 15
X_TOOLS     equ 0x000A              ; extension entry points (far)
X_POSTEND   equ 0x000D
X_MHZ       equ 0x0010
X_BOOT      equ 0x0013
X_HDINIT    equ 0x0016
X_CAPTURE   equ 0x0019
ROM19       equ 0xEF06              ; F000 shadow: an option ROM's INT 19h (dword) ...
ROM19_OK    equ 0xEF0A              ; ... and 1 if it is valid
BOOT_STATE  equ 0x04F3              ; 0000:04F3 during INT 19h: 0 undecided, 'E' boot order
                                    ; done, 'R' option ROM chosen, 'P' option ROM had its turn
ORDER_INDEX equ 0x4A                ; CMOS 4Ah-4Dh: saved boot order ('O', 4 device nibbles, check)
ORDER_SIG   equ 'O'
ORDER_OFF   equ 0x08                ; device nibble bit 3: in the list, but switched off
ORDER_DEFAULT equ 0x0B020104        ; editor start: option ROM, A:, C: on; CD-ROM off
BOOT_NEXT   equ 0x04F4              ; 0000:04F4 during INT 19h: next boot order position
FLAG_INDEX  equ 0xC8                ; CMOS 48h: fancy boot screen (A5h = off)
SUMMARY_TICKS equ 146               ; end-of-POST summary: 8 s
BEEP        equ 0x4F7D
PRINT2      equ 0x4DD2              ; prints AX as two digits + " MHz"
NCR_FDTEST  equ 0x0C00
INT19_ORIG  equ 0xE066
DISK_INIT   equ 0x9062              ; POST hard disk init
BOOT_MAGIC  equ 0x424E              ; "NB" at 0000:04F0 (inter-application area)
CD_DRIVE    equ 0xE0                ; boot choice "CD-ROM"; also the no-emulation drive number
ROM_CHOICE  equ 0xFE                ; boot choice "option ROM boot"

; ------------------------------------------------------------------ F000 hooks

;@ F000:3891 max=3
;; "PROCESSOR SPEED: nn MHz": was "call 4DD2" with AX = CMOS 43h
    call G_MHZ

;@ F000:47B6 max=6
;; end of POST: was "mov bx,350h / call 4F7D" (one beep)
    call G_POSTEND
    nop
    nop
    nop

;@ F000:47CB max=7
;; type-ahead key check: was "cmp ax,3B00h / jne 4806"; F1 still goes to Setup
    call G_KEYS
    nop
    nop
    nop
    nop

;@ F000:436E max=3
;; POST: was "call 9062" (hard disk init); now also sets up large disks
    call G_HDINIT

;@ F000:EF06 max=5 free
;; reserved: an option ROM's INT 19h (e.g. the PicoMEM's), saved at the end
;; of POST into the shadowed F000 (see capture19)
    times 5 db 0

;@ F000:EED6 max=0x30 free
;; reserved: large-disk (LBA) tables and the chain to the stock INT 13h,
;; written at POST into the shadowed F000 (see hd_setup)
    times 0x30 db 0

;@ F000:E6F2 max=3
;; INT 19h entry: was "jmp E066"
    jmp G_BOOT

;@ F000:F860 max=0x200 free
;; glue: checks the extension and calls into it; falls back to the stock code
    jmp near g_fdtest
    jmp near g_postend
    jmp near g_keys
    jmp near g_mhz
    jmp near g_boot
    jmp near g_hdinit

; CF=0 if E800:0000 holds a valid extension (signature, size, checksum).
ext_ok:
    push ax
    push bx
    push cx
    push si
    push ds
    mov ax, EXT_SEG
    mov ds, ax
    cmp word [0], 'NC'
    jne .bad
    cmp word [2], 'RX'
    jne .bad
    mov cx, [4]
    cmp cx, 8
    jb .bad
    cmp cx, 0x8000
    ja .bad
    test cl, 1
    jnz .bad
    shr cx, 1
    xor si, si
    xor bx, bx
    cld
.sum:
    lodsw
    add bx, ax
    loop .sum
    test bx, bx
    jnz .bad
    clc
    jmp short .out
.bad:
    stc
.out:
    pop ds
    pop si
    pop cx
    pop bx
    pop ax
    ret

g_fdtest:                           ; far, from the extension
    pusha
    push ds
    push es
    call NCR_FDTEST
    pop es
    pop ds
    popa
    retf

g_postend:                          ; replaces the end-of-POST beep
    call ext_ok
    jc .beep
    call EXT_SEG:X_CAPTURE          ; an option ROM's INT 19h: the BIOS keeps the vector
    push ax
    pushf
    cli
    mov al, FLAG_INDEX
    out 0x70, al
    in al, 0x71
    popf
    cmp al, 0xA5
    pop ax
    je .beep
    call EXT_SEG:X_POSTEND
    ret
.beep:
    mov bx, 0x350
    jmp BEEP

g_keys:                             ; AX = key waiting (peeked by POST)
    push bp
    mov bp, sp
    cmp ax, 0x3B00                  ; F1: Setup, as before
    jne .k1
    mov word [bp+2], 0x47D2
    pop bp
    ret
.k1:
    cmp ax, 0x4400                  ; F10: Tools
    je .tools
    cmp ax, 0x4200                  ; F8: boot menu
    je .tools
.other:
    mov word [bp+2], 0x4806
    pop bp
    ret
.tools:
    call ext_ok
    jc .other
    pusha
    push ds
    push es
    mov bx, ax
    xor ax, ax
    int 0x16                        ; take the key
    xor ax, ax
    cmp bx, 0x4200
    jne .go
    inc ax                          ; page 1 = boot menu
.go:
    call EXT_SEG:X_TOOLS
    pop es
    pop ds
    popa
    mov word [bp+2], 0x47FE         ; continue POST after the key check
    pop bp
    ret

g_mhz:                              ; AX = CMOS 43h (POST's stored speed)
    call ext_ok
    jc .print
    push ax
    call EXT_SEG:X_MHZ              ; AX = measured MHz, 0 if it failed
    test ax, ax
    jz .old
    add sp, 2
    jmp short .print
.old:
    pop ax
.print:
    cmp ax, 100
    jb .two
    push ax
    push bx
    mov bl, 100
    div bl                          ; AL = hundreds, AH = rest
    push ax
    add al, '0'
    mov ah, 0x0E
    mov bx, 0x0007
    int 0x10
    pop ax
    mov al, ah
    xor ah, ah
    pop bx
    add sp, 2
.two:
    jmp PRINT2

g_hdinit:                           ; POST disk init, then large-disk (LBA) mode
    call DISK_INIT
    call ext_ok
    jc .x
    call EXT_SEG:X_HDINIT
.x:
    ret

g_boot:                             ; INT 19h
    call ext_ok
    jc .normal
    call EXT_SEG:X_BOOT             ; boots the boot menu's choice; otherwise returns
    push ds
    push 0
    pop ds
    cmp byte [BOOT_STATE], 'R'      ; boot menu: the option ROM's own boot
    je .rom
    cmp byte [BOOT_STATE], 0        ; nothing decided: an option ROM goes first
    jne .bios
.rom:
    cmp byte [cs:ROM19_OK], 1
    jne .bios
    mov byte [BOOT_STATE], 'P'      ; once: its fall-back calls INT 19h again
    pop ds
    jmp far [cs:ROM19]
.bios:
    pop ds
.normal:
    jmp INT19_ORIG

; ================================================================== extension

;@ E800:0000 max=0x8000 ff
;; NCR 3230 Tools extension (runs as E800:xxxx)
bits 16
ext_start:
    db "NCRX"
    dw ext_end - ext_start          ; size covered by the checksum
    dw 0                            ; checksum, filled in by fix_checksum.py
    db 1, 0                         ; version
    jmp near tools_entry            ; 000A
    jmp near postend_entry          ; 000D
    jmp near mhz_entry              ; 0010
    jmp near boot_entry             ; 0013
    jmp near hdinit_entry           ; 0016
    jmp near capture_entry          ; 0019

; ------------------------------------------------------------------ variables (GS = VARSEG)
V_VSEG      equ 0x00
V_MONO      equ 0x02
V_ATTR      equ 0x03
V_ROW       equ 0x04
V_COL       equ 0x05
V_LMARG     equ 0x06
V_SEL       equ 0x07
V_SAVESS    equ 0x08
V_SAVESP    equ 0x0A
V_ARG       equ 0x0C
V_RET       equ 0x0E
V_SIG       equ 0x10
V_CPUID     equ 0x14
V_FPU       equ 0x15
V_MHZV      equ 0x16
V_VEND      equ 0x18                ; 13 bytes
V_ERRS      equ 0x28
V_PASS      equ 0x2C
V_TEST      equ 0x2E
V_NLOG      equ 0x2F
V_START     equ 0x30
V_END       equ 0x34
V_ADDR      equ 0x38
V_PAT       equ 0x3C
V_EXP       equ 0x40
V_TMP       equ 0x44
V_IDTYPE    equ 0x48                ; 2 bytes
V_STOP      equ 0x4A
V_LOG       equ 0x50                ; 6 entries x 12 bytes (addr, expected, read)
V_IDMB      equ 0x98                ; 2 dwords
V_IDNAME    equ 0xA0                ; 2 x 41 bytes
V_IDFW      equ 0xF4                ; 2 x 9 bytes
V_NUM       equ 0x108               ; 16 bytes
V_TC        equ 0x120               ; hard disk setup: working types for C: and D:
V_TD        equ 0x121
V_OC        equ 0x122               ; types as found in CMOS
V_OD        equ 0x123
V_UCYL      equ 0x124               ; user type (type 1): word
V_UHD       equ 0x126
V_USPT      equ 0x127
V_IDGEO     equ 0x128               ; 2 x (cylinders, heads, sectors) words from IDENTIFY
V_BOOTQ     equ 0x174               ; 1 while the boot order runs: give up on a CD quickly
V_ORDER     equ 0x178               ; 4 bytes: boot order devices (0 none, 1 A:, 2 C:, 3 CD, 4 ROM)
V_OSEL      equ 0x17C
V_OTMP      equ 0x180               ; 4 bytes: the order as read from CMOS
V_IDBUF     equ 0x200               ; 512 bytes
V_TLOOP     equ 0x400               ; timing loop copied to RAM

; colours (mapped for monochrome by xlat)
A_BG        equ 0x17
A_BAR       equ 0x30
A_TITLE     equ 0x1E
A_LABEL     equ 0x1B
A_VALUE     equ 0x1F
A_DIM       equ 0x13
A_SEL       equ 0x3F
A_OK        equ 0x1A
A_BAD       equ 0x1C
A_BOX       equ 0x1B

%macro SAY 1+                       ; print an inline string with escapes
    call say
    db %1, 0
%endmacro

; ------------------------------------------------------------------ entry/exit
; Each far entry switches to a private stack and keeps every register.
%macro ENTER 0
    push gs
    push ax
    mov ax, VARSEG
    mov gs, ax
    pop ax
    mov [gs:V_ARG], ax
    mov [gs:V_SAVESS], ss
    mov [gs:V_SAVESP], sp
    cli
    mov ss, [cs:zero_word]          ; keep every caller register for pushad
    mov sp, STACK_TOP
    sti
    pushad
    push ds
    push es
    push fs
    push cs
    pop ds
    cld
%endmacro

%macro LEAVE 0
    pop fs
    pop es
    pop ds
    popad
    cli
    mov ss, [gs:V_SAVESS]
    mov sp, [gs:V_SAVESP]
    sti
    pop gs
%endmacro

zero_word: dw 0

tools_entry:                        ; AX = 0 menu, 1 boot menu
    ENTER
    call ui_init
    call gather_cpu
    cmp word [gs:V_ARG], 1
    jne .menu
    call page_boot
    jmp short .done
.menu:
    call page_menu
.done:
    call ui_done
    LEAVE
    retf

postend_entry:
    ENTER
    call ui_init
    call chime
    call gather_cpu
    call page_summary
    LEAVE
    retf

mhz_entry:                          ; returns AX = MHz (0 = failed)
    ENTER
    call measure_mhz
    pop fs
    pop es
    pop ds
    popad
    mov ax, [gs:V_MHZV]             ; GS is still VARSEG here
    cli
    mov ss, [gs:V_SAVESS]
    mov sp, [gs:V_SAVESP]
    sti
    pop gs
    retf

boot_entry:                         ; returns (CF=1) when there is no override
    ENTER
    call boot_override
    push es
    push 0
    pop es
    cmp byte [es:BOOT_STATE], 'R'
    pop es
    je .out
    call boot_by_order
.out:
    LEAVE
    stc
    retf

; ------------------------------------------------------------------ screen library

ui_init:
    push ax
    push es
    mov ax, 0x40
    mov es, ax
    mov al, [es:0x49]
    mov word [gs:V_VSEG], 0xB800
    mov byte [gs:V_MONO], 0
    cmp al, 7
    jne .colour
    mov word [gs:V_VSEG], 0xB000
    mov byte [gs:V_MONO], 1
    jmp short .ok
.colour:
    cmp al, 2
    je .ok
    cmp al, 3
    je .ok
    mov ax, 0x0003                  ; graphics mode: switch to 80x25 text
    int 0x10
.ok:
    mov ah, 1
    mov cx, 0x2000                  ; hide the cursor
    int 0x10
    pop es
    pop ax
    ret

ui_done:
    mov ax, 0x0003
    cmp byte [gs:V_MONO], 0
    je .set
    mov al, 7
.set:
    int 0x10                        ; clean screen for booting
    ret

xlat:                               ; AH = attribute, mapped for monochrome
    cmp byte [gs:V_MONO], 0
    je .done
    test ah, 0x20                   ; cyan/grey bars -> reverse video
    jz .text
    test ah, 0x10
    jz .text
    mov ah, 0x70
    ret
.text:
    test ah, 0x08
    mov ah, 0x07
    jz .done
    mov ah, 0x0F
.done:
    ret

goto_rc:                            ; DH = row, DL = column
    mov [gs:V_ROW], dh
    mov [gs:V_COL], dl
    mov [gs:V_LMARG], dl
    ret

putc:                               ; AL at the current position, current attribute
    push ax
    push bx
    push di
    push es
    mov es, [gs:V_VSEG]
    movzx bx, byte [gs:V_ROW]
    imul bx, bx, 160
    movzx di, byte [gs:V_COL]
    shl di, 1
    add di, bx
    mov ah, [gs:V_ATTR]
    call xlat
    mov [es:di], ax
    inc byte [gs:V_COL]
    pop es
    pop di
    pop bx
    pop ax
    ret

puts:                               ; DS:SI, escapes: 1,a attr / 2,r,c position / 3 newline
    push ax
.next:
    lodsb
    or al, al
    jz .end
    cmp al, 1
    jne .p
    lodsb
    mov [gs:V_ATTR], al
    jmp short .next
.p:
    cmp al, 2
    jne .n
    lodsb
    mov [gs:V_ROW], al
    lodsb
    mov [gs:V_COL], al
    mov [gs:V_LMARG], al
    jmp short .next
.n:
    cmp al, 3
    jne .c
    inc byte [gs:V_ROW]
    mov al, [gs:V_LMARG]
    mov [gs:V_COL], al
    jmp short .next
.c:
    call putc
    jmp short .next
.end:
    pop ax
    ret

say:                                ; inline string after the call
    push bp
    mov bp, sp
    push si
    mov si, [bp+2]
    call puts
    mov [bp+2], si
    pop si
    pop bp
    ret

puts_gs:                            ; GS:SI, zero-terminated, no escapes
    push ax
.l:
    mov al, [gs:si]
    inc si
    or al, al
    jz .e
    call putc
    jmp short .l
.e:
    pop ax
    ret

spaces:                             ; CX blanks
    push ax
    mov al, ' '
.l:
    call putc
    loop .l
    pop ax
    ret

putdec:                             ; EAX unsigned decimal
    push eax
    push ebx
    push edx
    push si
    mov si, V_NUM + 15
    mov byte [gs:si], 0
    mov ebx, 10
.d:
    xor edx, edx
    div ebx
    add dl, '0'
    dec si
    mov [gs:si], dl
    test eax, eax
    jnz .d
    call puts_gs
    pop si
    pop edx
    pop ebx
    pop eax
    ret

puthex:                             ; EAX, CL = digits
    push eax
    push cx
    push dx
    movzx cx, cl
    mov dx, cx
    shl dx, 2
.rot:                               ; bring the top requested digit to the top
    cmp dx, 32
    je .go
    rol eax, 4
    add dx, 4
    jmp short .rot
.go:
    rol eax, 4
    push eax
    and al, 0x0F
    add al, '0'
    cmp al, '9'
    jbe .ok
    add al, 7
.ok:
    call putc
    pop eax
    loop .go
    pop dx
    pop cx
    pop eax
    ret

cls:                                ; whole screen blank in A_BG
    push ax
    push cx
    push di
    push es
    mov es, [gs:V_VSEG]
    mov ah, A_BG
    call xlat
    mov al, ' '
    xor di, di
    mov cx, 2000
    rep stosw
    pop es
    pop di
    pop cx
    pop ax
    ret

hline:                              ; row DH, columns DL.., CX cells of AL in V_ATTR
    call goto_rc
.l:
    call putc
    loop .l
    ret

frame:                              ; screen with top bar, title (SI) and help line (BX)
    call cls
    mov byte [gs:V_ATTR], A_BAR
    mov dx, 0x0000
    mov cx, 80
    mov al, ' '
    call hline
    mov dx, 0x0001
    call goto_rc
    SAY " NCR System 3230 ", 0xFA, " Tools"
    mov dx, 0x0032
    call goto_rc
    SAY "Enhanced by StevenC & Claude"
    mov dx, 0x1800
    mov cx, 80
    mov al, ' '
    call hline
    mov dx, 0x1801
    call goto_rc
    push si
    mov si, bx
    call puts
    pop si
    mov byte [gs:V_ATTR], A_TITLE
    mov dx, 0x0203
    call goto_rc
    call puts
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x0303
    mov cx, 74
    mov al, 0xC4
    call hline
    ret

label:                              ; row DH: label (SI) at column 3, value at column 25
    mov byte [gs:V_ATTR], A_LABEL
    mov dl, 3
    call goto_rc
    call puts
    mov byte [gs:V_ATTR], A_VALUE
    mov dl, 25
    mov [gs:V_COL], dl
    mov [gs:V_LMARG], dl
    ret

getkey:
    xor ax, ax
    int 0x16
    ret

wait_back:                          ; any key returns
    call getkey
    ret

; ------------------------------------------------------------------ small helpers

cmos_read:                          ; AL = register -> AL = value
    pushf
    cli
    or al, 0x80
    out 0x70, al
    in al, 0x71
    popf
    ret

chip_read:                          ; AL = chipset register -> AL = value
    pushf
    cli
    out 0x22, al
    in al, 0x24
    popf
    ret

delay_ms:                           ; CX milliseconds, counted on port 61h refresh toggles
    push ax
    push cx
    push dx
.ms:
    push cx
    mov cx, 66
    in al, 0x61
    and al, 0x10
    mov ah, al
.t:
    xor dx, dx
.same:
    in al, 0x61
    and al, 0x10
    cmp al, ah
    jne .flip
    dec dx
    jnz .same
.flip:
    mov ah, al
    loop .t
    pop cx
    loop .ms
    pop dx
    pop cx
    pop ax
    ret

tone:                               ; BX = PIT divisor, CX = milliseconds
    push ax
    mov al, 0xB6
    out 0x43, al
    mov al, bl
    out 0x42, al
    mov al, bh
    out 0x42, al
    in al, 0x61
    or al, 3
    out 0x61, al
    call delay_ms
    in al, 0x61
    and al, 0xFC
    out 0x61, al
    pop ax
    ret

chime:                              ; C6 E6 G6 C7
    push bx
    push cx
    mov bx, 1140
    mov cx, 70
    call tone
    mov bx, 905
    call tone
    mov bx, 761
    call tone
    mov bx, 570
    mov cx, 140
    call tone
    pop cx
    pop bx
    ret

; ------------------------------------------------------------------ CPU

gather_cpu:
    pushad
    mov byte [gs:V_CPUID], 0
    mov dword [gs:V_SIG], 0
    pushfd                          ; CPUID if the ID flag (bit 21) can be toggled
    pop eax
    mov ecx, eax
    xor eax, 0x200000
    push eax
    popfd
    pushfd
    pop eax
    push ecx
    popfd
    xor eax, ecx
    test eax, 0x200000
    jz .nocpuid
    mov byte [gs:V_CPUID], 1
    xor eax, eax
    cpuid
    mov [gs:V_VEND], ebx
    mov [gs:V_VEND+4], edx
    mov [gs:V_VEND+8], ecx
    mov byte [gs:V_VEND+12], 0
    mov eax, 1
    cpuid
    mov [gs:V_SIG], eax
.nocpuid:
    mov byte [gs:V_FPU], 0          ; FPU: FNINIT then FNSTSW must give 0
    mov eax, cr0
    test al, 0x0C                   ; EM or TS set: FPU instructions would trap
    jnz .nofpu
    mov word [gs:V_TMP], 0x5A5A
    fninit
    fnstsw [gs:V_TMP]
    cmp byte [gs:V_TMP], 0
    jne .nofpu
    mov byte [gs:V_FPU], 1
.nofpu:
    call measure_mhz
    popad
    ret

; Measure the core clock: 1000 x 32 "div bx" (24 clocks each on a 486) from RAM,
; timed with PIT channel 2. Result (rounded to a standard speed when close)
; in V_MHZV, 0 if the measurement makes no sense.
measure_mhz:
    pushad
    push es
    push ds
    mov word [gs:V_MHZV], 0
    mov ax, VARSEG                  ; copy the loop to RAM (ROM may be slow / uncached)
    mov es, ax
    mov di, V_TLOOP
    mov si, tloop
    mov cx, tloop_end - tloop
    rep movsb
    pushf
    cli
    in al, 0x61
    and al, 0xFC
    out 0x61, al
    mov al, 0xB0                    ; channel 2, lo/hi, mode 0
    out 0x43, al
    mov al, 0xFF
    out 0x42, al
    out 0x42, al
    in al, 0x61
    or al, 1                        ; gate on: counting starts
    out 0x61, al
    xor dx, dx
    mov ax, 1234
    mov bx, 7
    call VARSEG:V_TLOOP
    mov al, 0x80                    ; latch channel 2
    out 0x43, al
    in al, 0x42
    mov ah, al
    in al, 0x42
    xchg al, ah
    mov bx, ax
    in al, 0x61
    and al, 0xFC
    out 0x61, al
    popf
    mov cx, 0xFFFF
    sub cx, bx                      ; elapsed ticks at 1.193182 MHz
    cmp cx, 1500
    jb .done                        ; implausibly fast: give up
    movzx ecx, cx
    mov eax, 9211365                ; 772000 clocks x 1.193182 x 10
    xor edx, edx
    div ecx                         ; EAX = MHz x 10
    mov si, speeds                  ; snap to a standard speed within 6 %
.snap:
    mov bx, [cs:si]
    add si, 2
    test bx, bx
    jz .raw
    movzx ebx, bx
    mov edx, eax
    sub edx, ebx
    jns .pos
    neg edx
.pos:
    imul edx, edx, 100
    imul ecx, ebx, 6
    cmp edx, ecx
    ja .snap
    mov eax, ebx
.raw:
    add eax, 5
    xor edx, edx
    mov ecx, 10
    div ecx
    mov [gs:V_MHZV], ax
.done:
    pop ds
    pop es
    popad
    ret
speeds: dw 160, 200, 250, 330, 400, 500, 600, 660, 750, 800, 1000, 1200, 1330, 1500, 0

tloop:                              ; copied to VARSEG:V_TLOOP and called far
    mov cx, 1000
.l:
    times 32 div bx
    dec cx
    jnz .l
    retf
tloop_end:

cpu_name:                           ; prints the processor description
    cmp byte [gs:V_CPUID], 0
    jne .cpuid
    SAY "486"
    mov si, s_dx
    cmp byte [gs:V_FPU], 0
    jne .p
    mov si, s_sx
.p:
    call puts
    SAY "-class (no CPUID)"
    ret
.cpuid:
    mov eax, [gs:V_SIG]
    mov bl, ah
    and bl, 0x0F                    ; family
    mov bh, al
    shr bh, 4                       ; model
    cmp dword [gs:V_VEND], 'Genu'
    jne .amd
    cmp bl, 4
    jne .fam5
    movzx si, bh
    shl si, 1
    mov si, [cs:intel486 + si]
    call puts
    jmp short .od
.fam5:
    cmp bl, 5
    jne .generic
    SAY "Intel Pentium"
    jmp short .od
.amd:
    cmp dword [gs:V_VEND], 'Auth'
    jne .generic
    cmp bl, 4
    jne .generic
    movzx si, bh
    shl si, 1
    mov si, [cs:amd486 + si]
    call puts
    jmp short .od
.generic:
    mov si, V_VEND
    call puts_gs
.od:
    test byte [gs:V_SIG+1], 0x10    ; type field 1 = OverDrive
    jz .sig
    SAY " OverDrive"
.sig:
    mov byte [gs:V_ATTR], A_DIM
    SAY "  (family "
    movzx eax, bl
    call putdec
    SAY ", model "
    movzx eax, bh
    call putdec
    SAY ", stepping "
    mov eax, [gs:V_SIG]
    and eax, 0x0F
    call putdec
    SAY ")"
    mov byte [gs:V_ATTR], A_VALUE
    ret

s_dx: db "DX", 0
s_sx: db "SX", 0
i0: db "Intel 486DX", 0
i2: db "Intel 486SX", 0
i3: db "Intel 486DX2", 0
i4: db "Intel 486SL", 0
i5: db "Intel 486SX2", 0
i7: db "Intel 486DX2 write-back", 0
i8: db "Intel 486DX4", 0
i9: db "Intel 486DX4 write-back", 0
iq: db "Intel 486", 0
intel486: dw i0, i0, i2, i3, i4, i5, iq, i7, i8, i9, iq, iq, iq, iq, iq, iq
a3: db "AMD Am486DX2", 0
a7: db "AMD Am486DX2 write-back", 0
a8: db "AMD Am486DX4", 0
a9: db "AMD Am486DX4 write-back", 0
ae: db "AMD Am5x86", 0
af: db "AMD Am5x86 write-back", 0
aq: db "AMD 486", 0
amd486: dw aq, aq, aq, a3, aq, aq, aq, a7, a8, a9, aq, aq, aq, aq, ae, af

speed_value:                        ; "~66 MHz (measured)" or "not measured"
    movzx eax, word [gs:V_MHZV]
    test eax, eax
    jz .none
    mov al, 0xF7                    ; "about"
    call putc
    movzx eax, word [gs:V_MHZV]
    call putdec
    SAY " MHz", 1, A_DIM, " (measured)", 1, A_VALUE
    ret
.none:
    SAY "not measured"
    ret

; ------------------------------------------------------------------ memory and cache facts

base_kb:                            ; EAX = base memory in KB (BIOS data 40:13)
    push es
    mov ax, 0x40
    mov es, ax
    movzx eax, word [es:0x13]
    pop es
    ret

ext_kb:                             ; EAX = extended memory found by POST (CMOS 30h/31h)
    push bx
    mov al, 0x31
    call cmos_read
    mov ah, al
    mov al, 0x30
    call cmos_read
    movzx eax, ax
    pop bx
    ret

l2_value:
    mov al, 0x92
    call chip_read
    test al, 1
    jz .off
    mov al, 0x93
    call chip_read
    and al, 0x1F
    mov si, s_l2_256
    cmp al, 0x18
    je .p
    mov si, s_l2_128
    cmp al, 0x1C
    je .p
    mov si, s_l2_64
    cmp al, 0x1E
    je .p
    mov si, s_l2_32
.p:
    call puts
    ret
.off:
    SAY "not installed or switched off"
    ret
s_l2_256: db "256 KB, on", 0
s_l2_128: db "128 KB, on", 0
s_l2_64:  db "64 KB, on", 0
s_l2_32:  db "32 KB, on", 0

l1_value:
    mov eax, cr0
    test eax, 0x40000000
    jnz .off
    SAY "on (internal, write-through)"
    ret
.off:
    SAY "off"
    ret

ports_line:                         ; COM and LPT base addresses from 40:00
    push es
    push bx
    mov ax, 0x40
    mov es, ax
    xor bx, bx
    mov cx, 4
.com:
    mov ax, [es:bx]
    test ax, ax
    jz .nc
    SAY "COM"
    mov al, bl
    shr al, 1
    add al, '1'
    call putc
    mov al, ' '
    call putc
    movzx eax, word [es:bx]
    push cx
    mov cl, 3
    call puthex
    pop cx
    SAY "  "
.nc:
    add bx, 2
    loop .com
    mov bx, 8
    mov cx, 3
.lpt:
    mov ax, [es:bx]
    test ax, ax
    jz .nl
    SAY "LPT"
    mov al, bl
    sub al, 8
    shr al, 1
    add al, '1'
    call putc
    mov al, ' '
    call putc
    movzx eax, word [es:bx]
    push cx
    mov cl, 3
    call puthex
    pop cx
    SAY "  "
.nl:
    add bx, 2
    loop .lpt
    pop bx
    pop es
    ret

clock_value:                        ; RTC date and time, battery state
    mov ah, 4
    int 0x1A
    jc .bad
    push dx
    mov al, ch
    call bcd2
    mov al, cl
    call bcd2
    mov al, '-'
    call putc
    pop dx
    push dx
    mov al, dh
    call bcd2
    mov al, '-'
    call putc
    pop dx
    mov al, dl
    call bcd2
    mov al, ' '
    call putc
    mov ah, 2
    int 0x1A
    jc .bad
    mov al, ch
    call bcd2
    mov al, ':'
    call putc
    mov al, cl
    call bcd2
    mov al, ':'
    call putc
    mov al, dh
    call bcd2
.bat:
    mov al, 0x0D
    call cmos_read
    test al, 0x80
    jz .lost
    SAY 1, A_OK, "  battery OK", 1, A_VALUE
    ret
.lost:
    SAY 1, A_BAD, "  battery lost", 1, A_VALUE
    ret
.bad:
    SAY "not running"
    jmp short .bat

bcd2:                               ; AL as two BCD digits
    push ax
    shr al, 4
    add al, '0'
    call putc
    pop ax
    and al, 0x0F
    add al, '0'
    call putc
    ret

video_value:
    push es
    mov ax, 0x40
    mov es, ax
    mov al, [es:0x49]
    pop es
    mov si, s_vcol
    cmp byte [gs:V_MONO], 0
    je .p
    mov si, s_vmono
.p:
    call puts
    SAY ", BIOS at "
    mov ax, 0xC000
    call rom_at
    jnc .seg
    mov ax, 0xE000
.seg:
    movzx eax, ax
    mov cl, 4
    call puthex
    ret
s_vcol:  db "VGA colour", 0
s_vmono: db "monochrome", 0

rom_at:                             ; CF=0 if a 55AA option ROM header sits at AX:0
    push es
    mov es, ax
    cmp word [es:0], 0xAA55
    pop es
    je .yes
    stc
    ret
.yes:
    clc
    ret

; ------------------------------------------------------------------ IDE

; Identify primary-channel device BL (0 master, 1 slave) into GS:V_IDBUF.
; AL = 0 none, 1 ATA disk, 2 ATAPI device.
ide_identify:
    push bx
    push cx
    push dx
    push di
    push es
    mov dx, 0x3F6
    mov al, 0x0A                    ; no interrupts while we probe
    out dx, al
    mov dx, 0x1F6
    mov al, bl
    shl al, 4
    or al, 0xA0
    out dx, al
    mov dx, 0x1F7
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    cmp al, 0xFF                    ; floating bus: nothing there
    je .none
    call ide_wait_idle
    jc .none
    mov al, 0xEC                    ; IDENTIFY DEVICE
    out dx, al
    call ide_wait_data
    jnc .ata
    mov dx, 0x1F4                   ; aborted: ATAPI shows its signature
    in al, dx
    mov ah, al
    inc dx
    in al, dx
    cmp ax, 0x14EB
    jne .none
    mov dx, 0x1F7
    mov al, 0xA1                    ; IDENTIFY PACKET DEVICE
    out dx, al
    call ide_wait_data
    jc .none
    call ide_read
    mov al, 2
    jmp short .out
.ata:
    call ide_read
    mov al, 1
    jmp short .out
.none:
    xor al, al
.out:
    push ax
    mov dx, 0x1F7
    in al, dx                       ; clear any pending device interrupt
    push ds
    mov ax, 0x40
    mov ds, ax
    mov al, [0x76]
    and al, 0x0B
    mov dx, 0x3F6
    out dx, al
    and byte [0x8E], 0x7F           ; no stale "IRQ 14 seen" flag for INT 13h
    pop ds
    pop ax
    pop es
    pop di
    pop dx
    pop cx
    pop bx
    ret

ide_wait_idle:                      ; DX = 1F7. CF=1 if still busy after ~0.2 s
    push cx
    push bx
    mov bx, 4
.o:
    xor cx, cx
.l:
    in al, dx
    test al, 0x80
    jz .ok
    loop .l
    dec bx
    jnz .o
    stc
    jmp short .x
.ok:
    clc
.x:
    pop bx
    pop cx
    ret

ide_wait_data:                      ; CF=0 when DRQ (data ready), CF=1 on error/timeout
    push cx
    push bx
    in al, dx                       ; 400 ns settle
    in al, dx
    in al, dx
    in al, dx
    mov bx, 2
.o:
    xor cx, cx
.l:
    in al, dx
    test al, 0x80
    jnz .n
    test al, 0x01
    jnz .bad
    test al, 0x08
    jnz .ok
.n:
    loop .l
    dec bx
    jnz .o
.bad:
    stc
    jmp short .x
.ok:
    clc
.x:
    pop bx
    pop cx
    ret

ide_read:                           ; 256 words into GS:V_IDBUF
    push ax
    push cx
    push dx
    push di
    push es
    mov ax, VARSEG
    mov es, ax
    mov di, V_IDBUF
    mov dx, 0x1F0
    mov cx, 256
    rep insw
    pop es
    pop di
    pop dx
    pop cx
    pop ax
    ret

; Probe master and slave; fill V_IDTYPE, V_IDNAME, V_IDFW and V_IDMB.
ide_scan:
    pushad
    xor bx, bx
.dev:
    call ide_identify
    mov [gs:V_IDTYPE + bx], al
    test al, al
    jz .next
    imul di, bx, 41
    add di, V_IDNAME
    mov si, V_IDBUF + 54            ; model: words 27-46
    mov cx, 40
    call idstr
    imul di, bx, 9
    add di, V_IDFW
    mov si, V_IDBUF + 46            ; firmware: words 23-26
    mov cx, 8
    call idstr
    imul di, bx, 6                  ; default geometry: words 1, 3, 6
    add di, V_IDGEO
    mov ax, [gs:V_IDBUF + 2]
    mov [gs:di], ax
    mov ax, [gs:V_IDBUF + 6]
    mov [gs:di + 2], ax
    mov ax, [gs:V_IDBUF + 12]
    mov [gs:di + 4], ax
    mov eax, [gs:V_IDBUF + 120]     ; LBA sectors (words 60-61)
    test byte [gs:V_IDBUF + 99], 2  ; LBA supported (word 49 bit 9)
    jnz .lba
    movzx eax, word [gs:V_IDBUF + 2]
    movzx ecx, word [gs:V_IDBUF + 6]
    imul eax, ecx
    movzx ecx, word [gs:V_IDBUF + 12]
    imul eax, ecx
.lba:
    shr eax, 11                     ; sectors -> MB
    mov si, bx
    shl si, 2
    mov [gs:V_IDMB + si], eax
.next:
    inc bx
    cmp bx, 2
    jb .dev
    popad
    ret

idstr:                              ; byte-swapped ID string GS:SI (CX bytes) -> GS:DI, trimmed
    push di
.l:
    mov ax, [gs:si]
    xchg al, ah
    mov [gs:di], ax
    add si, 2
    add di, 2
    sub cx, 2
    jnz .l
    mov byte [gs:di], 0
    pop si                          ; trim trailing blanks
.t:
    dec di
    cmp di, si
    jb .done
    cmp byte [gs:di], ' '
    jne .done
    mov byte [gs:di], 0
    jmp short .t
.done:
    ret

ide_line:                           ; BX = device: print what is there
    mov al, [gs:V_IDTYPE + bx]
    test al, al
    jnz .some
    mov byte [gs:V_ATTR], A_DIM
    SAY "none"
    mov byte [gs:V_ATTR], A_VALUE
    ret
.some:
    push ax
    imul si, bx, 41
    add si, V_IDNAME
    call puts_gs
    pop ax
    mov byte [gs:V_ATTR], A_DIM
    cmp al, 2
    je .atapi
    SAY "  (disk, "
    mov si, bx
    shl si, 2
    mov eax, [gs:V_IDMB + si]
    call putdec
    SAY " MB"
    call lba_drive
    jc .nolba
    SAY ", LBA"
.nolba:
    SAY ")"
    jmp short .x
.atapi:
    SAY "  (CD-ROM / ATAPI)"
.x:
    mov byte [gs:V_ATTR], A_VALUE
    ret

; ------------------------------------------------------------------ floppy names

lba_drive:                          ; BX = IDE device: CF=0 if BIOS drive 80h+BX is in LBA mode
    pusha
    mov dl, bl
    or dl, 0x80
    mov ah, 0x41
    mov bx, 0x55AA
    int 0x13
    jc .x
    cmp bx, 0xAA55
    je .x                           ; (CF is clear here)
    stc
.x:
    popa
    ret

floppy_name:                        ; AL = CMOS type nibble
    movzx si, al
    cmp si, 6
    jbe .ok
    xor si, si
.ok:
    shl si, 1
    mov si, [cs:fdnames + si]
    call puts
    ret
f0: db "none", 0
f1: db "360 KB 5.25", 0x22, 0
f2: db "1.2 MB 5.25", 0x22, 0
f3: db "720 KB 3.5", 0x22, 0
f4: db "1.44 MB 3.5", 0x22, 0
f5: db "2.88 MB 3.5", 0x22, 0
fdnames: dw f0, f1, f2, f3, f4, f5, f5

; ------------------------------------------------------------------ pages

page_menu:
    mov byte [gs:V_SEL], 0
.draw:
    mov si, t_menu
    mov bx, h_menu
    call frame
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x0403
    call goto_rc
    SAY "Information and tests. Hard disk setup and the boot order are saved in CMOS."
    xor cx, cx
.item:
    mov dh, cl
    add dh, 6
    mov dl, 20
    call goto_rc
    mov byte [gs:V_ATTR], A_VALUE
    cmp cl, [gs:V_SEL]
    jne .n
    mov byte [gs:V_ATTR], A_SEL
.n:
    mov si, cx
    shl si, 1
    mov si, [cs:menu_items + si]
    push cx
    mov al, ' '
    call putc
    call puts
.pad:
    cmp byte [gs:V_COL], 60
    jae .padded
    mov al, ' '
    call putc
    jmp short .pad
.padded:
    pop cx
    inc cx
    cmp cx, MENU_N
    jb .item
.key:
    call getkey
    cmp ah, 0x01                    ; Esc: continue booting
    je .exit
    cmp ah, 0x48
    je .up
    cmp ah, 0x50
    je .down
    cmp al, 0x0D
    je .open
    cmp al, '1'
    jb .key
    cmp al, '0' + MENU_N
    ja .key
    sub al, '1'
    mov [gs:V_SEL], al
    jmp short .open
.up:
    cmp byte [gs:V_SEL], 0
    je .draw
    dec byte [gs:V_SEL]
    jmp .draw
.down:
    cmp byte [gs:V_SEL], MENU_N - 1
    jae .draw
    inc byte [gs:V_SEL]
    jmp .draw
.open:
    movzx si, byte [gs:V_SEL]
    cmp si, MENU_N - 1
    je .exit
    shl si, 1
    call [cs:menu_pages + si]
    jc .exit                        ; a page asked to leave the menu (boot menu choice)
    jmp .draw
.exit:
    ret

MENU_N equ 9
menu_items: dw m1, m2, m3, m4, m5, m6, m7, m8, m9
menu_pages: dw page_sysinfo, page_drives, page_memmap, page_memtest, page_cmos, page_fdtest, page_hdsetup
            dw page_boot_menu
m1: db "1  System information", 0
m2: db "2  Drives and devices", 0
m3: db "3  Memory map and option ROMs", 0
m4: db "4  Memory test", 0
m5: db "5  CMOS contents", 0
m6: db "6  Floppy drive test (NCR built-in)", 0
m7: db "7  Hard disk setup", 0
m8: db "8  Boot menu", 0
m9: db "9  Continue booting", 0
t_menu: db "Tools", 0
h_menu: db 0x18, 0x19, " Select   Enter Open   1-9 Shortcut   Esc Continue booting", 0
h_back: db "Any key returns to the menu", 0

page_sysinfo:
    mov si, t_sys
    mov bx, h_back
    call frame
    mov dh, 5
    mov si, l_cpu
    call label
    call cpu_name
    mov dh, 6
    mov si, l_speed
    call label
    call speed_value
    mov dh, 7
    mov si, l_fpu
    call label
    mov si, s_fpu_yes
    cmp byte [gs:V_FPU], 0
    jne .f
    mov si, s_fpu_no
.f:
    call puts
    mov dh, 8
    mov si, l_l1
    call label
    call l1_value
    mov dh, 9
    mov si, l_l2
    call label
    call l2_value
    mov dh, 11
    mov si, l_base
    call label
    call base_kb
    call putdec
    SAY " KB"
    mov dh, 12
    mov si, l_ext
    call label
    call ext_kb
    push eax
    call putdec
    SAY " KB", 1, A_DIM, "  (total "
    pop eax
    add eax, 1023
    shr eax, 10
    inc eax
    call putdec
    SAY " MB)", 1, A_VALUE
    mov dh, 13
    mov si, l_shadow
    call label
    call shadow_value
    mov dh, 15
    mov si, l_ports
    call label
    call ports_line
    mov dh, 16
    mov si, l_video
    call label
    call video_value
    mov dh, 17
    mov si, l_clock
    call label
    call clock_value
    mov dh, 19
    mov si, l_bios
    call label
    SAY "NCR 517-0000672 v2.03.00 (10/08/93), Enhanced Edition"
    mov dh, 20
    mov si, l_tools
    call label
    SAY "E800:0000, "
    mov ax, EXT_SEG
    mov es, ax
    movzx eax, word [es:4]
    call putdec
    SAY " bytes, checksum OK"
    call wait_back
    clc
    ret

shadow_value:
    mov al, 0x46
    call cmos_read
    mov ah, al
    mov al, 0x47
    call cmos_read
    test ah, ah
    jnz .some
    test al, 0x90
    jnz .some
    SAY "none"
    ret
.some:
    push ax
    xor cx, cx
    mov bx, 0xC000
.b:
    test ah, 1
    jz .nb
    movzx eax, bx
    push cx
    mov cl, 4
    call puthex
    pop cx
    mov al, ' '
    call putc
.nb:
    shr ah, 1
    add bx, 0x400
    inc cx
    cmp cx, 8
    jb .b
    pop ax
    test al, 0x10
    jz .ne
    SAY "E000 "
.ne:
    test al, 0x80
    jz .x
    SAY 1, A_DIM, "(video copied to C000)", 1, A_VALUE
.x:
    ret

t_sys: db "System information", 0
l_cpu: db "Processor", 0
l_speed: db "Clock speed", 0
l_fpu: db "Maths coprocessor", 0
l_l1: db "Level 1 cache", 0
l_l2: db "Level 2 cache", 0
l_base: db "Base memory", 0
l_ext: db "Extended memory", 0
l_shadow: db "Shadow RAM", 0
l_ports: db "Serial / parallel", 0
l_video: db "Video", 0
l_clock: db "Real-time clock", 0
l_bios: db "BIOS", 0
l_tools: db "Tools extension", 0
s_fpu_yes: db "present", 0
s_fpu_no: db "not present", 0

page_drives:
    mov si, t_drives
    mov bx, h_back
    call frame
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x0403
    call goto_rc
    SAY "Asking the IDE devices for their names..."
    call ide_scan
    mov dx, 0x0403
    mov cx, 60
    mov byte [gs:V_ATTR], A_BG
    mov al, ' '
    call hline
    mov dh, 5
    mov si, l_fda
    call label
    mov al, 0x10
    call cmos_read
    push ax
    shr al, 4
    call floppy_name
    mov dh, 6
    mov si, l_fdb
    call label
    pop ax
    and al, 0x0F
    call floppy_name
    mov dh, 8
    mov si, l_hdc
    call label
    mov dl, 0x80
    call bios_disk
    mov dh, 9
    mov si, l_hdd
    call label
    mov dl, 0x81
    call bios_disk
    mov dh, 11
    mov si, l_ide0
    call label
    xor bx, bx
    call ide_line
    mov dh, 12
    xor bx, bx
    call fw_line
    mov dh, 14
    mov si, l_ide1
    call label
    mov bx, 1
    call ide_line
    mov dh, 15
    mov bx, 1
    call fw_line
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x1103
    call goto_rc
    SAY "Sizes are as the drive reports them. Automatic disks over 504 MB use LBA.", 3
    SAY "A CD-ROM is used from DOS with a driver, e.g. OAKCDROM.SYS and MSCDEX."
    call wait_back
    clc
    ret

fw_line:                            ; row DH: firmware line, only when a device answered
    cmp byte [gs:V_IDTYPE + bx], 0
    je .x
    mov si, l_fw
    call label
    mov byte [gs:V_ATTR], A_DIM
    imul si, bx, 9
    add si, V_IDFW
    call puts_gs
.x:
    mov byte [gs:V_ATTR], A_VALUE
    ret

bios_disk:                          ; DL = 80h/81h: geometry INT 13h reports
    push dx
    mov ah, 8
    int 0x13
    pop ax                          ; AL = drive asked for
    jc .none
    sub al, 0x80
    cmp al, dl                      ; DL = number of hard disks
    jae .none
    movzx eax, cx                   ; cylinders = CH + (CL bits 6-7 << 2) + 1
    xchg al, ah
    shr ah, 6
    inc eax
    and eax, 0x3FF
    jnz .c
    mov eax, 1024
.c:
    push eax
    call putdec
    mov al, '/'
    call putc
    movzx eax, dh
    inc eax
    push eax
    call putdec
    mov al, '/'
    call putc
    and cx, 0x3F
    movzx eax, cx
    push eax
    call putdec
    SAY 1, A_DIM, "  (cylinders/heads/sectors, "
    pop eax
    pop ebx
    imul eax, ebx
    pop ebx
    imul eax, ebx
    shr eax, 11
    call putdec
    SAY " MB)", 1, A_VALUE
    ret
.none:
    mov byte [gs:V_ATTR], A_DIM
    SAY "not configured"
    mov byte [gs:V_ATTR], A_VALUE
    ret

t_drives: db "Drives and devices", 0
l_fda: db "Floppy A:", 0
l_fdb: db "Floppy B:", 0
l_hdc: db "Hard disk C: (BIOS)", 0
l_hdd: db "Hard disk D: (BIOS)", 0
l_ide0: db "IDE primary master", 0
l_ide1: db "IDE primary slave", 0
l_fw: db "  firmware", 0

page_memmap:
    mov si, t_map
    mov bx, h_back
    call frame
    mov byte [gs:V_ATTR], A_LABEL
    mov dx, 0x0503
    call goto_rc
    SAY "Address  Size     Contents"
    mov byte [gs:V_ROW], 6
    mov byte [gs:V_ATTR], A_VALUE
    mov dx, 0x0603
    call goto_rc
    SAY "00000    "
    call base_kb
    call putdec
    SAY " KB   Conventional RAM"
    mov dx, 0x0703
    call goto_rc
    SAY "A0000    128 KB   Video memory"
    mov dh, 8
    mov ax, 0xC000
.scan:
    call rom_at
    jc .next
    push ax
    mov dl, 3
    call goto_rc
    movzx eax, ax
    mov cl, 4
    call puthex
    mov al, '0'
    call putc
    SAY "    "
    pop ax
    push ax
    push es
    mov es, ax
    movzx eax, byte [es:2]
    shr eax, 1                      ; 512-byte units -> KB
    call putdec
    SAY " KB    "
    call rom_name
    pop es
    pop ax
    inc dh
.next:
    add ax, 0x80
    cmp ax, 0xE800
    jb .scan
    mov dl, 3
    call goto_rc
    SAY "E8000    32 KB    NCR 3230 Tools (this program)"
    inc dh
    mov dl, 3
    call goto_rc
    SAY "F0000    64 KB    System BIOS 517-0000672 v2.03.00"
    inc dh
    mov dl, 3
    call goto_rc
    SAY "100000   "
    call ext_kb
    call putdec
    SAY " KB   Extended RAM"
    add dh, 2
    mov si, l_shadow
    call label
    call shadow_value
    call wait_back
    clc
    ret

rom_name:                           ; ES = ROM segment: first readable text, up to 40 chars
    push si
    push cx
    mov si, 6
.find:
    cmp si, 0x180
    jae .none
    mov cx, si
.run:
    mov al, [es:si]
    cmp al, 0x20
    jb .short
    cmp al, 0x7E
    ja .short
    inc si
    jmp short .run
.short:
    mov ax, si
    sub ax, cx
    cmp ax, 10
    jae .found
    inc si
    jmp short .find
.found:
    mov si, cx
.lead:                              ; skip leading punctuation
    mov al, [es:si]
    cmp al, '0'
    jae .go
    inc si
    jmp short .lead
.go:
    mov cx, 40
.p:
    mov al, [es:si]
    cmp al, 0x20
    jb .done
    cmp al, 0x7E
    ja .done
    call putc
    inc si
    loop .p
    jmp short .done
.none:
    mov byte [gs:V_ATTR], A_DIM
    SAY "option ROM"
    mov byte [gs:V_ATTR], A_VALUE
.done:
    pop cx
    pop si
    ret

t_map: db "Memory map and option ROMs", 0

page_cmos:
    mov si, t_cmos
    mov bx, h_back
    call frame
    mov byte [gs:V_ATTR], A_LABEL
    mov dx, 0x0509
    call goto_rc
    xor cx, cx
.hdr:
    mov eax, ecx
    push cx
    mov cl, 1
    call puthex
    pop cx
    SAY "  "
    inc cx
    cmp cx, 16
    jb .hdr
    xor bx, bx                      ; register
.row:
    mov dh, bl
    shr dh, 4
    add dh, 6
    mov dl, 3
    call goto_rc
    mov byte [gs:V_ATTR], A_LABEL
    movzx eax, bl
    mov cl, 2
    call puthex
    SAY "h   "
.cell:
    mov al, bl
    call cmos_read
    mov byte [gs:V_ATTR], A_VALUE
    test bl, 0xF0
    jnz .h
    mov byte [gs:V_ATTR], A_DIM     ; clock / status registers
.h:
    movzx eax, al
    mov cl, 2
    call puthex
    mov al, ' '
    call putc
    inc bl
    test bl, 0x0F
    jnz .cell
    cmp bl, 0x80
    jb .row
    ; decoded facts
    mov dh, 15
    mov si, l_csum
    call label
    xor bx, bx                      ; sum 10h-2Dh
    mov cl, 0x10
.s:
    mov al, cl
    call cmos_read
    movzx ax, al
    add bx, ax
    inc cl
    cmp cl, 0x2E
    jb .s
    mov al, 0x2E
    call cmos_read
    mov ah, al
    mov al, 0x2F
    call cmos_read
    call ok_bad
    mov dh, 16
    mov si, l_ncsum
    call label
    xor bx, bx                      ; sum 44h-47h
    mov cl, 0x44
.s2:
    mov al, cl
    call cmos_read
    movzx ax, al
    add bx, ax
    inc cl
    cmp cl, 0x48
    jb .s2
    mov al, 0x7E
    call cmos_read
    mov ah, al
    mov al, 0x7F
    call cmos_read
    call ok_bad
    mov dh, 17
    mov si, l_batt
    call label
    mov al, 0x0D
    call cmos_read
    mov si, s_ok
    test al, 0x80
    jnz .b
    mov si, s_lost
.b:
    call puts
    mov dh, 18
    mov si, l_fancy
    call label
    mov al, 0x48
    call cmos_read
    mov si, s_on
    cmp al, 0xA5
    jne .f
    mov si, s_off
.f:
    call puts
    mov dh, 19
    mov si, l_type1
    call label
    xor bx, bx
    mov cl, 0x72
.u:
    mov al, cl
    call cmos_read
    movzx ax, al
    add bx, ax
    inc cl
    cmp cl, 0x7C
    jb .u
    mov al, 0x7C
    call cmos_read
    test bx, bx
    jz .unset
    cmp al, bl
    jne .unset
    mov al, 0x73
    call cmos_read
    mov ah, al
    mov al, 0x72
    call cmos_read
    movzx eax, ax
    call putdec
    mov al, '/'
    call putc
    mov al, 0x74
    call cmos_read
    movzx eax, al
    call putdec
    mov al, '/'
    call putc
    mov al, 0x7B
    call cmos_read
    movzx eax, al
    call putdec
    SAY 1, A_DIM, "  (set by USERHDD)", 1, A_VALUE
    jmp short .w
.unset:
    SAY "not set"
.w:
    call wait_back
    clc
    ret

ok_bad:                             ; AX = stored, BX = computed
    push ax
    SAY "stored "
    movzx eax, ax
    mov cl, 4
    call puthex
    SAY ", computed "
    movzx eax, bx
    call puthex
    pop ax
    cmp ax, bx
    jne .bad
    SAY 1, A_OK, "  OK", 1, A_VALUE
    ret
.bad:
    SAY 1, A_BAD, "  does not match", 1, A_VALUE
    ret

t_cmos: db "CMOS contents (00h-7Fh)", 0
l_csum: db "Checksum 10h-2Dh", 0
l_ncsum: db "NCR checksum 44h-47h", 0
l_batt: db "Battery (reg. D)", 0
l_fancy: db "Fancy boot (48h)", 0
l_type1: db "Disk type 1 (72h-7Ch)", 0
s_ok: db "OK", 0
s_lost: db "power was lost", 0
s_on: db "on", 0
s_off: db "off", 0

; ------------------------------------------------------------------ hard disk setup
; Sets CMOS hard disk types the 1990s way: Automatic (the drive is asked at
; every boot), a user geometry typed in or copied from the drive (what
; USERHDD.EXE does), or Not installed. Writes CMOS 12h (19h/1Ah for types 15+),
; the type-1 table 72h-7Ch, and the standard checksum.

page_hdsetup:
    call ide_scan
    mov al, 0x12
    call cmos_read
    push ax
    shr al, 4
    mov bl, 0x19
    call hd_type_in
    mov [gs:V_TC], al
    mov [gs:V_OC], al
    pop ax
    and al, 0x0F
    mov bl, 0x1A
    call hd_type_in
    mov [gs:V_TD], al
    mov [gs:V_OD], al
    call user_in
.draw:
    mov si, t_hd
    mov bx, h_hd
    call frame
    mov dh, 5
    mov si, l_ide0
    call label
    xor bx, bx
    call ide_line
    mov dh, 6
    xor bx, bx
    call geo_line
    mov dh, 7
    mov si, l_ide1
    call label
    mov bx, 1
    call ide_line
    mov dh, 8
    mov bx, 1
    call geo_line
    mov dh, 10
    mov si, l_hdc2
    call label
    mov al, [gs:V_TC]
    mov ah, 2
    call hd_value
    mov dh, 11
    mov si, l_hdd2
    call label
    mov al, [gs:V_TD]
    mov ah, 3
    call hd_value
    mov dh, 12
    mov si, l_user
    call label
    call user_value
    mov byte [gs:V_ATTR], A_VALUE
    mov dx, 0x0E05
    call goto_rc
    SAY 1, A_TITLE, "C", 1, A_VALUE, "  Change drive C:        ", 1, A_TITLE, "U", 1, A_VALUE, "  Type in the user geometry", 3
    SAY 1, A_TITLE, "D", 1, A_VALUE, "  Change drive D:        ", 1, A_TITLE, "M", 1, A_VALUE, "  User geometry from the master", 3
    SAY 1, A_TITLE, "S", 1, A_VALUE, "  Save                   ", 1, A_TITLE, "Esc", 1, A_VALUE, " Back without saving"
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x1203
    call goto_rc
    SAY "Automatic asks the drive for its geometry at every boot: right for any IDE", 3
    SAY "disk, nothing to type in. Use the user type only for a disk that must keep", 3
    SAY "a geometry it was set up with elsewhere. Over 504 MB, Automatic uses LBA."
    mov al, 0x0D
    call cmos_read
    test al, 0x80
    jnz .key
    mov byte [gs:V_ATTR], A_BAD
    mov dx, 0x1603
    call goto_rc
    SAY "No CMOS battery: settings are lost at power-off. The defaults use Automatic."
.key:
    call getkey
    cmp ah, 0x01
    je .back
    or al, 0x20                     ; letters in lower case
    cmp al, 'c'
    je .c
    cmp al, 'd'
    je .d
    cmp al, 'u'
    je .u
    cmp al, 'm'
    je .m
    cmp al, 's'
    je .s
    jmp .key
.c:
    mov al, [gs:V_TC]
    mov ah, 2
    mov bl, [gs:V_OC]
    call hd_cycle
    mov [gs:V_TC], al
    jmp .draw
.d:
    mov al, [gs:V_TD]
    mov ah, 3
    mov bl, [gs:V_OD]
    call hd_cycle
    mov [gs:V_TD], al
    jmp .draw
.u:
    call user_edit
    jmp .draw
.m:
    cmp byte [gs:V_IDTYPE], 1
    jne .key
    mov ax, [gs:V_IDGEO]
    cmp ax, 1024                    ; as Automatic does: at most 1024 cylinders
    jbe .mc
    mov ax, 1024
.mc:
    mov [gs:V_UCYL], ax
    mov al, [gs:V_IDGEO + 2]
    mov [gs:V_UHD], al
    mov al, [gs:V_IDGEO + 4]
    mov [gs:V_USPT], al
    jmp .draw
.s:
    call hd_save
    jnc .saved
    mov byte [gs:V_ATTR], A_BAD
    mov dx, 0x1603
    call goto_rc
    SAY "A drive is set to the user type: enter its geometry first (U or M).        "
    jmp .key
.saved:
    mov byte [gs:V_ATTR], A_OK
    mov dx, 0x1603
    call goto_rc
    SAY "Saved. Enter restarts now so POST uses the new settings; Esc goes back.    "
.sk:
    call getkey
    cmp ah, 0x01
    je .back
    cmp al, 0x0D
    jne .sk
    push 0x40
    pop es
    mov word [es:0x72], 0x1234      ; warm restart, no memory test
    jmp 0xFFFF:0x0000
.back:
    clc
    ret

hd_type_in:                         ; AL = CMOS nibble, BL = extended register -> AL = type
    cmp al, 0x0F
    jne .x
    mov al, bl
    call cmos_read
.x:
    ret

hd_cycle:                           ; AL = type, AH = Automatic value, BL = type found -> AL = next
    test al, al
    jnz .1
    mov al, ah                      ; Not installed -> Automatic
    ret
.1:
    cmp al, ah
    jne .2
    mov al, 1                       ; Automatic -> User type
    ret
.2:
    cmp al, 1
    jne .3
    mov al, bl                      ; User type -> the fixed type found, if any
    cmp al, 4
    jae .r
.3:
    xor al, al                      ; -> Not installed
.r:
    ret

hd_value:                           ; AL = type, AH = Automatic value
    test al, al
    jnz .1
    mov byte [gs:V_ATTR], A_DIM
    SAY "Not installed"
    ret
.1:
    cmp al, ah
    jne .2
    SAY "Automatic", 1, A_DIM, "  (detected at every boot)"
    ret
.2:
    cmp al, 1
    jne .3
    SAY "User type (type 1)"
    ret
.3:
    push ax
    SAY "Type "
    pop ax
    movzx eax, al
    push ax
    call putdec
    SAY "  "
    pop ax
    dec al                          ; table entry: 16 bytes from F000:E401
    movzx si, al
    shl si, 4
    push es
    push 0xF000
    pop es
    mov cx, [es:si + 0xE401]
    mov bl, [es:si + 0xE403]
    mov bh, [es:si + 0xE40F]
    pop es
    jmp geo_print

geo_print:                          ; CX cylinders, BL heads, BH sectors: "c/h/s (n MB)"
    mov byte [gs:V_ATTR], A_VALUE
    movzx eax, cx
    call putdec
    mov al, '/'
    call putc
    movzx eax, bl
    call putdec
    mov al, '/'
    call putc
    movzx eax, bh
    call putdec
    SAY 1, A_DIM, "  ("
    movzx eax, cx
    movzx edx, bl
    imul eax, edx
    movzx edx, bh
    imul eax, edx
    shr eax, 11
    call putdec
    SAY " MB)", 1, A_VALUE
    ret

geo_line:                           ; row DH: the default geometry of an ATA disk BX
    cmp byte [gs:V_IDTYPE + bx], 1
    jne .x
    mov si, l_geo
    call label
    imul si, bx, 6
    mov cx, [gs:V_IDGEO + si]
    mov bl, [gs:V_IDGEO + si + 2]
    mov bh, [gs:V_IDGEO + si + 4]
    call geo_print
.x:
    ret

user_value:
    cmp word [gs:V_UCYL], 0
    jne .set
    mov byte [gs:V_ATTR], A_DIM
    SAY "not set"
    ret
.set:
    mov cx, [gs:V_UCYL]
    mov bl, [gs:V_UHD]
    mov bh, [gs:V_USPT]
    jmp geo_print

user_in:                            ; CMOS type-1 table -> V_UCYL/V_UHD/V_USPT (0 if not valid)
    mov word [gs:V_UCYL], 0
    xor dx, dx
    mov cl, 0x72
.s:
    mov al, cl
    call cmos_read
    movzx ax, al
    add dx, ax
    inc cl
    cmp cl, 0x7C
    jb .s
    test dx, dx
    jz .x
    mov al, 0x7C
    call cmos_read
    cmp al, dl
    jne .x
    mov al, 0x73
    call cmos_read
    mov ah, al
    mov al, 0x72
    call cmos_read
    mov [gs:V_UCYL], ax
    mov al, 0x74
    call cmos_read
    mov [gs:V_UHD], al
    mov al, 0x7B
    call cmos_read
    mov [gs:V_USPT], al
.x:
    ret

user_edit:                          ; ask for cylinders, heads and sectors
    mov dx, 0x1603
    mov cx, 76
    mov byte [gs:V_ATTR], A_BG
    mov al, ' '
    call hline
    mov dx, 0x1603
    call goto_rc
    mov byte [gs:V_ATTR], A_VALUE
    SAY "Cylinders (1-1024): "
    mov bx, 1024
    call getnum
    jc .x
    push ax
    SAY "   heads (1-16): "
    mov bx, 16
    call getnum
    pop cx
    jc .x
    push cx
    push ax
    SAY "   sectors (1-63): "
    mov bx, 63
    call getnum
    pop dx
    pop cx
    jc .x
    mov [gs:V_UCYL], cx
    mov [gs:V_UHD], dl
    mov [gs:V_USPT], al
.x:
    ret

getnum:                             ; typed number 1..BX at the cursor -> AX. CF=1 on Esc
    push cx
    push dx
    push si
    xor cx, cx                      ; value
    xor si, si                      ; digits typed
    mov byte [gs:V_ATTR], A_SEL
.k:
    call getkey
    cmp ah, 0x01
    je .esc
    cmp al, 0x0D
    je .enter
    cmp al, 0x08
    je .bs
    cmp al, '0'
    jb .k
    cmp al, '9'
    ja .k
    cmp si, 4
    jae .k
    call putc
    sub al, '0'
    movzx dx, al
    imul cx, cx, 10
    add cx, dx
    inc si
    jmp .k
.bs:
    test si, si
    jz .k
    dec si
    mov ax, cx
    xor dx, dx
    mov cx, 10
    div cx
    mov cx, ax
    dec byte [gs:V_COL]
    mov al, ' '
    call putc
    dec byte [gs:V_COL]
    jmp .k
.enter:
    test cx, cx
    jz .k
    cmp cx, bx
    ja .k
    mov ax, cx
    mov byte [gs:V_ATTR], A_VALUE
    clc
    jmp short .x
.esc:
    mov byte [gs:V_ATTR], A_VALUE
    stc
.x:
    pop si
    pop dx
    pop cx
    ret

cmos_write:                         ; CMOS[AL] = AH
    pushf
    cli
    or al, 0x80
    out 0x70, al
    mov al, ah
    out 0x71, al
    popf
    ret

hd_save:                            ; CF=1 if a drive is type 1 with no user geometry
    mov al, [gs:V_TC]
    cmp al, 1
    je .user
    cmp byte [gs:V_TD], 1
    jne .types
.user:
    mov cx, [gs:V_UCYL]
    test cx, cx
    jz .fail
    mov al, 0x72                    ; type-1 table, as USERHDD writes it
    mov ah, cl
    call cmos_write
    mov al, 0x73
    mov ah, ch
    call cmos_write
    mov al, 0x74
    mov ah, [gs:V_UHD]
    call cmos_write
    mov al, 0x75                    ; no write precompensation
    mov ah, 0xFF
    call cmos_write
    mov al, 0x76
    call cmos_write
    mov al, 0x77
    xor ah, ah
    call cmos_write
    mov al, 0x78                    ; control byte: bit 3 = more than 8 heads
    cmp byte [gs:V_UHD], 8
    jbe .ctl
    mov ah, 0x08
.ctl:
    call cmos_write
    mov al, 0x79                    ; landing zone = cylinders
    mov ah, cl
    call cmos_write
    mov al, 0x7A
    mov ah, ch
    call cmos_write
    mov al, 0x7B
    mov ah, [gs:V_USPT]
    call cmos_write
    xor dx, dx
    mov cl, 0x72
.us:
    mov al, cl
    call cmos_read
    add dl, al
    inc cl
    cmp cl, 0x7C
    jb .us
    mov al, 0x7C
    mov ah, dl
    call cmos_write
.types:
    mov al, [gs:V_TC]
    mov bl, 0x19
    call .nib
    shl dh, 4
    mov cl, dh
    mov al, [gs:V_TD]
    mov bl, 0x1A
    call .nib
    or cl, dh
    mov al, 0x12
    mov ah, cl
    call cmos_write
    xor dx, dx                      ; standard checksum over 10h-2Dh
    mov cl, 0x10
.cs:
    mov al, cl
    call cmos_read
    movzx ax, al
    add dx, ax
    inc cl
    cmp cl, 0x2E
    jb .cs
    mov al, 0x2E
    mov ah, dh
    call cmos_write
    mov al, 0x2F
    mov ah, dl
    call cmos_write
    clc
    ret
.fail:
    stc
    ret
.nib:                               ; AL = type, BL = extended register -> DH = nibble
    mov dh, al
    cmp al, 15
    jb .n
    mov ah, al
    mov al, bl
    call cmos_write
    mov dh, 0x0F
.n:
    ret

t_hd:   db "Hard disk setup", 0
h_hd:   db "C/D Change   U/M User geometry   S Save   Esc Back", 0
l_hdc2: db "Hard disk C:", 0
l_hdd2: db "Hard disk D:", 0
l_user: db "User type (type 1)", 0
l_geo:  db "  geometry", 0

page_fdtest:
    mov si, t_fd
    mov bx, h_fd
    call frame
    mov byte [gs:V_ATTR], A_VALUE
    mov dx, 0x0603
    call goto_rc
    SAY "This runs NCR's own floppy drive test, built into the BIOS (in the", 3
    SAY "stock BIOS it hides behind Ctrl-D at the end of POST).", 3, 3
    SAY 1, A_BAD, "Its format and write tests destroy the data on the test disk.", 3
    SAY 1, A_VALUE, "Use a scratch disk. Leave the test with its EXIT DISK TEST item.", 3, 3
    SAY 1, A_TITLE, "Press Y to start, any other key to go back."
    call getkey
    or al, 0x20
    cmp al, 'y'
    jne .x
    call 0xF000:G_FDTEST
    mov ax, 0x0003
    cmp byte [gs:V_MONO], 0
    je .m
    mov al, 7
.m:
    int 0x10
    mov ah, 1
    mov cx, 0x2000
    int 0x10
.x:
    clc
    ret
t_fd: db "Floppy drive test", 0
h_fd: db "Y Start   any other key Back", 0

; ------------------------------------------------------------------ boot menu

page_boot_menu:                     ; from the Tools menu: CF=1 leaves Tools after a choice
    call page_boot
    ret

page_boot:                          ; CF=1 if a device was chosen
.draw:
    mov si, t_boot
    mov bx, h_boot
    call frame
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x0503
    call goto_rc
    SAY "Boot once from:"
    mov byte [gs:V_ATTR], A_VALUE
    mov dx, 0x0705
    call goto_rc
    SAY "1  Floppy disk A:", 3, 3
    SAY "2  Hard disk C:", 3, 3
    SAY "3  CD-ROM "
    call ide_scan                   ; name the CD-ROM drive, if there is one
    mov bx, 0
    cmp byte [gs:V_IDTYPE], 2
    je .cdname
    inc bx
    cmp byte [gs:V_IDTYPE + 1], 2
    je .cdname
    mov byte [gs:V_ATTR], A_DIM
    SAY "(no drive found)"
    jmp short .cdx
.cdname:
    mov byte [gs:V_ATTR], A_DIM
    mov al, '('
    call putc
    imul si, bx, 41
    add si, V_IDNAME
    call puts_gs
    mov al, ')'
    call putc
.cdx:
    mov byte [gs:V_ATTR], A_VALUE
    mov dx, 0x0D05
    call goto_rc
    call rom_boot
    jc .norom
    SAY "4  Option ROM boot "
    mov byte [gs:V_ATTR], A_DIM
    mov al, '('
    call putc
    call rom_name                   ; ES = the ROM's segment
    mov al, ')'
    call putc
    jmp short .esc
.norom:
    mov byte [gs:V_ATTR], A_DIM
    SAY "4  Option ROM boot (no option ROM hooked the boot)"
.esc:
    mov byte [gs:V_ATTR], A_VALUE
    mov dx, 0x0F05
    call goto_rc
    SAY "Esc  Normal boot order"
    mov dx, 0x1203
    call goto_rc
    mov byte [gs:V_ATTR], A_LABEL
    SAY "Normal boot order (O changes it, saved in CMOS):", 3
    mov byte [gs:V_ATTR], A_VALUE
    SAY "  "
    call order_line
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x1503
    call goto_rc
    SAY "1-4 apply to this boot only. CD-ROM boot needs a bootable (El Torito) disc.", 3
    SAY "With a PicoMEM that emulates a hard disk, C: may be its disk image."
.k:
    call getkey
    cmp ah, 0x01
    je .none
    cmp al, '1'
    je .a
    cmp al, '2'
    je .c
    cmp al, '3'
    je .cd
    cmp al, '4'
    je .rom
    or al, 0x20
    cmp al, 'o'
    jne .k
    call page_order
    jmp .draw
.rom:
    call rom_boot
    jc .k
    mov al, ROM_CHOICE
    jmp short .set
.a:
    xor al, al
    jmp short .set
.c:
    mov al, 0x80
    jmp short .set
.cd:
    mov al, CD_DRIVE
.set:
    push ds
    push 0
    pop ds
    mov word [0x4F0], BOOT_MAGIC
    mov [0x4F2], al
    pop ds
    stc
    ret
.none:
    clc
    ret

rom_boot:                           ; CF=0 if an option ROM's INT 19h was kept: ES = its segment
    push ax
    push 0xF000
    pop es
    cmp byte [es:ROM19_OK], 1
    jne .no
    mov ax, [es:ROM19 + 2]
    mov es, ax
    pop ax
    clc
    ret
.no:
    pop ax
    stc
    ret

t_boot: db "Boot menu", 0
h_boot: db "1-4 Choose   O Normal boot order   Esc Continue", 0

capture_entry:                      ; far, end of POST
    ENTER
    call capture19
    LEAVE
    retf

; Option ROMs such as the PicoMEM's hook INT 19h and boot their own way,
; which leaves the boot menu no say. At the end of POST the BIOS takes INT 19h
; back and keeps the ROM's handler, called first unless the boot menu chose
; something else or the boot order says "BIOS first" (see g_boot).
capture19:
    push 0
    pop es
    mov word [es:BOOT_STATE], 0     ; and BOOT_NEXT
    push 0xF000
    pop fs
    mov eax, [es:0x19 * 4]
    cmp eax, 0xF000E6F2
    je .none
    cmp eax, [fs:ROM19]             ; already saved (shadow kept from the last boot)?
    jne .save
    cmp byte [fs:ROM19_OK], 1
    je .take
.save:
    call shadow_open
    mov [fs:ROM19], eax
    mov byte [fs:ROM19_OK], 1
    mov bx, [es:0x7000]             ; a RAM read before locking, as POST does
    call shadow_lock
    cmp eax, [fs:ROM19]             ; no shadow RAM: leave INT 19h with the ROM
    jne .x
.take:
    cli
    mov dword [es:0x19 * 4], 0xF000E6F2
    sti
.x:
    ret
.none:
    cmp byte [fs:ROM19_OK], 0
    je .x
    call shadow_open
    mov byte [fs:ROM19_OK], 0
    mov bx, [es:0x7000]
    call shadow_lock
    ret

; INT 19h: if the boot menu left a choice, try that device once.
boot_override:
    mov byte [gs:V_BOOTQ], 0
    push ds
    push 0
    pop ds
    cmp word [0x4F0], BOOT_MAGIC
    jne .no
    mov dl, [0x4F2]
    mov word [0x4F0], 0
    cmp dl, ROM_CHOICE
    jne .dev
    mov byte [BOOT_STATE], 'R'      ; the option ROM's boot: g_boot calls it
.no:
    pop ds
    ret
.dev:
    pop ds
    cmp dl, CD_DRIVE
    jne .disk
    jmp cd_boot                     ; returns only if the CD did not boot
.disk:
    call boot_drive                 ; returns only if it did not boot
    mov si, s_bootfail
    jmp tty

boot_drive:                         ; DL = 00h or 80h: boot from it, or return
    push ds
    push 0
    pop ds
    mov si, 3
.try:
    xor ax, ax
    int 0x13
    push 0
    pop es
    mov bx, 0x7C00
    mov ax, 0x0201
    mov cx, 1
    xor dh, dh
    int 0x13
    jnc .read
    dec si
    jnz .try
    jmp short .fail
.read:
    cmp dl, 0x80
    jb .go
    cmp word [0x7DFE], 0xAA55
    jne .fail
.go:
    xor ax, ax                      ; boot sectors expect DS = ES = 0
    mov ds, ax
    mov es, ax
    jmp 0x0000:0x7C00               ; DL = boot drive
.fail:
    pop ds
    ret

s_bootfail: db 13, 10, "Boot menu: that drive did not boot, using the normal order.", 13, 10, 0

; ------------------------------------------------------------------ saved boot order
; CMOS 4Ah = 'O', 4Bh/4Ch = four device nibbles (first in the high nibble of
; 4Bh), 4Dh = NOT of the 8-bit sum of 4Ah-4Ch. Devices: 1 floppy A:, 2 hard
; disk C:, 3 CD-ROM, 4 the option ROM's own boot; bit 3 set = switched off.
; Each device is listed once (an older save with gaps is filled up on reading). Without a valid
; order the BIOS default applies: an option ROM's boot first, then A:/C: as
; Setup sets them. Missing or unbootable devices are skipped; when all fail,
; the stock boot (with its "insert system disk" prompt) takes over.

order_read:                         ; -> GS:V_ORDER (all 4 devices). CF=1 if no valid order is saved
    push ax                         ; (then V_ORDER holds the BIOS default, for the editor)
    push bx
    push cx
    push dx
    push di
    mov dword [gs:V_ORDER], ORDER_DEFAULT
    mov al, ORDER_INDEX
    call cmos_read
    cmp al, ORDER_SIG
    jne .no
    mov cl, al
    mov al, ORDER_INDEX + 1
    call cmos_read
    add cl, al
    mov ah, al
    shr al, 4
    mov [gs:V_OTMP], al
    and ah, 0x0F
    mov [gs:V_OTMP + 1], ah
    mov al, ORDER_INDEX + 2
    call cmos_read
    add cl, al
    mov ah, al
    shr al, 4
    mov [gs:V_OTMP + 2], al
    and ah, 0x0F
    mov [gs:V_OTMP + 3], ah
    mov al, ORDER_INDEX + 3
    call cmos_read
    not al
    cmp al, cl
    jne .no
    xor dx, dx                      ; DL = devices taken (bit n = device n)
    xor di, di
    xor bx, bx
.take:                              ; each device once, in the saved order
    mov al, [gs:V_OTMP + bx]
    mov ah, al
    and ah, ORDER_OFF
    and al, 7
    jz .skip
    cmp al, 4
    ja .skip
    mov cl, al
    mov ch, 1
    shl ch, cl
    test dl, ch
    jnz .skip
    or dl, ch
    or al, ah
    mov [gs:V_ORDER + di], al
    inc di
.skip:
    inc bx
    cmp bx, 4
    jb .take
    mov al, 1                       ; devices not saved (an older order): added, off
.add:
    mov cl, al
    mov ch, 1
    shl ch, cl
    test dl, ch
    jnz .an
    mov ah, al
    or ah, ORDER_OFF
    mov [gs:V_ORDER + di], ah
    inc di
.an:
    inc al
    cmp al, 4
    jbe .add
    clc
    jmp short .x
.no:
    stc
.x:
    pop di
    pop dx
    pop cx
    pop bx
    pop ax
    ret

order_write:                        ; GS:V_ORDER -> CMOS 4Ah-4Dh
    push ax
    push cx
    mov al, ORDER_INDEX
    mov ah, ORDER_SIG
    call cmos_write
    mov cl, ORDER_SIG
    mov ah, [gs:V_ORDER]
    shl ah, 4
    or ah, [gs:V_ORDER + 1]
    add cl, ah
    mov al, ORDER_INDEX + 1
    call cmos_write
    mov ah, [gs:V_ORDER + 2]
    shl ah, 4
    or ah, [gs:V_ORDER + 3]
    add cl, ah
    mov al, ORDER_INDEX + 2
    call cmos_write
    mov ah, cl
    not ah
    mov al, ORDER_INDEX + 3
    call cmos_write
    pop cx
    pop ax
    ret

order_clear:                        ; back to the BIOS default
    push ax
    mov al, ORDER_INDEX
    xor ah, ah
    call cmos_write
    pop ax
    ret

; INT 19h: boot in the saved order, from the position reached so far (an
; option ROM that falls back calls INT 19h again and the order continues).
boot_by_order:
    call order_read
    jc .x
.next:
    push 0
    pop es
    movzx bx, byte [es:BOOT_NEXT]
    cmp bx, 4
    jae .done
    inc byte [es:BOOT_NEXT]
    mov al, [gs:V_ORDER + bx]
    test al, ORDER_OFF              ; switched off in the editor
    jnz .next
    cmp al, 1
    je .fd
    cmp al, 2
    je .hd
    cmp al, 3
    je .cd
    cmp al, 4
    jne .next
    call rom_boot                   ; the option ROM's boot: g_boot calls it
    jc .next
    push 0
    pop es
    mov byte [es:BOOT_STATE], 'R'
    ret
.fd:
    mov si, s_ofd
    call tty
    xor dl, dl
    call boot_drive
    mov si, s_onodisk
    call tty
    jmp .next
.hd:
    mov si, s_ohd
    call tty
    mov dl, 0x80
    call boot_drive
    mov si, s_onoboot
    call tty
    jmp .next
.cd:
    mov byte [gs:V_BOOTQ], 1
    call cd_boot
    mov byte [gs:V_BOOTQ], 0
    jmp .next
.done:
    mov byte [es:BOOT_STATE], 'E'   ; nothing booted: the stock boot follows
.x:
    ret

s_ofd:      db 13, 10, "Boot order: floppy A: ", 0
s_ohd:      db 13, 10, "Boot order: hard disk C: ", 0
s_onodisk:  db "no boot disk", 0
s_onoboot:  db "not bootable", 0

dev_name:                           ; AL = boot order device (bit 3 ignored): print its name
    and al, 7
    cmp al, 1
    jne .2
    SAY "Floppy A:"
    ret
.2:
    cmp al, 2
    jne .3
    SAY "Hard disk C:"
    ret
.3:
    cmp al, 3
    jne .4
    SAY "CD-ROM"
    ret
.4:
    SAY "Option ROM boot"
    ret

order_line:                         ; the boot order in use, in one line
    call order_read
    jnc .list
    SAY "BIOS default (option ROM boot first, then A:, C:)"
    ret
.list:
    xor bx, bx
    xor cx, cx                      ; devices printed
.l:
    mov al, [gs:V_ORDER + bx]
    test al, ORDER_OFF
    jnz .n
    jcxz .first
    push ax
    SAY ", "
    pop ax
.first:
    call dev_name
    inc cx
.n:
    inc bx
    cmp bx, 4
    jb .l
    jcxz .none
    ret
.none:
    SAY "nothing on (the stock boot only)"
    ret

; Edit the saved boot order: all four devices are always listed, each once.
; Up/Down select, +/- (or PgUp/PgDn) move the selected device, Space turns it
; on or off, S saves, D goes back to the BIOS default.
page_order:
    call order_read                 ; the saved order, or the default to start from
    mov byte [gs:V_OSEL], 0
    mov si, s_none
.draw:
    push si
    mov si, t_order
    mov bx, h_order
    call frame
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x0503
    call goto_rc
    SAY "Devices that are on are tried from the top at every boot."
    xor bx, bx
.row:
    mov dh, bl
    add dh, 7
    mov dl, 5
    call goto_rc
    mov byte [gs:V_ATTR], A_LABEL
    mov al, '1'
    add al, bl
    call putc
    SAY ".  "
    mov byte [gs:V_ATTR], A_VALUE
    cmp bl, [gs:V_OSEL]
    jne .v
    mov byte [gs:V_ATTR], A_SEL
.v:
    mov al, ' '
    call putc
    mov al, [gs:V_ORDER + bx]
    push bx
    call dev_name
    pop bx
.pad:
    cmp byte [gs:V_COL], 28
    jae .state
    mov al, ' '
    call putc
    jmp short .pad
.state:
    mov al, [gs:V_ORDER + bx]
    test al, ORDER_OFF
    jnz .off
    mov byte [gs:V_ATTR], A_OK
    SAY " on "
    jmp short .extra
.off:
    mov byte [gs:V_ATTR], A_DIM
    SAY " off  (skipped)"
.extra:
    mov al, [gs:V_ORDER + bx]
    and al, 7
    cmp al, 4
    jne .rn
    call rom_boot
    jnc .rn
    mov byte [gs:V_ATTR], A_DIM
    SAY "  no option ROM hooked the boot"
.rn:
    inc bx
    cmp bx, 4
    jb .row
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x0C03
    call goto_rc
    SAY "Missing or unbootable devices are skipped; if none boots, the stock boot", 3
    SAY "asks for a system disk. Option ROM boot is a card's own boot, such as the", 3
    SAY "PicoMEM's; when it hands back, the next device is tried. A CD-ROM with no", 3
    SAY "disc is skipped after about 2 s. F8 at the end of POST still boots any", 3
    SAY "device once."
    mov dx, 0x1203
    call goto_rc
    mov byte [gs:V_ATTR], A_LABEL
    SAY "Saved now:  "
    mov byte [gs:V_ATTR], A_VALUE
    push dword [gs:V_ORDER]         ; order_line reads CMOS into V_ORDER
    call order_line
    mov eax, [gs:V_ORDER]           ; what is saved (or the default)
    pop dword [gs:V_ORDER]
    pop si
    mov dx, 0x1503
    call goto_rc
    mov byte [gs:V_ATTR], A_OK
    cmp eax, [gs:V_ORDER]
    je .msg
    cmp si, s_none
    jne .msg
    mov byte [gs:V_ATTR], A_TITLE
    mov si, s_unsaved
.msg:
    call puts
.key:
    call getkey
    mov si, s_none
    cmp ah, 0x01
    je .x
    cmp ah, 0x48
    je .up
    cmp ah, 0x50
    je .down
    cmp ah, 0x49                    ; PgUp
    je .mup
    cmp ah, 0x51                    ; PgDn
    je .mdown
    cmp al, '+'
    je .mup
    cmp al, '='                     ; the + key without Shift
    je .mup
    cmp al, '-'
    je .mdown
    cmp al, ' '
    je .toggle
    cmp al, 0x0D
    je .toggle
    or al, 0x20
    cmp al, 's'
    je .save
    cmp al, 'd'
    je .def
    jmp short .key
.up:
    cmp byte [gs:V_OSEL], 0
    je .key
    dec byte [gs:V_OSEL]
    jmp .draw
.down:
    cmp byte [gs:V_OSEL], 3
    jae .key
    inc byte [gs:V_OSEL]
    jmp .draw
.mup:                               ; swap with the one above; the selection follows
    movzx bx, byte [gs:V_OSEL]
    test bx, bx
    jz .key
    mov ax, [gs:V_ORDER + bx - 1]
    xchg al, ah
    mov [gs:V_ORDER + bx - 1], ax
    dec byte [gs:V_OSEL]
    jmp .draw
.mdown:
    movzx bx, byte [gs:V_OSEL]
    cmp bx, 3
    jae .key
    mov ax, [gs:V_ORDER + bx]
    xchg al, ah
    mov [gs:V_ORDER + bx], ax
    inc byte [gs:V_OSEL]
    jmp .draw
.toggle:
    movzx bx, byte [gs:V_OSEL]
    xor byte [gs:V_ORDER + bx], ORDER_OFF
    jmp .draw
.save:
    call order_write
    mov si, s_osaved
    jmp .draw
.def:
    call order_clear
    mov dword [gs:V_ORDER], ORDER_DEFAULT
    mov si, s_odef
    jmp .draw
.x:
    ret

t_order:  db "Boot order", 0
h_order:  db 0x18, 0x19, " Select   +/- Move   Space On/off   S Save   D Default   Esc Back", 0
s_none:   db 0
s_osaved: db "Saved: this order is used from the next boot.", 0
s_odef:   db "Saved: the BIOS default is used from the next boot.", 0
s_unsaved: db "Not saved yet: S saves this order, Esc leaves it unchanged.", 0

; ------------------------------------------------------------------ CD-ROM boot (El Torito)
; The boot menu's "CD-ROM" choice. The stock BIOS predates El Torito, so this
; brings its own ATAPI driver (polled PIO, packet commands on the primary IDE
; channel) and, for after the boot, its own INT 13h service for the CD:
;   * floppy emulation (1.2/1.44/2.88 MB images, most DOS-era boot CDs): the
;     image is drive 00h (A:), read-only; a real floppy drive moves to B:.
;   * no emulation (ISOLINUX, newer installers): drive E0h with the INT 13h
;     extensions loaders use (41h, 42h, 48h) and El Torito's 4B00h/4B01h.
; Hard-disk emulation is rare and is refused. The service lives in this ROM;
; its data and a 2 KB sector cache take 3 KB from the top of base memory.

R_KB        equ 3                   ; KB of base memory taken for the RAM block
R_OLD13     equ 0x10                ; RAM block (DS in the CD code): previous INT 13h
C_DEV       equ 0x14                ; 0 master, 1 slave
C_MEDIA     equ 0x15                ; 0 no emulation, 1/2/3 = 1.2/1.44/2.88 MB floppy
C_DRIVE     equ 0x16                ; BIOS drive number of the CD: 00h or E0h
C_STAT      equ 0x17                ; last INT 13h status
C_RBA       equ 0x18                ; CD sector of the boot image
C_CACHE     equ 0x1C                ; CD sector held in C_BUF (-1 = none)
C_SPT       equ 0x20
C_HEADS     equ 0x21
C_CYLS      equ 0x22                ; word
C_REALFD    equ 0x24                ; 1 = a real floppy drive answers as B:
C_FUNC      equ 0x25
C_LOADSEG   equ 0x26                ; word
C_COUNT     equ 0x28                ; word, 512-byte sectors loaded at boot
C_PKT       equ 0x30                ; 12-byte ATAPI packet
C_SPEC      equ 0x40                ; 13h-byte El Torito specification packet
C_BUF       equ 0x400               ; 2048-byte sector buffer
R_CHAIN     equ cd_chain - cd_stub

; Copied to the start of the RAM block; INT 13h points here.
cd_stub:
    push ds
    push cs
    pop ds
    jmp EXT_SEG:cd_int13
cd_chain:                           ; the handler returns here (RETF) to pass a call on
    pop ds
    jmp far [cs:R_OLD13]
cd_stub_end:

tty:                                ; CS:SI, zero-terminated, through BIOS teletype
    push ax
    push bx
    push si
.l:
    mov al, [cs:si]
    inc si
    test al, al
    jz .x
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    jmp short .l
.x:
    pop si
    pop bx
    pop ax
    ret

tty_gs:                             ; GS:SI, zero-terminated
    push ax
    push bx
    push si
.l:
    mov al, [gs:si]
    inc si
    test al, al
    jz .x
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    jmp short .l
.x:
    pop si
    pop bx
    pop ax
    ret

norm_esdi:                          ; ES:DI -> same address with DI < 16
    push ax
    push bx
    mov ax, di
    shr ax, 4
    mov bx, es
    add bx, ax
    mov es, bx
    and di, 0x0F
    pop bx
    pop ax
    ret

atapi_wait:                         ; DX = 1F7, AH = status bits awaited with BSY clear (0 = none)
    push ecx                        ; -> AL = status. CF=1 after ~6-12 s
    in al, dx                       ; 400 ns before the status is valid
    in al, dx
    in al, dx
    in al, dx
    mov ecx, 6000000
.l:
    in al, dx
    test al, 0x80
    jnz .n
    test ah, ah
    jz .ok
    test al, ah
    jnz .ok
.n:
    dec ecx
    jnz .l
    stc
    jmp short .x
.ok:
    clc
.x:
    pop ecx
    ret

; Send the packet at C_PKT to the CD-ROM; data goes to ES:DI.
; CF=1 on error or timeout, AL = error register (sense key in bits 7-4).
atapi_packet:
    push bx
    push cx
    push dx
    push si
    push di
    push es
    call norm_esdi
    mov dx, 0x3F6
    mov al, 0x0A                    ; polled: no interrupts
    out dx, al
    mov dx, 0x1F6
    mov al, [C_DEV]
    shl al, 4
    or al, 0xA0
    out dx, al
    mov dx, 0x1F7
    xor ah, ah
    call atapi_wait
    jc .fail
    mov dx, 0x1F1
    xor al, al                      ; PIO data transfer
    out dx, al
    mov dx, 0x1F4
    out dx, al                      ; at most 0800h bytes (one sector) per block
    inc dx
    mov al, 0x08
    out dx, al
    mov dx, 0x1F7
    mov al, 0xA0                    ; PACKET
    out dx, al
    mov ah, 0x09                    ; wait for DRQ or ERR
    call atapi_wait
    jc .fail
    test al, 0x01
    jnz .err
    mov si, C_PKT
    mov cx, 6
    mov dx, 0x1F0
    rep outsw
    mov dx, 0x1F7
.phase:
    xor ah, ah
    call atapi_wait
    jc .fail
    test al, 0x01
    jnz .err
    test al, 0x08
    jz .done                        ; no more data: command complete
    mov dx, 0x1F4                   ; byte count of this block
    in al, dx
    mov cl, al
    inc dx
    in al, dx
    mov ch, al
    inc cx
    shr cx, 1
    mov dx, 0x1F0
    rep insw
    call norm_esdi
    mov dx, 0x1F7
    jmp short .phase
.done:
    clc
    jmp short .out
.err:
    mov dx, 0x1F1
    in al, dx
    stc
    jmp short .out
.fail:
    xor al, al
    stc
.out:
    pushf
    push ax
    mov dx, 0x1F7
    in al, dx                       ; clear any pending device interrupt
    push ds
    push 0x40
    pop ds
    mov al, [0x76]                  ; the BIOS's device-control byte
    and al, 0x0B
    mov dx, 0x3F6
    out dx, al
    and byte [0x8E], 0x7F           ; no stale "IRQ 14 seen" flag for INT 13h
    pop ds
    pop ax
    popf
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    ret

cd_read:                            ; EAX = CD sector, CX = sectors -> ES:DI. CF=1 on error
    push edx
    push si
    mov si, 4                       ; tries: the first read after a disc change reports it
.try:
    mov edx, eax
    bswap edx
    mov word [C_PKT], 0x0028        ; READ(10)
    mov [C_PKT + 2], edx
    mov byte [C_PKT + 6], 0
    mov [C_PKT + 7], ch
    mov [C_PKT + 8], cl
    mov byte [C_PKT + 9], 0
    mov word [C_PKT + 10], 0
    push ax
    call atapi_packet
    pop ax
    jnc .x
    dec si
    jnz .try
    stc
.x:
    pop si
    pop edx
    ret

cd_nomedia:                         ; REQUEST SENSE: CF=0 if the drive reports no disc (ASC 3Ah)
    push eax
    push di
    push es
    push ds
    pop es
    xor eax, eax
    mov [C_PKT], eax
    mov [C_PKT + 4], eax
    mov [C_PKT + 8], eax
    mov byte [C_PKT], 0x03
    mov byte [C_PKT + 4], 18
    mov byte [C_BUF + 12], 0
    mov di, C_BUF
    call atapi_packet
    jc .no
    cmp byte [C_BUF + 12], 0x3A
    je .yes
.no:
    stc
    jmp short .x
.yes:
    clc
.x:
    pop es
    pop di
    pop eax
    ret

cd_tur:                             ; TEST UNIT READY. CF=1 if not ready
    push eax
    xor eax, eax
    mov [C_PKT], eax
    mov [C_PKT + 4], eax
    mov [C_PKT + 8], eax
    call atapi_packet
    pop eax
    ret

vread:                              ; EAX = 512-byte sector of the boot image -> ES:DI. CF=1 on error
    push eax
    push ecx
    push si
    push di
    mov si, ax
    and si, 3
    shl si, 9
    add si, C_BUF
    shr eax, 2
    add eax, [C_RBA]
    cmp eax, [C_CACHE]
    je .copy
    mov dword [C_CACHE], -1
    push es
    push di
    push ds
    pop es
    mov di, C_BUF
    mov cx, 1
    call cd_read
    pop di
    pop es
    jc .x
    mov [C_CACHE], eax
.copy:
    mov cx, 256
    rep movsw
    clc
.x:
    pop di
    pop si
    pop ecx
    pop eax
    ret

cd_ready:                           ; wait for a disc: up to ~25 s, Esc cancels. CF=1 if none
    push bx
    push cx
    push si
    push di
    mov di, 100
.t:
    call cd_tur
    jnc .x
    cmp byte [gs:V_BOOTQ], 0        ; boot order: no disc for ~2 s -> next device
    je .slow
    cmp di, 100 - 8
    ja .slow
    call cd_nomedia
    jnc .no
.slow:
    cmp di, 99                      ; the first failure is usually just "disc changed"
    jne .dot
    mov si, s_cdwait
    call tty
.dot:
    test di, 3
    jnz .key
    mov al, '.'
    mov ah, 0x0E
    mov bx, 7
    int 0x10
.key:
    mov ah, 1
    int 0x16
    jz .wait
    xor ah, ah
    int 0x16
    cmp ah, 0x01
    je .no
.wait:
    mov cx, 250
    call delay_ms
    dec di
    jnz .t
.no:
    stc
.x:
    pop di
    pop si
    pop cx
    pop bx
    ret

; From boot_override (DS = CS, private stack). Returns only if the CD did not boot.
cd_boot:
    mov si, s_cdboot
    call tty
    call ide_scan
    xor bx, bx
    cmp byte [gs:V_IDTYPE], 2
    je .found
    inc bx
    cmp byte [gs:V_IDTYPE + 1], 2
    je .found
    mov si, s_cdnodrv
    jmp .say
.found:
    imul si, bx, 41
    add si, V_IDNAME
    call tty_gs
    push 0x40
    pop es
    sub word [es:0x13], R_KB        ; RAM block at the top of base memory
    mov ax, [es:0x13]
    shl ax, 6
    mov es, ax
    xor di, di
    mov si, cd_stub
    mov cx, cd_stub_end - cd_stub
    rep movsb
    xor al, al
    mov cx, C_BUF - (cd_stub_end - cd_stub)
    rep stosb
    push es
    pop ds                          ; DS = RAM block from here on
    mov [C_DEV], bl
    mov dword [C_CACHE], -1
    call cd_ready
    mov si, s_cdready
    jc .fail
    push ds
    pop es
    mov di, C_BUF                   ; boot record volume descriptor
    mov eax, 17
    mov cx, 1
    call cd_read
    mov si, s_cdnoboot
    jc .fail
    cmp dword [C_BUF], 0x30444300   ; 00h "CD0"
    jne .fail
    cmp word [C_BUF + 4], "01"      ; "01": "CD001", version 1
    jne .fail
    push si
    push cs
    pop es
    mov si, C_BUF + 7
    mov di, s_eltorito
    mov cx, 23
    repe cmpsb
    pop si
    jne .fail
    push ds
    pop es
    mov eax, [C_BUF + 0x47]         ; boot catalog
    mov di, C_BUF
    mov cx, 1
    call cd_read
    jc .fail
    xor ax, ax                      ; validation entry: header 1, key 55AAh, words sum to 0
    mov di, C_BUF
    mov cx, 16
.sum:
    add ax, [di]
    add di, 2
    loop .sum
    test ax, ax
    jnz .fail
    cmp byte [C_BUF], 1
    jne .fail
    cmp word [C_BUF + 0x1E], 0xAA55
    jne .fail
    cmp byte [C_BUF + 0x20], 0x88   ; initial entry: bootable
    jne .fail
    mov al, [C_BUF + 0x21]
    and al, 0x0F
    mov si, s_cdhd
    cmp al, 4
    jae .fail
    mov [C_MEDIA], al
    mov ax, [C_BUF + 0x22]
    test ax, ax
    jnz .seg
    mov ax, 0x07C0
.seg:
    mov [C_LOADSEG], ax
    mov ax, [C_BUF + 0x26]
    mov [C_COUNT], ax
    mov eax, [C_BUF + 0x28]
    mov [C_RBA], eax
    mov dword [C_CACHE], -1         ; the buffer held the catalog
    mov byte [C_DRIVE], CD_DRIVE
    mov cx, 4                       ; a no-emulation count of 0 means one CD sector
    cmp byte [C_MEDIA], 0
    je .cnt
    mov byte [C_DRIVE], 0
    mov word [C_CYLS], 80
    mov byte [C_HEADS], 2
    mov al, 15
    cmp byte [C_MEDIA], 1
    je .spt
    mov al, 18
    cmp byte [C_MEDIA], 2
    je .spt
    mov al, 36
.spt:
    mov [C_SPT], al
    mov cx, 1
.cnt:
    cmp word [C_COUNT], 0
    jne .fit
    mov [C_COUNT], cx
.fit:
    mov si, s_cdnoboot              ; image must fit between 7000h and the RAM block
    cmp word [C_LOADSEG], 0x0700
    jb .fail
    movzx eax, word [C_COUNT]
    shl eax, 5
    movzx ecx, word [C_LOADSEG]
    add eax, ecx
    mov cx, ds
    cmp eax, ecx
    ja .fail
    mov es, [C_LOADSEG]             ; load the boot image
    xor di, di
    xor eax, eax
    mov cx, [C_COUNT]
.load:
    call vread
    mov si, s_cdread
    jc .fail
    mov dx, es
    add dx, 0x20
    mov es, dx
    inc eax
    loop .load
    mov byte [C_SPEC], 0x13         ; El Torito specification packet for INT 13h AX=4B01h
    mov al, [C_MEDIA]
    mov [C_SPEC + 1], al
    mov al, [C_DRIVE]
    mov [C_SPEC + 2], al
    mov eax, [C_RBA]
    mov [C_SPEC + 4], eax
    mov al, [C_DEV]
    mov [C_SPEC + 8], al
    mov ax, [C_LOADSEG]
    mov [C_SPEC + 12], ax
    mov ax, [C_COUNT]
    mov [C_SPEC + 14], ax
    cmp byte [C_MEDIA], 0
    je .hook
    mov byte [C_SPEC + 16], 79      ; last cylinder, sectors per track, last head
    mov al, [C_SPT]
    mov [C_SPEC + 17], al
    mov byte [C_SPEC + 18], 1
    push 0x40                       ; the CD is A:; a real floppy drive becomes B:
    pop es
    mov al, [es:0x10]
    mov ah, al
    and al, 0x3E
    or al, 0x01
    test ah, 0x01
    jz .one
    or al, 0x40
    mov byte [C_REALFD], 1
.one:
    mov [es:0x10], al
.hook:
    push 0
    pop es
    cli
    mov eax, [es:0x13 * 4]
    mov [R_OLD13], eax
    mov word [es:0x13 * 4], 0
    mov [es:0x13 * 4 + 2], ds
    sti
    mov si, s_cdnoemu
    cmp byte [C_MEDIA], 0
    je .msg
    mov si, s_cdemu
    call tty
    mov si, s_cdrealb
    cmp byte [C_REALFD], 0
    jne .msg
    mov si, s_cdnl
.msg:
    call tty
    mov dl, [C_DRIVE]
    mov bx, [C_LOADSEG]
    xor ax, ax
    mov ds, ax
    mov es, ax
    cmp bx, 0x07C0
    jne .far
    jmp 0x0000:0x7C00
.far:
    push bx
    push ax
    retf
.fail:
    push 0x40
    pop es
    add word [es:0x13], R_KB        ; give the memory back
.say:
    call tty
    mov si, s_cdtail
    mov cx, 2000
    cmp byte [gs:V_BOOTQ], 0
    je .tail
    mov si, s_cdnext                ; boot order: straight on to the next device
    mov cx, 300
.tail:
    call tty
    call delay_ms
    ret

s_eltorito: db "EL TORITO SPECIFICATION"
s_cdboot:   db 13, 10, "CD-ROM boot: ", 0
s_cdwait:   db 13, 10, "  waiting for the disc (Esc cancels) ", 0
s_cdnodrv:  db "no CD-ROM drive found on the IDE channel", 0
s_cdready:  db 13, 10, "  no disc, or the drive did not become ready", 0
s_cdnoboot: db 13, 10, "  this disc is not bootable (no El Torito boot image)", 0
s_cdhd:     db 13, 10, "  hard-disk emulation boot images are not supported", 0
s_cdread:   db 13, 10, "  read error while loading the boot image", 0
s_cdtail:   db 13, 10, "Using the normal boot order.", 13, 10, 0
s_cdnext:   db 13, 10, "Trying the next boot device.", 0
s_cdnoemu:  db 13, 10, "  El Torito, no emulation: the CD is drive E0h", 13, 10, 0
s_cdemu:    db 13, 10, "  El Torito, floppy emulation: the CD is drive A:", 0
s_cdrealb:  db ", the floppy drive is B:"
s_cdnl:     db 13, 10, 0

; INT 13h after a CD boot. From the RAM stub: DS = RAM block, caller's DS on the stack.
cd_int13:
    cmp dl, [C_DRIVE]
    je cd_own
    cmp ah, 0x4B
    jne .notq
    cmp dl, 0x7F                    ; El Torito "any drive" status query
    je cd_own
.notq:
    cmp dl, 1
    jne .chain
    cmp byte [C_REALFD], 0
    jne .remap
.chain:
    push ds
    push word R_CHAIN
    retf                            ; the stub restores DS and jumps to the old INT 13h
.remap:                             ; B: is the real drive A:
    mov [C_FUNC], ah
    mov dl, 0
    pushf
    call far [R_OLD13]
    pushf
    mov dl, 1
    cmp byte [C_FUNC], 0x08
    jne .rm
    mov dl, 2                       ; drive count: the CD and the real drive
.rm:
    popf
    pop ds
    retf 2

; Frame after PUSHAD: DI 0, SI 4, BX 16, DX 20, CX 24, AX 28, ES 32, caller DS 34.
cd_own:
    sti
    cld
    push es
    pushad
    mov bp, sp
    mov si, cd_funcs
.f:
    mov al, [cs:si]
    cmp al, 0xFF
    je cdf_bad
    cmp al, [bp + 29]
    je .hit
    add si, 3
    jmp short .f
.hit:
    jmp word [cs:si + 1]

cd_funcs:
    db 0x00
    dw cdf_ok
    db 0x01
    dw cdf_status
    db 0x02
    dw cdf_read
    db 0x03
    dw cdf_wp
    db 0x04
    dw cdf_ok
    db 0x05
    dw cdf_wp
    db 0x08
    dw cdf_params
    db 0x0D
    dw cdf_ok
    db 0x10
    dw cdf_ok
    db 0x15
    dw cdf_type
    db 0x16
    dw cdf_floppy
    db 0x17
    dw cdf_floppy
    db 0x18
    dw cdf_media
    db 0x41
    dw cdf_ext
    db 0x42
    dw cdf_xread
    db 0x43
    dw cdf_wp
    db 0x44
    dw cdf_ok
    db 0x47
    dw cdf_ok
    db 0x48
    dw cdf_xparams
    db 0x4B
    dw cdf_spec
    db 0xFF

cdf_ok:
    mov byte [bp + 29], 0
cd_ret:                             ; AH in the frame = status, CF = status not zero
    mov al, [bp + 29]
    mov [C_STAT], al
    popad
    pop es
    pop ds
    test ah, ah
    jnz .e
    retf 2
.e:
    stc
    retf 2

cd_ret_nc:                          ; return with CF=0 whatever AH is
    mov byte [C_STAT], 0
    popad
    pop es
    pop ds
    clc
    retf 2

cdf_bad:
    mov byte [bp + 29], 0x01        ; invalid function
    jmp short cd_ret

cdf_wp:
    mov byte [bp + 29], 0x03        ; write-protected
    jmp short cd_ret

cdf_status:
    mov al, [C_STAT]
    mov [bp + 29], al
    popad
    pop es
    pop ds
    clc
    retf 2

cdf_type:                           ; 15h: floppy without change line
    cmp byte [C_MEDIA], 0
    je cdf_bad
    mov byte [bp + 29], 0x01
    jmp short cd_ret_nc

cdf_floppy:                         ; 16h (disc not changed), 17h
    cmp byte [C_MEDIA], 0
    je cdf_bad
    jmp short cdf_ok

cdf_media:                          ; 18h: ES:DI = diskette parameter table
    cmp byte [C_MEDIA], 0
    je cdf_bad
    xor ax, ax
    mov es, ax
    mov eax, [es:0x1E * 4]
    mov [bp], ax
    shr eax, 16
    mov [bp + 32], ax
    jmp short cdf_ok

cdf_params:                         ; 08h
    cmp byte [C_MEDIA], 0
    je cdf_bad
    mov word [bp + 28], 0
    mov al, [C_MEDIA]
    shl al, 1                       ; drive type 2/4/6 = 1.2/1.44/2.88 MB
    mov [bp + 16], al
    mov byte [bp + 17], 0
    mov ax, [C_CYLS]
    dec ax
    mov [bp + 25], al
    shl ah, 6
    or ah, [C_SPT]
    mov [bp + 24], ah
    mov al, [C_HEADS]
    dec al
    mov [bp + 21], al
    mov al, [C_REALFD]
    inc al
    mov [bp + 20], al
    xor ax, ax
    mov es, ax
    mov eax, [es:0x1E * 4]
    mov [bp], ax
    shr eax, 16
    mov [bp + 32], ax
    jmp cdf_ok

cdf_read:                           ; 02h: AL sectors, CH/CL cylinder and sector, DH head, ES:BX
    cmp byte [C_MEDIA], 0
    je cdf_bad
    movzx ebx, byte [bp + 24]
    mov ax, bx
    and bx, 0x3F                    ; sector
    shl ax, 2
    and ax, 0x300
    mov al, [bp + 25]               ; cylinder
    test bl, bl
    jz .nf
    cmp bl, [C_SPT]
    ja .nf
    cmp ax, [C_CYLS]
    jae .nf
    mov cl, [bp + 21]
    cmp cl, [C_HEADS]
    jae .nf
    movzx eax, ax
    movzx ecx, byte [C_HEADS]
    imul eax, ecx
    movzx ecx, byte [bp + 21]
    add eax, ecx
    movzx ecx, byte [C_SPT]
    imul eax, ecx
    dec bx
    add eax, ebx                    ; image sector
    movzx esi, word [C_CYLS]
    movzx ecx, byte [C_HEADS]
    imul esi, ecx
    movzx ecx, byte [C_SPT]
    imul esi, ecx                   ; sectors in the image
    mov es, [bp + 32]
    mov di, [bp + 16]
    movzx cx, byte [bp + 28]
    xor dx, dx
.l:
    jcxz .done
    cmp eax, esi
    jae .end
    call vread
    jc .err
    mov bx, es
    add bx, 0x20
    mov es, bx
    inc eax
    inc dx
    dec cx
    jmp short .l
.done:
    mov [bp + 28], dl
    jmp cdf_ok
.end:
    mov [bp + 28], dl
.nf:
    mov byte [bp + 29], 0x04        ; sector not found
    jmp cd_ret
.err:
    mov [bp + 28], dl
    mov byte [bp + 29], 0x20        ; controller failure
    jmp cd_ret

cdf_ext:                            ; 41h: extensions present (fixed-disk access subset)
    cmp byte [C_MEDIA], 0
    jne cdf_bad
    cmp word [bp + 16], 0x55AA
    jne cdf_bad
    mov word [bp + 16], 0xAA55
    mov byte [bp + 29], 0x21        ; EDD 1.1
    mov word [bp + 24], 0x0001
    jmp cd_ret_nc

cdf_xread:                          ; 42h: DS:SI = disk address packet (2048-byte sectors)
    cmp byte [C_MEDIA], 0
    jne cdf_bad
    mov es, [bp + 34]
    mov si, [bp + 4]
    mov eax, [es:si + 8]
    mov cx, [es:si + 2]
    les di, [es:si + 4]
    xor dx, dx
.l:
    test cx, cx
    jz .ok
    mov bx, cx
    cmp bx, 16
    jbe .n
    mov bx, 16
.n:
    push cx
    mov cx, bx
    call cd_read
    pop cx
    jc .err
    movzx ebx, bx
    add eax, ebx
    add dx, bx
    sub cx, bx
    shl bx, 7                       ; 2048 bytes = 128 paragraphs per sector
    mov si, es
    add si, bx
    mov es, si
    jmp short .l
.ok:
    mov byte [bp + 29], 0
    jmp short .count
.err:
    mov byte [bp + 29], 0x20
.count:
    mov es, [bp + 34]
    mov si, [bp + 4]
    mov [es:si + 2], dx             ; sectors transferred
    jmp cd_ret

cdf_xparams:                        ; 48h: drive parameters
    cmp byte [C_MEDIA], 0
    jne cdf_bad
    mov es, [bp + 34]
    mov di, [bp + 4]
    cmp word [es:di], 0x1A
    jb cdf_bad
    mov word [es:di], 0x1A
    mov word [es:di + 2], 0x0074    ; removable, change line, lockable
    push di
    add di, 4
    xor ax, ax
    mov cx, 10
    rep stosw
    pop di
    mov word [es:di + 24], 2048
    jmp cdf_ok

cdf_spec:                           ; 4B00h/4B01h: El Torito specification packet -> DS:SI
    cmp byte [bp + 28], 1
    ja cdf_bad
    mov es, [bp + 34]
    mov di, [bp + 4]
    mov si, C_SPEC
    mov cx, 0x13
    rep movsb
    jmp cdf_ok

; ------------------------------------------------------------------ large disks (LBA)
; The stock INT 13h (F000:94E3) addresses disks by physical CHS, which ends at
; 1024/16/63 = 504 MB. After POST's disk init, every hard disk set to
; Automatic that supports LBA and holds more is switched to large-disk mode:
;   * INT 13h AH=02h-15h use the standard LBA-assisted translation
;     (32/64/128/255 heads, 63 sectors, at most 1024 cylinders = 8.4 GB) and
;     ATA LBA commands, polled PIO.
;   * The INT 13h extensions 41h-44h, 47h, 48h (EDD 1.1) reach the whole disk
;     (28-bit LBA: up to 128 GB), for FAT32 and LBA partitions.
;   * INT 41h/46h point at translated parameter tables (signature A0h).
; Other drives keep the stock handler. Like the stock auto-detect (which
; writes F000:E411), the tables live in the shadowed F000 segment, written
; at POST with the shadow unlocked (chipset 9Bh bit 0); INT 13h points
; straight at this ROM and keeps its working state on the stack, so no base
; memory is taken. A disk partitioned with the old 504 MB limit can keep it
; by setting it to the user type 1024/16/63 in Hard disk setup.

HD_DATA     equ 0xEED6              ; F000: 30h bytes, reserved by the chunk below
D_JMP       equ 0x00                ; EAh + previous INT 13h: the chain to the stock code
D_FLAG      equ 0x06                ; 1 = drive 80h/81h in LBA mode
D_TOTAL     equ 0x08                ; 2 dwords: LBA sectors
D_FDPT      equ 0x10                ; 2 x 16 bytes: translated parameter tables
D_SIZE      equ 0x30
HD_CHAINJ   equ HD_DATA + D_JMP
V_HTMP      equ 0x140               ; VARSEG: the data, built at POST
L_LBA       equ -4                  ; locals below the INT 13h frame
L_LEFT      equ -6
L_DONE      equ -8
L_CNT       equ -10
L_DEV       equ -11
L_MODE      equ -12                 ; 0 read, 1 write, 2 verify
L_N         equ -13
L_SIZE      equ 14

hdinit_entry:                       ; far, from POST right after its disk init
    ENTER
    call hd_setup
    LEAVE
    retf

hd_setup:
    push 0x40
    pop es
    mov cl, [es:0x75]               ; hard disks POST counted
    test cl, cl
    jz .x
    mov di, V_HTMP
    xor al, al
.z:
    mov [gs:di], al
    inc di
    cmp di, V_HTMP + D_SIZE
    jb .z
    mov al, 0x12
    call cmos_read
    mov ch, al                      ; drive types
    xor bx, bx
.dev:
    cmp bl, cl
    jae .done
    mov al, ch
    shr al, 4
    mov ah, 2                       ; C: Automatic
    test bl, bl
    jz .auto
    mov al, ch
    and al, 0x0F
    mov ah, 3                       ; D: Automatic
.auto:
    cmp al, ah
    jne .next
    push cx
    call ide_identify               ; BX = device -> AL = 1 for an ATA disk, data in V_IDBUF
    pop cx
    cmp al, 1
    jne .next
    test byte [gs:V_IDBUF + 99], 2  ; LBA supported
    jz .next
    mov eax, [gs:V_IDBUF + 120]     ; LBA sectors
    cmp eax, 1024 * 16 * 63
    jbe .next                       ; fits the stock 504 MB: leave it alone
    cmp eax, 0x0FFFFFFF
    jbe .t
    mov eax, 0x0FFFFFFF
.t:
    push cx
    mov si, bx
    mov byte [gs:V_HTMP + D_FLAG + si], 1
    shl si, 2
    mov [gs:V_HTMP + D_TOTAL + si], eax
    mov si, bx
    shl si, 4
    add si, V_HTMP + D_FDPT         ; GS:SI = this drive's table
    mov ecx, 1024 * 32 * 63         ; heads: the fewest of 32/64/128/255 that fit
    mov dl, 32
.h:
    cmp eax, ecx
    jbe .hs
    shl ecx, 1
    shl dl, 1
    jnz .h
    mov dl, 255
.hs:
    mov [gs:si + 2], dl             ; logical heads
    movzx ecx, dl
    imul ecx, ecx, 63
    xor edx, edx
    div ecx                         ; cylinders
    cmp eax, 1024
    jbe .c
    mov eax, 1024
.c:
    mov [gs:si], ax                 ; logical cylinders
    mov byte [gs:si + 3], 0xA0      ; translated table
    mov al, [gs:V_IDBUF + 12]
    mov [gs:si + 4], al             ; physical sectors
    mov word [gs:si + 5], 0xFFFF    ; no precompensation
    mov byte [gs:si + 8], 0x08      ; more than 8 heads
    mov ax, [gs:V_IDBUF + 2]
    mov [gs:si + 9], ax             ; physical cylinders
    mov [gs:si + 12], ax            ; landing zone
    mov al, [gs:V_IDBUF + 6]
    mov [gs:si + 11], al            ; physical heads
    mov byte [gs:si + 14], 63       ; logical sectors
    xor ax, ax
    mov cx, 15
.ck:
    add al, [gs:si]
    inc si
    loop .ck
    neg al
    mov [gs:si], al                 ; bytes sum to 0
    pop cx
.next:
    inc bx
    jmp .dev
.done:
    mov ax, [gs:V_HTMP + D_FLAG]
    test ax, ax
    jz .x
    push 0
    pop ds
    mov byte [gs:V_HTMP + D_JMP], 0xEA
    mov eax, [0x13 * 4]             ; chain: jmp far to the stock INT 13h
    mov [gs:V_HTMP + D_JMP + 1], eax
    push 0xF000
    pop es
    call shadow_open
    mov di, HD_DATA
    mov si, V_HTMP
    mov cx, D_SIZE
.cp:
    mov al, [gs:si]
    stosb
    inc si
    loop .cp
    mov ax, [0x7000]                ; a RAM read before locking, as POST does
    call shadow_lock
    mov di, HD_DATA                 ; did it stick? (no shadow RAM: stay on the stock code)
    mov si, V_HTMP
    mov cx, D_SIZE
.vf:
    mov al, [gs:si]
    cmp al, [es:di]
    jne .x
    inc si
    inc di
    loop .vf
    cli
    mov word [0x13 * 4], hd_int13
    mov word [0x13 * 4 + 2], EXT_SEG
    cmp byte [gs:V_HTMP + D_FLAG], 0
    je .d1
    mov word [0x41 * 4], HD_DATA + D_FDPT
    mov word [0x41 * 4 + 2], 0xF000
.d1:
    cmp byte [gs:V_HTMP + D_FLAG + 1], 0
    je .d2
    mov word [0x46 * 4], HD_DATA + D_FDPT + 16
    mov word [0x46 * 4 + 2], 0xF000
.d2:
    sti
.x:
    push cs
    pop ds
    ret

shadow_open:                        ; chipset 9Bh bit 0 clear: the F000 shadow is writable
    push ax
    mov al, 0x9B
    call chip_read
    and al, 0xFE
    jmp short shadow_set
shadow_lock:
    push ax
    mov al, 0x9B
    call chip_read
    or al, 0x01
shadow_set:
    mov ah, al
    mov al, 0x9B
    pushf
    cli
    out 0x22, al
    mov al, ah
    out 0x24, al
    popf
    pop ax
    ret

; INT 13h for large disks. Not ours: straight on to the stock handler.
hd_int13:
    cmp dl, 0x80
    jb .chain
    cmp dl, 0x81
    ja .chain
    push ds
    push 0xF000
    pop ds
    push bx
    movzx bx, dl
    cmp byte [bx + HD_DATA + D_FLAG - 0x80], 0
    pop bx
    jne hd_own
    pop ds
.chain:
    jmp 0xF000:HD_CHAINJ

; DS = F000. Frame after PUSHAD: DI 0, SI 4, BX 16, DX 20, CX 24, AX 28,
; ES 32, caller DS 34; locals below BP.
hd_own:
    sti
    cld
    push es
    pushad
    mov bp, sp
    sub sp, L_SIZE
    mov al, [bp + 20]
    sub al, 0x80
    mov [bp + L_DEV], al
    mov si, hd_funcs
.f:
    mov al, [cs:si]
    cmp al, 0xFF
    je hdf_bad
    cmp al, [bp + 29]
    je .hit
    add si, 3
    jmp short .f
.hit:
    jmp word [cs:si + 1]

hd_funcs:
    db 0x00
    dw hdf_ok
    db 0x01
    dw hdf_status
    db 0x02
    dw hdf_rw
    db 0x03
    dw hdf_rw
    db 0x04
    dw hdf_rw
    db 0x05
    dw hdf_ok
    db 0x08
    dw hdf_params
    db 0x09
    dw hdf_ok
    db 0x0C
    dw hdf_ok
    db 0x0D
    dw hdf_ok
    db 0x10
    dw hdf_ok
    db 0x11
    dw hdf_ok
    db 0x12
    dw hdf_ok
    db 0x13
    dw hdf_ok
    db 0x14
    dw hdf_ok
    db 0x15
    dw hdf_type
    db 0x41
    dw hdf_ext
    db 0x42
    dw hdf_xrw
    db 0x43
    dw hdf_xrw
    db 0x44
    dw hdf_xrw
    db 0x47
    dw hdf_ok
    db 0x48
    dw hdf_xparams
    db 0xFF

hd_setstat:                         ; 40:74 = AL (last hard disk status)
    push ds
    push 0x40
    pop ds
    mov [0x74], al
    pop ds
    ret

hdf_ok:
    mov byte [bp + 29], 0
hd_ret:                             ; AH in the frame = status (also 40:74), CF = status not zero
    mov al, [bp + 29]
    call hd_setstat
    mov sp, bp
    popad
    pop es
    pop ds
    test ah, ah
    jnz .e
    retf 2
.e:
    stc
    retf 2

hd_ret_nc:                          ; CF=0 whatever AH is; status 0
    xor al, al
    call hd_setstat
    mov sp, bp
    popad
    pop es
    pop ds
    clc
    retf 2

hdf_bad:
    mov byte [bp + 29], 0x01
    jmp short hd_ret

hdf_status:
    push ds
    push 0x40
    pop ds
    mov al, [0x74]
    pop ds
    mov [bp + 29], al
    mov sp, bp
    popad
    pop es
    pop ds
    clc
    retf 2

hdf_params:                         ; 08h: logical geometry
    call hd_table
    mov word [bp + 28], 0
    mov ax, [si]
    dec ax                          ; last cylinder
    mov [bp + 25], al
    shl ah, 6
    or ah, [si + 14]
    mov [bp + 24], ah
    mov al, [si + 2]
    dec al
    mov [bp + 21], al
    push ds
    push 0x40
    pop ds
    mov al, [0x75]
    pop ds
    mov [bp + 20], al
    jmp hdf_ok

hdf_type:                           ; 15h: fixed disk, CX:DX = sectors
    call hd_table
    call hd_chs_total
    mov [bp + 20], ax
    shr eax, 16
    mov [bp + 24], ax
    mov byte [bp + 29], 0x03
    jmp hd_ret_nc

hd_table:                           ; -> SI = this drive's translated table
    movzx si, byte [bp + L_DEV]
    shl si, 4
    add si, HD_DATA + D_FDPT
    ret

hd_chs_total:                       ; SI = table -> EAX = cylinders x heads x sectors
    movzx eax, word [si]
    movzx edx, byte [si + 2]
    imul eax, edx
    movzx edx, byte [si + 14]
    imul eax, edx
    ret

hdf_rw:                             ; 02h/03h/04h: AL sectors at CH/CL/DH, ES:BX
    call hd_table
    movzx ebx, byte [bp + 24]
    mov ax, bx
    shl ax, 2
    and ax, 0x300
    mov al, [bp + 25]               ; cylinder
    and bx, 0x3F                    ; sector
    jz .nf
    cmp bl, [si + 14]
    ja .nf
    cmp ax, [si]
    jae .nf
    movzx ecx, byte [bp + 21]
    cmp cl, [si + 2]
    jae .nf
    movzx eax, ax
    movzx edx, byte [si + 2]
    imul eax, edx
    add eax, ecx
    movzx edx, byte [si + 14]
    imul eax, edx
    dec bx
    add eax, ebx                    ; LBA
    movzx cx, byte [bp + 28]
    test cx, cx
    jz hdf_bad
    mov dl, [bp + 29]
    sub dl, 2                       ; 0 read, 1 write, 2 verify
    mov [bp + L_MODE], dl
    mov es, [bp + 32]
    mov di, [bp + 16]
    call ata_xfer
    mov [bp + 28], dl               ; sectors done
    mov [bp + 29], ah
    jmp hd_ret
.nf:
    mov byte [bp + 28], 0
    mov byte [bp + 29], 0x04        ; sector not found
    jmp hd_ret

hdf_ext:                            ; 41h
    cmp word [bp + 16], 0x55AA
    jne hdf_bad
    mov word [bp + 16], 0xAA55
    mov byte [bp + 29], 0x21        ; EDD 1.1
    mov word [bp + 24], 0x0001      ; fixed-disk access subset
    jmp hd_ret_nc

hdf_xrw:                            ; 42h/43h/44h: DS:SI = disk address packet
    mov dl, [bp + 29]
    sub dl, 0x42
    mov [bp + L_MODE], dl
    mov es, [bp + 34]
    mov si, [bp + 4]
    cmp dword [es:si + 12], 0       ; 28-bit LBA only
    jne .nf
    mov eax, [es:si + 8]
    mov cx, [es:si + 2]
    les di, [es:si + 4]
    call ata_xfer
    mov [bp + 29], ah
.count:
    mov es, [bp + 34]
    mov si, [bp + 4]
    mov [es:si + 2], dx             ; sectors transferred
    jmp hd_ret
.nf:
    xor dx, dx
    mov byte [bp + 29], 0x04
    jmp short .count

hdf_xparams:                        ; 48h
    mov es, [bp + 34]
    mov di, [bp + 4]
    cmp word [es:di], 0x1A
    jb hdf_bad
    call hd_table
    mov word [es:di], 0x1A
    mov word [es:di + 2], 0x0002    ; geometry valid
    movzx eax, word [si]
    mov [es:di + 4], eax
    movzx eax, byte [si + 2]
    mov [es:di + 8], eax
    movzx eax, byte [si + 14]
    mov [es:di + 12], eax
    movzx bx, byte [bp + L_DEV]
    shl bx, 2
    mov eax, [bx + HD_DATA + D_TOTAL]
    mov [es:di + 16], eax
    mov dword [es:di + 20], 0
    mov word [es:di + 24], 512
    jmp hdf_ok

; EAX = LBA, CX = sectors, ES:DI = buffer, L_DEV, L_MODE. -> DX = sectors done,
; AH = BIOS status (0 = good). Up to 128 sectors per ATA command.
ata_xfer:
    mov [bp + L_LBA], eax
    mov [bp + L_LEFT], cx
    mov word [bp + L_DONE], 0
    movzx ebx, byte [bp + L_DEV]    ; past the end of the disk?
    shl bx, 2
    movzx ecx, cx
    add eax, ecx
    jc .range
    cmp eax, [bx + HD_DATA + D_TOTAL]
    ja .range
    call norm_esdi
    mov dx, 0x3F6
    mov al, 0x0A                    ; polled: no interrupts
    out dx, al
.chunk:
    mov cx, [bp + L_LEFT]
    test cx, cx
    jz .good
    cmp cx, 128
    jbe .n
    mov cx, 128
.n:
    mov [bp + L_N], cl
    mov [bp + L_CNT], cx
    mov dx, 0x1F6
    mov eax, [bp + L_LBA]
    shr eax, 24
    and al, 0x0F
    or al, 0xE0                     ; LBA
    mov ah, [bp + L_DEV]
    shl ah, 4
    or al, ah
    out dx, al
    mov dx, 0x1F7
    mov ah, 0x40                    ; ready
    call atapi_wait
    jc .timeout
    mov dx, 0x1F2
    mov al, cl
    out dx, al
    inc dx
    mov eax, [bp + L_LBA]
    out dx, al
    inc dx
    mov al, ah
    out dx, al
    inc dx
    shr eax, 16
    out dx, al
    mov dx, 0x1F7
    mov al, 0x20                    ; READ SECTORS
    cmp byte [bp + L_MODE], 1
    jb .cmd
    mov al, 0x30                    ; WRITE SECTORS
    je .cmd
    mov al, 0x40                    ; READ VERIFY SECTORS
.cmd:
    out dx, al
    cmp byte [bp + L_MODE], 2
    je .verify
.sector:
    mov ah, 0x09                    ; DRQ or ERR
    call atapi_wait
    jc .timeout
    test al, 0x01
    jnz .err
    mov cx, 256
    mov dx, 0x1F0
    cmp byte [bp + L_MODE], 0
    jne .w
    rep insw
    jmp short .moved
.w:
    push ds
    push es
    pop ds
    mov si, di
    rep outsw
    pop ds
    add di, 512
.moved:
    call norm_esdi
    mov dx, 0x1F7
    inc word [bp + L_DONE]
    dec byte [bp + L_N]
    jnz .sector
    cmp byte [bp + L_MODE], 1       ; a write: wait until it is on the disk
    jne .next
.verify:
    xor ah, ah
    call atapi_wait
    jc .timeout
    test al, 0x01
    jnz .err
    cmp byte [bp + L_MODE], 2
    jne .next
    mov ax, [bp + L_CNT]            ; verify: the whole command at once
    add [bp + L_DONE], ax
.next:
    movzx eax, word [bp + L_CNT]
    add [bp + L_LBA], eax
    sub [bp + L_LEFT], ax
    jmp .chunk
.good:
    xor ah, ah
    jmp short .out
.range:
    mov ah, 0x04
    xor dx, dx
    ret
.timeout:
    mov ah, 0x80
    jmp short .out
.err:
    mov dx, 0x1F1
    in al, dx
    mov ah, 0x10                    ; UNC: uncorrectable data
    test al, 0x40
    jnz .out
    mov ah, 0x04                    ; IDNF: sector not found
    test al, 0x10
    jnz .out
    mov ah, 0x0A                    ; BBK: bad sector
    test al, 0x80
    jnz .out
    mov ah, 0xBB                    ; anything else: undefined error
.out:
    push ax
    mov dx, 0x1F7
    in al, dx
    push ds
    push 0x40
    pop ds
    mov al, [0x76]
    and al, 0x0B
    mov dx, 0x3F6
    out dx, al
    and byte [0x8E], 0x7F
    pop ds
    pop ax
    mov dx, [bp + L_DONE]
    ret

; ------------------------------------------------------------------ memory test

page_memtest:
    mov si, t_mem
    mov bx, h_mem1
    call frame
    mov byte [gs:V_ATTR], A_VALUE
    mov dx, 0x0503
    call goto_rc
    SAY "Tests every byte of RAM except the first 64 KB, with three patterns:", 3
    SAY "each address holding its own address, a 55h/AAh checkerboard (both ways)", 3
    SAY "and all zeros / all ones. It runs until you press Esc.", 3, 3
    SAY 1, A_LABEL, "Conventional  ", 1, A_VALUE, "64 KB - "
    call base_kb
    call putdec
    SAY " KB", 3
    SAY 1, A_LABEL, "Extended      ", 1, A_VALUE, "1 MB - "
    call ext_kb
    add eax, 1024
    call putdec
    SAY " KB", 3, 3
    SAY 1, A_TITLE, "Press Enter to start, Esc to go back."
.k:
    call getkey
    cmp ah, 0x01
    je .back
    cmp al, 0x0D
    jne .k
    call memtest_run
.back:
    clc
    ret

memtest_run:
    mov si, t_mem
    mov bx, h_mem2
    call frame
    call flat_on
    call a20_on
    mov dword [gs:V_ERRS], 0
    mov word [gs:V_PASS], 0
    mov byte [gs:V_NLOG], 0
    mov byte [gs:V_STOP], 0
    call a20_check
    jnc .pass
    mov byte [gs:V_ATTR], A_BAD
    mov dx, 0x0503
    call goto_rc
    SAY "Gate A20 did not open: only conventional memory is tested."
.pass:
    inc word [gs:V_PASS]
    xor bp, bp                      ; test number 0..4
.test:
    mov ax, bp
    mov [gs:V_TEST], al
    call base_kb                    ; conventional: 64 KB .. base
    shl eax, 10
    mov dword [gs:V_START], 0x10000
    mov [gs:V_END], eax
    call sweep
    cmp byte [gs:V_STOP], 0
    jne .stop
    call a20_check
    jc .noext
    call ext_kb
    shl eax, 10
    add eax, 0x100000
    mov dword [gs:V_START], 0x100000
    mov [gs:V_END], eax
    call sweep
    cmp byte [gs:V_STOP], 0
    jne .stop
.noext:
    inc bp
    cmp bp, 5
    jb .test
    jmp .pass
.stop:
    call a20_off
    mov byte [gs:V_ATTR], A_TITLE
    mov dx, 0x1503
    call goto_rc
    SAY "Stopped. ", 1, A_VALUE
    movzx eax, word [gs:V_PASS]
    dec eax
    call putdec
    SAY " full pass(es), "
    mov eax, [gs:V_ERRS]
    call putdec
    SAY " error(s). Press any key."
    call getkey
    ret

; Write the whole range with the current test's pattern, then verify it,
; in 64 KB steps, updating the screen and watching for Esc.
sweep:
    mov byte [gs:V_TMP+3], 0        ; phase 0 = write, 1 = verify
.phase:
    mov edi, [gs:V_START]
.chunk:
    cmp edi, [gs:V_END]
    jae .phase_done
    call status_line
    mov ecx, 16384                  ; dwords in 64 KB
    mov eax, [gs:V_END]
    sub eax, edi
    shr eax, 2
    cmp ecx, eax
    jbe .n
    mov ecx, eax
.n:
    cmp byte [gs:V_TMP+3], 0
    jne .verify
.write:
    call pattern
    mov [fs:edi], eax
    add edi, 4
    dec ecx
    jnz .write
    jmp short .after
.verify:
    call pattern
    cmp [fs:edi], eax
    jne .error
.vnext:
    add edi, 4
    dec ecx
    jnz .verify
.after:
    mov ah, 1
    int 0x16
    jz .chunk
    xor ax, ax
    int 0x16
    cmp ah, 0x01
    jne .chunk
    mov byte [gs:V_STOP], 1
    ret
.error:
    call log_error
    jmp short .vnext
.phase_done:
    cmp byte [gs:V_TMP+3], 0
    jne .done
    mov byte [gs:V_TMP+3], 1
    jmp .phase
.done:
    ret

pattern:                            ; EAX = expected dword at EDI for the current test
    movzx ax, byte [gs:V_TEST]
    cmp al, 0
    jne .p1
    mov eax, edi                    ; own address
    ret
.p1:
    cmp al, 3
    jae .solid
    mov eax, edi                    ; checkerboard by dword
    shr eax, 2
    and eax, 1
    neg eax                         ; 0 or FFFFFFFF
    xor eax, 0x55555555
    cmp byte [gs:V_TEST], 2
    jne .r
    not eax
.r:
    ret
.solid:
    mov eax, 0
    cmp byte [gs:V_TEST], 3
    je .r
    dec eax
    ret

log_error:                          ; EDI, expected EAX, actual at FS:EDI
    pushad
    inc dword [gs:V_ERRS]
    movzx bx, byte [gs:V_NLOG]
    cmp bx, 6
    jb .room
    mov bx, 5                       ; keep the latest six: shift up
    push ds
    push gs
    pop ds
    push es
    push gs
    pop es
    mov si, V_LOG + 12
    mov di, V_LOG
    mov cx, 60
    rep movsb
    pop es
    pop ds
    jmp short .put
.room:
    inc byte [gs:V_NLOG]
.put:
    imul bx, bx, 12
    mov [gs:V_LOG + bx], edi
    mov [gs:V_LOG + bx + 4], eax
    mov eax, [fs:edi]
    mov [gs:V_LOG + bx + 8], eax
    popad
    ret

status_line:                        ; pass, test, progress bar and error log
    pushad
    mov byte [gs:V_ATTR], A_LABEL
    mov dx, 0x0703
    call goto_rc
    SAY "Pass    "
    mov byte [gs:V_ATTR], A_VALUE
    movzx eax, word [gs:V_PASS]
    call putdec
    SAY "   "
    mov byte [gs:V_ATTR], A_LABEL
    mov dx, 0x0803
    call goto_rc
    SAY "Test    "
    mov byte [gs:V_ATTR], A_VALUE
    movzx si, byte [gs:V_TEST]
    shl si, 1
    mov si, [cs:testnames + si]
    call puts
    mov si, s_writing
    cmp byte [gs:V_TMP+3], 0
    je .w
    mov si, s_verifying
.w:
    call puts
    mov byte [gs:V_ATTR], A_LABEL
    mov dx, 0x0903
    call goto_rc
    SAY "Address "
    mov byte [gs:V_ATTR], A_VALUE
    mov eax, edi
    mov cl, 8
    call puthex
    SAY "  of  "
    mov eax, [gs:V_END]
    call puthex
    ; bar: 60 cells over the current range
    mov dx, 0x0B03
    call goto_rc
    mov eax, edi
    sub eax, [gs:V_START]
    imul eax, eax, 60
    mov ecx, [gs:V_END]
    sub ecx, [gs:V_START]
    jnz .r
    inc ecx
.r:
    xor edx, edx
    div ecx                         ; 0..60
    cmp eax, 60
    jbe .b
    mov eax, 60
.b:
    mov cx, ax
    mov byte [gs:V_ATTR], A_OK
    jcxz .rest
.fill:
    mov al, 0xDB
    call putc
    loop .fill
.rest:
    mov cx, 60
    movzx ax, byte [gs:V_COL]
    sub ax, 3
    sub cx, ax
    jbe .errs
    mov byte [gs:V_ATTR], A_DIM
.e:
    mov al, 0xB0
    call putc
    loop .e
.errs:
    mov byte [gs:V_ATTR], A_LABEL
    mov dx, 0x0D03
    call goto_rc
    SAY "Errors  "
    mov byte [gs:V_ATTR], A_OK
    mov eax, [gs:V_ERRS]
    test eax, eax
    jz .z
    mov byte [gs:V_ATTR], A_BAD
.z:
    call putdec
    mov byte [gs:V_ATTR], A_DIM
    SAY "      (address  expected  read)"
    movzx cx, byte [gs:V_NLOG]
    xor bx, bx
    mov dh, 14
.log:
    jcxz .x
    push cx
    mov dl, 11
    call goto_rc
    mov byte [gs:V_ATTR], A_BAD
    mov eax, [gs:V_LOG + bx]
    mov cl, 8
    call puthex
    SAY "  "
    mov eax, [gs:V_LOG + bx + 4]
    call puthex
    SAY "  "
    mov eax, [gs:V_LOG + bx + 8]
    call puthex
    pop cx
    add bx, 12
    inc dh
    loop .log
.x:
    popad
    ret

testnames: dw tn0, tn1, tn2, tn3, tn4
tn0: db "1/5 own address   ", 0
tn1: db "2/5 checkerboard  ", 0
tn2: db "3/5 inverted board", 0
tn3: db "4/5 all zeros     ", 0
tn4: db "5/5 all ones      ", 0
s_writing: db "  writing  ", 0
s_verifying: db "  checking ", 0
t_mem: db "Memory test", 0
h_mem1: db "Enter Start   Esc Back", 0
h_mem2: db "Esc Stop", 0

; Flat real mode: FS gets a 4 GB limit (base 0) via a short trip to protected mode.
flat_on:
    pushf
    cli
    push eax
    o32 lgdt [cs:gdtr]
    mov eax, cr0
    or al, 1
    mov cr0, eax
    jmp short .pm
.pm:
    mov ax, 8
    mov fs, ax
    mov eax, cr0
    and al, 0xFE
    mov cr0, eax
    jmp short .rm
.rm:
    xor ax, ax
    mov fs, ax
    pop eax
    popf
    ret
align 8
gdt:
    dq 0
    dw 0xFFFF, 0x0000
    db 0x00, 0x92, 0xCF, 0x00
gdtr:
    dw 15
    dd 0xE8000 + gdt

kbc_wait:
    push cx
    xor cx, cx
.l:
    in al, 0x64
    test al, 2
    jz .x
    loop .l
.x:
    pop cx
    ret

a20_on:
    call kbc_wait
    mov al, 0xD1
    out 0x64, al
    call kbc_wait
    mov al, 0xDF
    out 0x60, al
    call kbc_wait
    ret

a20_off:
    call kbc_wait
    mov al, 0xD1
    out 0x64, al
    call kbc_wait
    mov al, 0xDD
    out 0x60, al
    call kbc_wait
    ret

a20_check:                          ; CF=1 if 1 MB wraps to 0 (A20 closed)
    push eax
    push ebx
    mov ebx, [fs:dword 0x600]
    mov dword [fs:dword 0x100600], 0x13572468
    mov dword [fs:dword 0x600], 0x2468ACE0
    cmp dword [fs:dword 0x100600], 0x13572468
    mov [fs:dword 0x600], ebx
    pop ebx
    pop eax
    je .ok
    stc
    ret
.ok:
    clc
    ret

; ------------------------------------------------------------------ end-of-POST summary

page_summary:
    call cls
    mov byte [gs:V_ATTR], A_BOX
    mov dx, 0x0000
    call goto_rc
    mov al, 0xC9
    call putc
    mov cx, 78
    mov al, 0xCD
.t:
    call putc
    loop .t
    mov al, 0xBB
    call putc
    mov dx, 0x0100
    call goto_rc
    mov al, 0xBA
    call putc
    mov byte [gs:V_ATTR], A_VALUE
    SAY " NCR System 3230 ", 1, A_DIM, 0xFA, 1, A_VALUE, " System summary"
    mov dx, 0x014F
    call goto_rc
    mov byte [gs:V_ATTR], A_BOX
    mov al, 0xBA
    call putc
    mov dx, 0x0200
    call goto_rc
    mov al, 0xC8
    call putc
    mov cx, 78
    mov al, 0xCD
.b:
    call putc
    loop .b
    mov al, 0xBC
    call putc
    mov byte [gs:V_ATTR], A_DIM
    mov dx, 0x1203
    call goto_rc
    SAY "Gathering drive details..."
    call ide_scan
    mov dx, 0x1203
    mov cx, 40
    mov byte [gs:V_ATTR], A_BG
    mov al, ' '
    call hline
    mov dh, 4
    mov si, l_cpu
    call label
    call cpu_name
    mov dh, 5
    mov si, l_speed
    call label
    call speed_value
    mov dh, 6
    mov si, l_fpu
    call label
    mov si, s_fpu_yes
    cmp byte [gs:V_FPU], 0
    jne .f
    mov si, s_fpu_no
.f:
    call puts
    mov dh, 7
    mov si, l_mem
    call label
    call base_kb
    call putdec
    SAY " KB base + "
    call ext_kb
    call putdec
    SAY " KB extended"
    mov dh, 8
    mov si, l_cache
    call label
    call l1_value
    mov dh, 9
    mov si, l_l2
    call label
    call l2_value
    mov dh, 11
    mov si, l_fda
    call label
    mov al, 0x10
    call cmos_read
    push ax
    shr al, 4
    call floppy_name
    mov dh, 12
    mov si, l_fdb
    call label
    pop ax
    and al, 0x0F
    call floppy_name
    mov dh, 13
    mov si, l_ide0
    call label
    xor bx, bx
    call ide_line
    mov dh, 14
    mov si, l_ide1
    call label
    mov bx, 1
    call ide_line
    mov dh, 16
    mov si, l_ports
    call label
    call ports_line
    mov dh, 17
    mov si, l_video
    call label
    call video_value
    mov dh, 18
    mov si, l_order
    call label
    call order_line
    ; footer and a 3 second wait (any key ends it; the key is left for POST)
    mov byte [gs:V_ATTR], A_BAR
    mov dx, 0x1800
    mov cx, 80
    mov al, ' '
    call hline
    mov dx, 0x1801
    call goto_rc
    SAY "F1 Setup  F8 Boot menu  F10 Tools  Space holds  other keys boot"
    push es
    mov ax, 0x40
    mov es, ax
    mov bx, [es:0x6C]
    mov cl, 0xFF                    ; seconds last shown
    xor di, di
    mov si, 100                     ; fall-back if the timer does not tick
.wait:
    mov ax, [es:0x6C]
    sub ax, bx
    cmp ax, SUMMARY_TICKS
    jae .end
    neg ax                          ; seconds left, rounded up
    add ax, SUMMARY_TICKS + 17
    xor dx, dx
    push bx
    mov bx, 18
    div bx
    pop bx
    cmp al, cl
    je .key
    mov cl, al
    push ax
    mov dx, 0x184A
    call goto_rc
    mov byte [gs:V_ATTR], A_BAR
    pop ax
    movzx eax, al
    call putdec
    SAY " s "
.key:
    mov ah, 1
    int 0x16
    jnz .pressed
    dec di
    jnz .wait
    dec si
    jnz .wait
    jmp short .end
.pressed:
    cmp al, ' '                     ; Space: keep the summary until another key
    jne .end
    xor ah, ah
    int 0x16
    mov dx, 0x184A
    call goto_rc
    SAY "held "
.hold:
    mov ah, 1
    int 0x16
    jz .hold
    cmp ax, 0x3B00                  ; F1, F8, F10 are left for POST to act on
    je .end
    cmp ax, 0x4200
    je .end
    cmp ax, 0x4400
    je .end
    xor ah, ah
    int 0x16                        ; any other key boots (taken, so POST ignores it)
.end:
    pop es
    ret
l_mem: db "Memory", 0
l_order: db "Boot order", 0
l_cache: db "Level 1 cache", 0

align 2, db 0                       ; the checksum covers whole words
ext_end:
