#!/usr/bin/env python3
"""Bake Italy 9:16 pack3 portraits from the final 16:9 masters.

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
    "084", "085", "088", "089", "090", "091", "093", "094", "095", "096",
    "098", "100", "102", "104", "106", "107", "108", "109", "110", "113",
    "115", "116", "117", "118", "119", "120", "121", "123", "126", "127",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("084", False): 447,  # Castello Scaligero: center clips the left lakeside tower
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
