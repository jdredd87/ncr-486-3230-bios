; Fancy boot screen, coloured POST messages, a Setup switch for them, and credits.
;
; * Splash (F000:32A5): POST clears the screen and prints "ROM BIOS Version".
;   Before that, the screen is now painted blue and a double-line banner is
;   typed in: "NCR System 3230 . 486 BIOS v2.03.00 . Enhanced Edition 1.0"
;   (the version comes from version.inc), a small colour stripe, and "Enhanced by StevenC & Claude .
;   Press <F1> for SETUP". About 0.3 s. Monochrome adapters get the banner
;   without colour; other video modes get nothing.
; * Coloured messages (F000:4D11, the POST message printer): while the blue
;   screen is up, errors print in red, "**" warnings in yellow, and the "_"
;   list markers as cyan bullets. On any other screen (black background,
;   e.g. after POST or with the splash off) messages print exactly as before.
; * Setup switch: CMOS 48h (unused by the stock BIOS) = A5h turns all of the
;   above off; any other value leaves it on, so a battery-less machine keeps
;   it on. Setup's F2 screen shows "Fancy Boot Screen: Yes/No" and F3 toggles
;   it (written to CMOS at once).
; * Credits on Setup's title line.

%include "version.inc"

VERSION_LINE equ 0x4C88       ; prints "ROM BIOS Version ..."
SPLASH       equ 0xEC60
CPUTS        equ 0xA240
F2DRAW       equ 0xA300       ; far, called from the Setup module
F2TOGGLE     equ 0xA303       ; far
FLAG_INDEX   equ 0xC8         ; CMOS 48h, NMI kept masked as POST/Setup do
FLAG_OFF     equ 0xA5
M_STUB_DRAW  equ 0x3B71       ; Setup-module stubs (FA40 segment)
M_STUB_KEY   equ 0x3B74
M_TITLE      equ 0x3BA0       ; new Setup title string (FA40 segment)
SETUP_F2VAL  equ 0x08DF       ; Setup: draws the F2 screen's current values
SETUP_BEEP   equ 0x1A83       ; Setup: teletype AL (used with AL=7 to beep)

; ------------------------------------------------------------------ POST hooks

;@ F000:32A5 max=3
;; was: call 4C88 (version line). The splash draws first, then jumps there.
    call SPLASH

;@ F000:4D11 max=16
;; the message printer's character loop now goes through CPUTS
    call CPUTS
    jmp short 0x4D21
    times 11 nop

; ------------------------------------------------------------------ splash

;@ F000:EC60 max=0x2F0 free
;; splash: paints the screen and banner, sets the cursor to row 5, then
;; tail-jumps to the version line so POST continues exactly as before
splash:
    pusha
    push ds
    push es
    pushf
    cli
    mov al, FLAG_INDEX
    out 0x70, al
    in al, 0x71
    popf
    cmp al, FLAG_OFF
    je near .skip
    mov ax, 0x40
    mov ds, ax
    mov al, [0x49]              ; current video mode
    mov bx, 0xB800
    xor bp, bp                  ; bp = 1 for monochrome
    cmp al, 3
    je .go
    cmp al, 2
    je .go
    cmp al, 7
    jne near .skip
    mov bx, 0xB000
    inc bp
.go:
    mov es, bx
    cld
    test bp, bp
    jnz .border
    xor di, di
    mov ax, 0x1720              ; light grey on blue, whole screen
    mov cx, 2000
    rep stosw
.border:
    mov ah, 0x1B                ; bright cyan on blue
    call xlat
    xor di, di                  ; row 0: top edge
    mov al, 0xC9
    stosw
    mov al, 0xCD
    mov cx, 78
    rep stosw
    mov al, 0xBB
    stosw
    mov al, 0xBA                ; rows 1-2: sides
    mov [es:160*1], ax
    mov [es:160*1+158], ax
    mov [es:160*2], ax
    mov [es:160*2+158], ax
    mov di, 160*3               ; row 3: bottom edge
    mov al, 0xC8
    stosw
    mov al, 0xCD
    mov cx, 78
    rep stosw
    mov al, 0xBC
    stosw
    mov di, 160*1+4
    mov si, row1
    call typeline
    mov di, 160*2+4
    mov si, row2
    push es                     ; tools extension present at E800:0000?
    mov ax, 0xE800
    mov es, ax
    cmp word [es:0], 'NC'
    jne .notools
    cmp word [es:2], 'RX'
    jne .notools
    mov si, row2t
.notools:
    pop es
    call typeline
    mov ah, 2
    mov bh, 0
    mov dx, 0x0500              ; POST text continues on row 5
    int 0x10
