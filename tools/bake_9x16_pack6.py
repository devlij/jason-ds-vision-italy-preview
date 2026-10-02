#!/usr/bin/env python3
"""Bake Italy 9:16 pack6 portraits from the final 16:9 masters.

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
    "229", "231", "233", "234", "235", "236", "237", "238", "239", "240",
    "241", "242", "244", "246", "248", "249", "251", "252", "254", "255",
    "256", "257", "258", "259", "260", "261", "262", "263", "266", "267",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("233", False): 947,  # San Giorgio: center clips the campanile
    ("238", False): 867,  # Orcus: center clips the right side of the mouth
    ("239", False): 767,  # Santa Maria Novella: center clips the right volute
    ("240", False): 767,  # Torcello: center clips the cathedral; campanile stays
    ("248", False): 767,  # Frasassi: center clips the right side of the cave arch
    ("257", False): 827,  # Avio: center clips the right-hand keep
    ("258", False): 827,  # Trajan's Column: center leaves the shaft on the edge
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
