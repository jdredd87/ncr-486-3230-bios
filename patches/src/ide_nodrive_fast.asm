; Fail fast when a drive type is set but nothing is on the IDE cable.
;
; sub_95E4 waits for BSY to clear for up to BX*65536 status reads. With no
; device the bus floats to FFh, BSY never clears, and POST sits for ~16 s in
; the controller diagnostic (INT 13h AH=14h, BX=50h) before "Disk controller
; failure". A real device never returns FFh for long, so give up after 16384
; consecutive FFh reads (~50 ms). Behaviour with a device present is unchanged.

WAIT_NEW equ 0x9F30

;@ F000:95E4 max=3
;; sub_95E4 now jumps to the new wait routine
    jmp WAIT_NEW

;@ F000:9F30 max=0x40 free
;; same contract as sub_95E4: BX = outer count, CF=1 on timeout, AL=0 on success;
;; clobbers AL, BX, CX, DX (as before), keeps everything else
    push si
    xor si, si
    xor cx, cx
    mov dx, 0x1F7
.poll:
    in al, dx
    out 0xEB, al
    out 0xEB, al
    cmp al, 0xFF
    jne .real
    inc si
    cmp si, 0x4000
    jae .fail                   ; floating bus: no device
    jmp short .next
.real:
    xor si, si
    and al, 0x80
    jz .ok                      ; BSY clear
.next:
    loop .poll
    dec bx
    jnz .poll
.fail:
    pop si
    stc
    ret
.ok:
    pop si
    clc
    ret
