; POST prompts continue on their own after a short countdown.
;
; Stock POST stops and waits for a key at two prompts:
;   * battery / configuration / time / memory-size problems (F000:4775):
;     "Press <F1> for SETUP or <ENTER> to go on", then waits forever;
;   * any other error, e.g. "Disk controller failure" (F000:47A1):
;     "Press <ENTER> to continue", then waits forever.
; Now each prompt shows "continuing in Ns" and counts down (3 s and 5 s).
; ENTER, F1 (Setup) or Ctrl-D during the countdown are handed to the
; original key handler at F000:478A, so they behave exactly as before.
; Any other key is ignored. When the countdown ends, POST carries on at
; F000:47AF, the normal boot path. A poll counter backs up the timer tick,
; so the countdown ends even if the tick were not running.
; Replaces battery_prompt (same idea for the first prompt only).

BEEPS     equ 0x4F60          ; original "beep three times"
PRINT     equ 0x4D06          ; POST message printer (SI = message id byte)
KEYLOOP   equ 0x478A          ; original wait for F1 / ENTER / Ctrl-D
CONTINUE  equ 0x47AF          ; normal path: continue booting
PROMPT_A  equ 0xA140
PROMPT_B  equ 0xA143

;@ F000:4781 max=3
;; battery/config prompt: was "call 4F60" (beeps), then a wait for a key
    call PROMPT_A

;@ F000:47AA max=3
;; other errors: was "call 4D06" (print "Press <ENTER> to continue"), then a wait
    call PROMPT_B

;@ F000:A140 max=0x100 free
;; countdown routines; each returns to KEYLOOP (key pressed) or CONTINUE
    jmp near prompt_a
    jmp near prompt_b

prompt_a:
    call BEEPS
    mov cl, 3
    mov si, msg_a
    jmp short countdown

prompt_b:
    call PRINT                  ; "Press <ENTER> to continue" (SI set by POST)
    mov cl, 5
    mov si, msg_b

; CL = seconds, CS:SI = text to print before the number.
; The caller's return address is replaced with KEYLOOP or CONTINUE.
countdown:
    push bp
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    sti
    call puts
    mov ax, 0x40
    mov ds, ax
.second:
    mov al, cl
    add al, '0'
    call putc
    mov al, 's'
    call putc
    mov bx, [0x6C]              ; BIOS tick count, 18.2 per second
    xor di, di                  ; poll counter (backup for the tick)
    mov dh, 4
.poll:
    mov ah, 1
    int 0x16                    ; key waiting?
    jz .nokey
    cmp al, 0x0D                ; ENTER
    je .handoff
    cmp ax, 0x3B00              ; F1
    je .handoff
    cmp al, 0x04                ; Ctrl-D
    je .handoff
    mov ah, 0
    int 0x16                    ; drop any other key
.nokey:
    mov ax, [0x6C]
    sub ax, bx
    cmp ax, 18
    jae .tick
    dec di
    jnz .poll
    dec dh
    jnz .poll                   ; 4 x 65536 polls without a tick: count it anyway
.tick:
    mov al, 8
    call putc
    call putc                   ; back over "Ns"
    dec cl
    jnz .second
    mov dx, CONTINUE
    jmp short .done
.handoff:
    mov dx, KEYLOOP
.done:
    mov bp, sp
    mov [bp+16], dx             ; replace our return address
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    pop bp
    ret

puts:                           ; print CS:SI, zero-terminated
    mov al, [cs:si]
    inc si
    or al, al
    jz .end
    call putc
    jmp short puts
.end:
    ret

putc:                           ; teletype AL (keeps the screen colour)
    push ax
    push bx
    mov ah, 0x0E
    mov bx, 0x0007
    int 0x10
    pop bx
    pop ax
    ret

msg_a: db "  Continuing in ", 0
msg_b: db " - continuing in ", 0
