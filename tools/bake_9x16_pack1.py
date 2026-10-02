#!/usr/bin/env python3
"""Bake Italy 9:16 pack1 portraits from the final 16:9 masters.

Finished canvas is true 9:16: 1080×1920 = photo 1080×1730 + 190px label bar.
See tools/portrait_9x16.py. Do not scale the photo to 1080×1920 and then add
the bar — that yields 1080×2110, which is not 9:16.

Default crop is centered. Offsets are the left edge of the 674px-wide source
window and keep the same window center as the previous 608px shifts
(left' = left - 33). Art. 50 chunks are copied from the source 16:9.
Nothing here writes approval_status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portrait_9x16 import bake_pack

PACK = (
    "001", "002", "004", "005", "006", "007", "008", "009", "010",
    "014", "015", "016", "018", "019", "020", "021", "022", "023",
    "024", "025", "026", "027", "028", "029", "030", "031", "032",
    "033", "034", "035",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("016", False): 407,  # Manarola town sits left; center is open water
    ("016", True): 178,
    ("018", False): 947,  # Temple of Concordia sits right of center
    ("018", True): 897,
    ("020", True): 948,  # Ortigia daylight houses sit on the right
    ("022", False): 159,  # Alghero curtain wall is on the left; center is sea
    ("024", False): 342,  # Costa Smeralda landmass is left of center
    ("024", True): 302,
    ("025", False): 961,  # La Maddalena harbor town is right of center
    ("028", False): 198,  # Stromboli / Sciara del Fuoco is left; center is sea
    ("034", False): 869,  # Miramare castle body extends right of the center window
    ("035", False): 378,  # Sassi mass is a compact block left of center
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