.skip:
    pop es
    pop ds
    popa
    jmp VERSION_LINE

; Type a line: CS:SI = text with 01h,attr escapes, 0-terminated; ES:DI = target.
typeline:
    mov dl, 0x17
.next:
    mov al, [cs:si]
    inc si
    or al, al
    jz .end
    cmp al, 1
    jne .char
    mov dl, [cs:si]
    inc si
    jmp short .next
.char:
    mov ah, dl
    call xlat
    stosw
    mov ax, 0x1FDB              ; bright block ahead of the text
    call xlat
    mov [es:di], ax
    call delay
    jmp short .next
.end:
    mov ax, 0x1720              ; remove the block
    call xlat
    mov [es:di], ax
    ret

; Monochrome: map attribute AH to normal (07h) or bright (0Fh).
xlat:
    test bp, bp
    jz .done
    test ah, 0x08
    mov ah, 0x07
    jz .done
    mov ah, 0x0F
.done:
    ret

; About 2 ms: count refresh toggles on port 61h bit 4 (15 us each),
; with a guard so a stuck bit cannot hang POST.
delay:
    push ax
    push cx
    push dx
    mov cx, 130
    in al, 0x61
    and al, 0x10
    mov ah, al
.wait:
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
    loop .wait
    pop dx
    pop cx
    pop ax
    ret

row1:
    db 1, 0x1F, "NCR System 3230"
    db 1, 0x13, " ", 0xFA, " "
    db 1, 0x17, "486 BIOS v2.03.00"
    db 1, 0x13, " ", 0xFA, " "
    db 1, 0x1F, "Enhanced Edition ", ED_VERSION, 1, 0x17, "   "
    db 1, 0x1C, 0xDC, 1, 0x1E, 0xDC, 1, 0x1A, 0xDC, 1, 0x1B, 0xDC, 1, 0x19, 0xDC, 1, 0x1D, 0xDC
    db 0
row2:
    db 1, 0x1E, "Enhanced by StevenC & Claude"
    db 1, 0x13, "  ", 0xFA, "  "
    db 1, 0x1A, "Press <F1> for SETUP"
    db 0
row2t:
    db 1, 0x1E, "Enhanced by StevenC & Claude"
    db 1, 0x13, "  ", 0xFA, "  "
    db 1, 0x1F, "F1", 1, 0x17, " Setup  "
    db 1, 0x1F, "F8", 1, 0x17, " Boot menu  "
    db 1, 0x1F, "F10", 1, 0x17, " Tools"
    db 0

; ------------------------------------------------------------------ coloured messages

;@ F000:A240 max=0xC0 free
;; CPUTS: print ES:SI up to '@' (SI ends after it), like the original loop.
;; Colours only when the cell under the cursor has a blue background.
cputs:
    push dx
    push ds
    mov ax, 0x40
    mov ds, ax
    mov al, [0x49]
    cmp al, 3
    je .colour
    cmp al, 2
    jne .plain
.colour:
    mov ah, 8
    mov bh, 0
    int 0x10                    ; AH = attribute under the cursor
    mov al, ah
    and al, 0x70
    cmp al, 0x10
    jne .plain
    mov dh, ah                  ; DH = base attribute
    and dh, 0xF0
    mov dl, ah                  ; DL = text attribute
    cmp byte [es:si], '*'
    jne .scan
    mov dl, dh
    or dl, 0x0E                 ; "**" warning: yellow
.scan:                          ; "rro" / "RRO" / "ilu" / "ILU" anywhere: error, red
    push si
.look:
    mov al, [es:si]
    inc si
    cmp al, '@'
    je .looked
    mov ah, [es:si]
    mov bl, 'o'
    cmp ax, 0x7272              ; "rr" ... "o" (not "Interrupt")
    je .third
    mov bl, 'O'
    cmp ax, 0x5252              ; "RR" ... "O" (not "INTERRUPT CONTROLLERS")
    je .third
    mov bl, 'u'
    cmp ax, 0x6C69              ; "il" ... "u"
    je .third
    mov bl, 'U'
    cmp ax, 0x4C49              ; "IL" ... "U"
    jne .look
.third:
    cmp [es:si+1], bl
    jne .look
.err:
    mov dl, dh
    or dl, 0x0C
.looked:
    pop si
.next:
    mov al, [es:si]
    inc si
    cmp al, '@'
    je .done
    mov bl, dl
    cmp al, '_'
    jne .print
    mov al, 0x10                ; list marker -> cyan bullet
    mov bl, dh
    or bl, 0x0B
