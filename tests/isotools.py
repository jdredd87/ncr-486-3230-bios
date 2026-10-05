"""Build small El Torito ISO images in memory for the CD-ROM boot tests."""
import struct


def pattern(n, tag):
    """n 512-byte sectors, each starting with its number and a tag."""
    return b"".join((struct.pack("<I", i) + tag).ljust(512, bytes([i & 0xFF])) for i in range(n))


def boot_sector():
    s = bytearray(512)
    s[0:2] = b"\xEB\xFE"                             # jmp $
    s[510:512] = b"\x55\xAA"
    return bytes(s)


def make_iso(image, media, count=1, load_seg=0, bootable=True, eltorito=True):
    """ISO 9660 with an El Torito boot catalog at sector 19 and the image at 20."""
    sec = [bytes(2048)] * 16
    pvd = bytearray(2048)
    pvd[0:7] = b"\x01CD001\x01"
    sec.append(bytes(pvd))
    brvd = bytearray(2048)
    brvd[0:7] = b"\x00CD001\x01"
    if eltorito:
        brvd[7:30] = b"EL TORITO SPECIFICATION"
    struct.pack_into("<I", brvd, 0x47, 19)
    sec.append(bytes(brvd))
    sec.append(b"\xFFCD001\x01".ljust(2048, b"\0"))
    cat = bytearray(2048)
    cat[0], cat[1] = 1, 0
    cat[4:28] = b"NCR3230 TEST".ljust(24, b"\0")
    cat[0x1E], cat[0x1F] = 0x55, 0xAA
    s = sum(struct.unpack_from("<16H", cat, 0)) & 0xFFFF
    struct.pack_into("<H", cat, 0x1C, (-s) & 0xFFFF)
    cat[0x20] = 0x88 if bootable else 0x00
    cat[0x21] = media
    struct.pack_into("<HBBHI", cat, 0x22, load_seg, 0, 0, count, 20)
    sec.append(bytes(cat))
    iso = b"".join(sec) + image
    return iso.ljust((len(iso) + 2047) // 2048 * 2048 + 2048 * 8, b"\0")
