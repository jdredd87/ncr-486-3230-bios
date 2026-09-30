; Setup: a two-digit year 00-79 means 20xx.
;
; Setup's date entry turns 80-99 into 19xx but leaves 00-79 as year 00xx,
; which its own range check (1980-2099) then rejects as "Entry is an invalid
; date". Now 00-79 become 2000-2079; four-digit years are unchanged.
; FA40:1091 (12 bytes), AX = BCD year as typed, AH = century (0 if 2 digits).

;@ FA40:1091 max=12
    or ah, ah
    jnz short 0x109D                 ; four digits typed: keep the century
    mov ah, 0x20
    cmp al, 0x80
    jb short 0x109D
    mov ah, 0x19
