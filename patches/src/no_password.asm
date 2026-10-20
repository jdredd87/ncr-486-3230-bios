; No NCR passwords: the power-on and Setup password checks are skipped.
;
; NCR's password code keeps four 10-byte slots in CMOS 4Ah-71h (slot number
; in 34h bits 1-0, typed password in 36h-3Eh, prompt flags in 49h). It runs
; from two places:
;   F000:04DA  power-on check, called at the end of every POST (F000:481B)
;   F000:0616  Setup password check, called before F1 Setup (F000:47EE)
; With no password set, the power-on check finds slot 0 empty, counts that as
; invalid and resets the password state (F000:05D1): it zeroes 34h, 36h-3Eh
; and 49h-71h. The Enhanced Edition keeps its boot order (4Ah-4Dh), chipset
; and video settings (4Eh-52h, 60h) and Plug and Play settings (54h-5Fh)
; there, so every boot erased them. A password can only be set from that
; prompt (F000:087A), not from Setup.
;
; Both routines start by re-setting the video mode and hooking INT 9, then
; read CMOS 0Eh (call 0759). Jump from there to each one's own exit, which
; prints its newline, restores INT 9 and returns: the screen behaves as
; before, and no password is ever asked for, checked, set or cleared.

;@ F000:050C max=3
    jmp 0x05F5

;@ F000:0648 max=3
    jmp 0x071B
