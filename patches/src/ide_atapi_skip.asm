; Recognise an ATAPI CD-ROM where a hard-disk type is configured and skip it.
;
; Stock POST resets each configured drive, then calls INT 13h AH=10h ("drive
; ready") up to 31000 times with a ~1 ms delay each (F000:9150). A CD-ROM
; never reports ready to the hard-disk command set, so POST sits ~32 s, prints
; "Disk 0 failure / Drive not ready" and still counts a phantom hard disk.
;
; Now, before that loop, the device is asked IDENTIFY PACKET DEVICE (A1h).
; A hard disk aborts it at once and POST carries on exactly as before. A
; CD-ROM answers; POST prints a note, drops that drive and any after it from
; the hard-disk count (40:75), and continues. Interrupts from the device are
; masked (nIEN) during the probe so no stale "IRQ 14 seen" flag is left.

PRINT     equ 0x4D06            ; POST message printer: skips 1 id byte, stops at '@'
CHECK     equ 0xA000
DSEG      equ 0x40

;@ F000:9150 max=3
;; was: mov bx, 7918h   (start of the drive-ready retry loop)
    call CHECK

;@ F000:A000 max=0x140 free
;; stack on entry: [sp] = return (9153), [sp+2] = drive (80h/81h) pushed by POST
    push bp
    mov bp, sp
    push ax
    push cx
    push dx
    push ds
    mov ax, DSEG
    mov ds, ax
    mov dx, 0x3F6
    mov al, 0x0A                ; nIEN: no IRQ 14 during the probe
    out dx, al
    mov dx, 0x1F6
    mov al, [bp+4]
    and al, 1
    shl al, 4
    or al, 0xA0
    out dx, al                  ; select the device
    mov dx, 0x1F7
    xor cx, cx
.busy:
    in al, dx
    test al, 0x80
    jz .idle
    loop .busy
    jmp .not_atapi              ; still busy (disk spinning up): leave it to POST
.idle:
    mov al, 0xA1                ; IDENTIFY PACKET DEVICE
    out dx, al
    in al, dx                   ; give the device 400 ns before trusting status
    in al, dx
    in al, dx
    in al, dx
    xor cx, cx
.wait:
    in al, dx
    test al, 0x80
    jnz .again
    test al, 0x09               ; DRQ or ERR
    jnz .answered
.again:
    loop .wait
    jmp .not_atapi
.answered:
    test al, 0x08
    jz .not_atapi               ; ERR: aborted, so it is an ATA hard disk
    mov dx, 0x1F0
    mov cx, 256
.drain:
    in ax, dx                   ; read and discard the IDENTIFY PACKET data
    loop .drain
    call .restore
    mov al, [bp+4]
    and al, 1
    mov [0x75], al              ; hard disks = drives before this one
    push si
    mov si, msg0
    test al, al
    jz .print
    mov si, msg1
.print:
    call PRINT
    pop si
    pop ds
    pop dx
    pop cx
    pop ax
    pop bp
    add sp, 2                   ; drop our return address
    pop dx                      ; the drive POST pushed
    ret                         ; return from the POST disk init (F000:9062)
.not_atapi:
    call .restore
    pop ds
    pop dx
    pop cx
    pop ax
    pop bp
    mov bx, 0x7918              ; the instruction we replaced
    ret
.restore:
    mov dx, 0x1F7
    in al, dx                   ; clear any pending device interrupt
    mov dx, 0x3F6
    mov al, [0x76]              ; control byte POST uses for 3F6h
    and al, 0x0B                ; without SRST
    out dx, al
    and byte [0x8E], 0x7F       ; no stale "IRQ 14 seen" flag
    ret
msg0: db 0, "Disk 0: CD-ROM (ATAPI) found - not a hard disk, skipped", 13, 10, "@"
msg1: db 0, "Disk 1: CD-ROM (ATAPI) found - not a hard disk, skipped", 13, 10, "@"
; Note: a hard disk aborts A1h with status 51h (DRDY|DSC|ERR). The BIOS's
; ready test (sub_991F) accepts that; the next real command clears ERR.
