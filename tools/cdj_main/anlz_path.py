"""Where a track's analysis files live on a stick: the player computes it from the file path."""
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import struct
from pathlib import Path


def anlz_dir(card_path: str) -> str:
    """The analysis folder MAIN 4.33 opens for CARD_PATH.

    MAIN does not read the track row's analyze_path: it hashes the file path
    (0x04258214, over UTF-16 code units, mod 200003) and builds
    `P%03X/%08X` from that number (0x042596ee; the P folder is bits
    0,2,6,7,9,13,16 of it).  It is the folder rekordbox writes: all 12
    tracks of rekordbox-pdb's bigger-export.pdb agree.  With any other folder
    MAIN never opens the DAT, answers the GUI's overview request with an
    empty record (console `♪WAVE[0,0]`) and has no beat grid: the track
    loads with a flat overview and an empty BPM box."""
    n = 0
    units = card_path.encode("utf-16-le")
    for unit in struct.unpack("<%dH" % (len(units) // 2), units):
        n = ((n * 0x5BC9 + unit) * 0x93B5 + unit) & 0xFFFFFFFF
    n %= 200003
    folder = 0
    for out_bit, in_bit in enumerate((0, 2, 6, 7, 9, 13, 16)):
        folder |= (n >> in_bit & 1) << out_bit
    return "/PIONEER/USBANLZ/P%03X/%08X" % (folder, n)


def free_stem(folder: Path) -> str:
    """The first ANLZ%04X name not yet taken in FOLDER.

    Two paths can hash to one folder (even odds from about 500 tracks on).  MAIN's
    own analysis writer counts the number up (0x042592a8), so the second track
    takes ANLZ0001; that the read side walks them too is not established."""
    number = 0
    while (folder / ("ANLZ%04X.DAT" % number)).exists():
        number += 1
    return "ANLZ%04X" % number
