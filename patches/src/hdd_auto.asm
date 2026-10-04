; Hard disks on "Automatic" by default, and absent drives skipped quietly.
;
; Stock behaviour after the CMOS settings are lost (no battery, or a bad
; checksum): POST loads defaults with both hard disks "Not installed", and the
; disk init (F000:9062) also returns at once because CMOS 0Eh says the
; settings were bad. The defaults never get valid checksums either, so they are
; reloaded, with the same warning, on every boot until Setup saves them.
; A hard disk is therefore ignored until it is set up again by hand.
;
; Now:
;   * Defaults set C: and D: to type 2/3, "Automatic" (IDENTIFY at each boot),
;     and store valid checksums (10h-2Dh in 2Eh/2Fh, NCR 44h-47h in 7Eh/7Fh).
;   * The disk init runs after a settings loss too. Every path that sets the
;     0Eh error bits loads these defaults in the same boot, so the drive types
;     it sees are always sane.
;   * Before the controller test, each "Automatic" drive is probed. If nothing
;     answers (floating bus, status 00h for the slave, or registers that do
;     not hold a written value),
;     it is dropped from the count without "Disk controller failure", the
;     countdown or a phantom drive. Drives with a fixed type, or USERHDD's
;     type 1, are handled exactly as before.

CMOS_RD     equ 0x93E7              ; AL = index|80h -> AL = value
DEFS_NEW    equ 0xEE69
PROBE_NEW   equ 0x9F5B

;@ F000:21BB max=0x30
;; defaults: was 10h = 40h, 44h = E5h, 47h = 4Eh; now through the new routine
    call DEFS_NEW
    jmp short 0x21EB

;@ F000:90C4 max=5
;; disk init: no longer skipped when CMOS 0Eh reports lost settings
    jmp short 0x90C9
    nop
    nop
    nop

;@ F000:9131 max=3
;; was: mov dx, 80h (before the controller test); the probe returns DX = 80h
    call PROBE_NEW

;@ F000:EE69 max=0xEE free
;; CMOS defaults: floppy A: 1.44 MB, C: and D: automatic, NCR bytes, checksums
    mov ax, 0x9040                  ; (index, value) pairs
    call .w
    mov ax, 0x9223
    call .w
    mov ax, 0xC4E5
    call .w
    mov ax, 0xC74E
    call .w
    xor dx, dx                      ; standard checksum over 10h-2Dh
    mov ah, 0x90
.s1:
    mov al, ah
    call CMOS_RD
    add dl, al
    adc dh, 0
    inc ah
    cmp ah, 0xAE
    jne .s1
    mov ah, 0xAE
    mov al, dh
    call .w
    mov ah, 0xAF
    mov al, dl
    call .w
    xor dx, dx                      ; NCR checksum over 44h-47h
    mov ah, 0xC4
.s2:
    mov al, ah
    call CMOS_RD
    add dl, al
    adc dh, 0
    inc ah
    cmp ah, 0xC8
    jne .s2
    mov ah, 0xFE
    mov al, dh
    call .w
    mov ah, 0xFF
    mov al, dl
.w:                                 ; CMOS[AH] = AL (AH has the NMI bit)
    xchg al, ah
    out 0x70, al
    out 0xEB, al
    out 0xEB, al
    xchg al, ah
    out 0x71, al
    out 0xEB, al
    out 0xEB, al
    ret

;@ F000:9F5B max=0xA5 free
;; probe "Automatic" drives; DS = 40h. Returns DX = 80h, or leaves the disk
;; init when C: is not there.
    push ax
    mov al, 0x92
    call CMOS_RD
    mov ah, al
    and al, 0x0F
    cmp al, 3                       ; D: automatic and counted?
    jne .c
    cmp byte [0x75], 2
    jne .c
    mov al, 1
    call .present
    jnc .c
    mov byte [0x75], 1              ; nothing as slave: no D:
.c:
    and ah, 0xF0
    cmp ah, 0x20                    ; C: automatic?
    jne .go
    xor al, al
    call .present
    jnc .go
    mov byte [0x75], 0              ; no master: no hard disks at all
    pop ax
    add sp, 2                       ; drop our return address
    ret                             ; return from the disk init
.go:
    pop ax
    mov dx, 0x80
    ret
.present:                           ; AL = device 0/1 -> CF=1 if nothing answers
    push ax
    push dx
    mov ah, al
    shl al, 4
    or al, 0xA0
    mov dx, 0x1F6
    out dx, al
    mov dx, 0x1F7
    in al, dx                       ; 400 ns for the status to settle
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    cmp al, 0xFF                    ; floating bus
    je .no
    test al, 0x80
    jnz .yes                        ; busy: a disk still spinning up
    test al, al
    jnz .regs
    test ah, ah
    jnz .no                         ; 00h for device 1: device 0 answering for it
.regs:
    mov dx, 0x1F2                   ; registers that hold what is written
    mov al, 0x55
    out dx, al
    inc dx
    mov al, 0xAA
    out dx, al
    dec dx
    in al, dx
    cmp al, 0x55
    jne .no
    inc dx
    in al, dx
    cmp al, 0xAA
    jne .no
.yes:
    clc
    jmp short .x
.no:
    stc
.x:
    pop dx
    pop ax
    ret
