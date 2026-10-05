"""The Enhanced Edition version, read from patches/src/version.inc."""
import os
import re

INC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "patches", "src", "version.inc")


def read():
    text = open(INC).read()
    version = re.search(r'%define\s+ED_VERSION\s+"([^"]+)"', text).group(1)
    date = re.search(r'%define\s+ED_DATE\s+"([^"]+)"', text).group(1)
    return version, date


ED_VERSION, ED_DATE = read()
