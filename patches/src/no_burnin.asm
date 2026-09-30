; Never drop into NCR factory burn-in mode.
;
; F000:474C  cmp ah,0 / jne 4769 / mov [40:72],5678h / jmp POST
; AH is the keyboard-controller input port saved in 40:12. F000:3EA4 forces
; it to 0 when the keyboard interface test returns code 3 and the clock/data
; lines are not idle-high (how NCR detected its factory loopback plug). A bad
; keyboard, adapter or blown keyboard fuse does the same; the machine then
; reboots into burn-in, where F1 never works. Make the branch unconditional.

;@ F000:474F max=4
    jmp 0x4769
    nop