.print:
    cmp al, 0x0E                ; BEL, BS, LF, CR: teletype only (10h bullet gets colour)
    jb .tty
    mov ah, 9                   ; character with colour ...
    mov bh, 0
    mov cx, 1
    int 0x10
.tty:
    mov ah, 0x0E                ; ... then teletype to advance the cursor
    mov bh, 0
    int 0x10
    jmp short .next
.plain:                         ; exactly the original loop
    mov bh, 0
    mov ah, 0x0E
    mov al, [es:si]
    inc si
    cmp al, '@'
    je .done
    int 0x10
    jmp short .plain
.done:
    pop ds
    pop dx
    ret

; ------------------------------------------------------------------ Setup F2 option (far)

;@ F000:A300 max=0xF8 free
;; F2DRAW: label, value and help line on Setup's F2 screen.
;; F2TOGGLE: flip CMOS 48h and redraw the value. Both far, both keep all registers.
    jmp near f2draw
    jmp near f2toggle

f2draw:
    pusha
    push ds
    push es
    call savecur
    mov dx, 0x0E03              ; copy the label colour from "Boot from Flex Disk"
    call getattr
    mov dx, 0x0E27              ; row 14, column 39
    mov si, label
    call putsat
    call drawval
    mov dx, 0x1625              ; key colour from "ESC" (row 22, column 37)
    call getattr
    mov dx, 0x1525              ; row 21, column 37
    mov si, helpkey
    call putsat
    mov dx, 0x1629              ; help text colour (row 22, column 41)
    call getattr
    mov dx, 0x1529
    mov si, helptext
    call putsat
    jmp short f2out

f2toggle:
    pusha
    push ds
    push es
    call savecur
    call readflag
    cmp al, FLAG_OFF
    mov al, FLAG_OFF
    jne .write
    xor al, al
.write:
    mov ah, al
    pushf
    cli
    mov al, FLAG_INDEX
    out 0x70, al
    mov al, ah
    out 0x71, al
    popf
    call drawval
f2out:
    pop dx                      ; saved cursor (pushed by savecur's caller frame)
    mov ah, 2
    mov bh, 0
    int 0x10
    pop es
    pop ds
    popa
    retf

savecur:                        ; push the cursor position under our return address
    pop si
    mov ah, 3
    mov bh, 0
    int 0x10
    push dx
    jmp si

drawval:
    mov dx, 0x0443              ; value colour from row 4, column 67
    call getattr
    call readflag
    mov si, yes
    cmp al, FLAG_OFF
    jne .show
    mov si, no
.show:
    mov dx, 0x0E41              ; row 14, column 65
    jmp short putsat

readflag:
    pushf
    cli
    mov al, FLAG_INDEX
    out 0x70, al
    in al, 0x71
    popf
    ret

getattr:                        ; BL = attribute at row DH, column DL
    mov ah, 2
    mov bh, 0
    int 0x10
    mov ah, 8
    int 0x10
    mov bl, ah
    ret

putsat:                         ; CS:SI at row DH, column DL in colour BL
    mov al, [cs:si]
    inc si
    or al, al
    jz .end
    push dx
    mov ah, 2
    mov bh, 0
    int 0x10
    mov ah, 9
    mov cx, 1
    int 0x10
    pop dx
    inc dl
    jmp short putsat
.end:
    ret

label:    db "Fancy Boot Screen:", 0
yes:      db " Yes", 0
no:       db "  No", 0
helpkey:  db "F3", 0
helptext: db "Fancy boot screen on/off", 0

; ------------------------------------------------------------------ Setup module hooks

;@ FA40:084D max=3
;; F2 screen: was "call 08DF" (draw values); now also draws the new option
    call M_STUB_DRAW

;@ FA40:0B31 max=5
;; F2 key loop, unknown key: was "mov al,7 / call 1A83" (beep); F3 now toggles
    call M_STUB_KEY
    nop
    nop

;@ FA40:1965 max=2
;; Setup title string pointer (inline argument, offset from 20B0h)
    dw M_TITLE - 0x20B0

;@ FA40:3B71 max=0x2F free
;; stubs inside the Setup module (segment FA40)
    jmp near stub_draw
    jmp near stub_key
stub_draw:
    call SETUP_F2VAL
    call 0xF000:F2DRAW
    ret
stub_key:
    cmp ax, 0x003D              ; F3
    jne .beep
    call 0xF000:F2TOGGLE
    ret
.beep:
    mov al, 7
    call SETUP_BEEP
    ret

;@ FA40:3BA0 max=0x60 free
;; Setup title: column 3, row 0
    db 3, 0
    db "Setup, Version 2.01.00 (3230)   "
    db "Enhanced Edition ", ED_VERSION, " by StevenC & Claude", 13, 10, 0
