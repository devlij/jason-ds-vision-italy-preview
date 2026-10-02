#!/usr/bin/env python3
"""Bake Italy 9:16 pack7 portraits from the final 16:9 masters.

Finished canvas is true 9:16: 1080×1920 = photo 1080×1730 + 190px label bar.
See tools/portrait_9x16.py. Do not scale the photo to 1080×1920 and then add
the bar — that yields 1080×2110, which is not 9:16.

Offsets are the left edge of the 674px-wide source window and keep the same
window center as the previous 608px shifts (left' = left - 33). Nothing here
writes approval_status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portrait_9x16 import bake_pack

PACK = (
    "268", "272", "273", "274", "275", "276", "277", "278", "279", "280",
    "281", "282", "283", "288", "290", "291", "292", "294", "295", "296",
    "299", "301", "303", "307", "309", "310", "312", "313", "314", "315",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("274", False): 827,  # Castel Gandolfo: center clips the dome
    ("278", False): 1007,  # Giardino degli Aranci: center misses St Peter's dome
    ("281", False): 727,  # Santa Maria Maggiore: center clips the campanile
    ("291", False): 287,  # Cefalù: center clips a tower; 287 holds both
    ("294", False): 1167,  # Levanto: center is beach; town sits to the right
    ("296", False): 1147,  # Feltre: center misses Castello di Alboino
    ("301", False): 87,  # Panarea: center is open sea; houses sit to the left
    ("307", False): 1147,  # Tellaro: center misses the church and cliff village
    ("309", False): 1207,  # Baia del Silenzio: center is open water
    ("310", False): 87,  # Bagno Vignoni: center misses the thermal pool
    ("312", False): 27,  # Nemi: center misses the crater-rim village
    ("314", False): 1107,  # Sorano: center is canyon; the town sits to the right
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
