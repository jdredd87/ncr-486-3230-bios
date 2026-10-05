; Version of the Enhanced Edition: the one place to change it.
;
; Bump it for every build that is meant to be burned, and add a CHANGELOG.md
; entry. It shows on the boot screen, the end-of-POST summary, Setup's title
; line and Tools -> System information, and is stored in the Tools header
; (E800:0008). The NCR BIOS's own version (2.03.00) and date (10/08/93 at
; F000:FFF5) are never changed: DOS-era software reads them.

%define ED_VERSION "1.1"
%define ED_DATE    "2026-10-05"
ED_MAJOR    equ 1
ED_MINOR    equ 1
