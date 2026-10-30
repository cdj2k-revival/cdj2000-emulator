# SPDX-License-Identifier: GPL-2.0-or-later
"""rb_card's analysis folder is the one the player computes from the file path.

The pairs are the file_path / analyze_path of every track of rekordbox-pdb's
tests/data/bigger-export.pdb, a real rekordbox export (MIT).  rekordbox writes
the folder under /.PIONEER in the row; MAIN 4.33 opens it under /PIONEER.
"""

import pytest

from tools.cdj_main.anlz_path import anlz_dir, free_stem

REKORDBOX = [
    ("/Contents/[a]pendics.shuffle/Framed And Defamed/01 A1 - It's In The Eyes.mp3", "P017/0000CA47"),
    ("/Contents/[a]pendics.shuffle/Framed And Defamed/02 A2 - In Charge.mp3", "P00A/0000C986"),
    ("/Contents/[a]pendics.shuffle/Framed And Defamed/03 B1 - About To Be.mp3", "P041/00015D11"),
    ("/Contents/[a]pendics.shuffle/Framed And Defamed/"
     "04 B2 - In Charge (Stavöstranos Peep Mix).mp3", "P06D/000161C3"),
    ("/Contents/[a]pendics.shuffle/Rampent Passenger EP/01 Sit Up on this.mp3", "P025/0000FC61"),
    ("/Contents/[a]pendics.shuffle/Rampent Passenger EP/02 Deluxe Cynic.mp3", "P02F/0002ACC7"),
    ("/Contents/[a]pendics.shuffle/Rampent Passenger EP/03 Pussy Willow Trackmate.mp3", "P027/0000B95D"),
    ("/Contents/[a]pendics.shuffle/Rampent Passenger EP/04 Move it on.mp3", "P006/0002554C"),
    ("/Contents/[A]pendics.Shuffle/Shes Got Moves EP/01 Your Moves.mp3", "P01B/000097AD"),
    ("/Contents/[A]pendics.Shuffle/Shes Got Moves EP/02 Award Winning Actor.mp3", "P01C/0000C6D0"),
    ("/Contents/[A]pendics.Shuffle/Shes Got Moves EP/"
     "03 Your Moves (Losoul's High Tide Remix).mp3", "P047/0001507F"),
    ("/Contents/[A]pendics.Shuffle/Shes Got Moves EP/04 On Yo Back.mp3", "P00B/000205BF"),
]


@pytest.mark.parametrize("path, folder", REKORDBOX)
def test_folder_matches_rekordbox(path, folder):
    assert anlz_dir(path) == "/PIONEER/USBANLZ/" + folder


def test_a_second_track_in_one_folder_takes_the_next_name(tmp_path):
    assert free_stem(tmp_path) == "ANLZ0000"
    (tmp_path / "ANLZ0000.DAT").touch()
    assert free_stem(tmp_path) == "ANLZ0001"
