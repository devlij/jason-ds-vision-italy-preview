#!/usr/bin/env python3
"""Bake Italy 9:16 pack8 portraits from the final 16:9 masters.

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
    "319", "321", "323", "324", "325", "326", "327", "328", "329", "330",
    "331", "332", "333", "334", "335", "336", "337", "338", "339", "340",
    "341", "342", "343", "344", "345", "346", "347", "348", "349", "350",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("323", False): 1047,  # Cetara: center is beach; the cliff houses sit right
    ("325", False): 1127,  # Salerno: center clips Castello di Arechi
    ("329", False): 787,  # Porto Ercole: center clips the right of Forte Stella
    ("344", False): 947,  # Vitorchiano: center clips the right cliff houses
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
