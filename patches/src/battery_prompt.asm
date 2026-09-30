; Don't wait forever at the "Battery Power Lost / Configuration not Set /
; Time & Date not Set / Memory Size Error" prompt.
;
; Stock POST prints "Press <F1> for SETUP or <ENTER> to go on" and blocks in
; INT 16h until a key arrives. Now it beeps, waits up to ~3 s (or until a key
; is pressed) and carries on. F1 pressed during POST or during the wait still
; enters Setup: the type-ahead check at F000:47C5 sees it. Prompts for other
; errors (keyboard, disk failure) are unchanged.

BEEPS       equ 0x4F60          ; original "beep three times" routine
PROMPT_WAIT equ 0x9F00          ; new routine (free space)

;@ F000:4781 max=3
;; call the timed wait instead of the plain beep routine
    call PROMPT_WAIT

;@ F000:4786 max=4
;; after the wait, always continue to the normal boot path at 47AF
    jmp 0x47AF
    nop

;@ F000:9F00 max=0x30 free
;; timed wait: beep, then up to 55 ticks (~3 s) or until a key is waiting
    call BEEPS
    push ax                     ; AL = POST error flags, needed by the caller
    push ds
    push bx
    sti
    mov ax, 0x40
    mov ds, ax
    mov bx, [0x6C]              ; BIOS tick count (18.2 Hz)
.wait:
    mov ah, 1
    int 0x16                    ; key waiting? (not consumed)
    jnz .done
    mov ax, [0x6C]
    sub ax, bx
    cmp ax, 55
    jb .wait
.done:
    pop bx
    pop ds
    pop ax
    ret
