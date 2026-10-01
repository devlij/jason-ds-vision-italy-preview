#!/usr/bin/env python3
"""Bake Italy 9:16 pack4 portraits from the final 16:9 masters.

Finished canvas is true 9:16: 1080×1920 = photo 1080×1730 + 190px label bar.
See tools/portrait_9x16.py. Do not scale the photo to 1080×1920 and then add
the bar — that yields 1080×2110, which is not 9:16.

Default crop is centered (left 623 on the 674px window). Each previous center
window was checked against the 16:9 photo; the wider window shares that center,
so nothing is shifted. Pack4 scenes have no daylight 16:9 on main. Nothing
here writes approval_status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portrait_9x16 import bake_pack

PACK = (
    "128", "130", "131", "132", "133", "137", "138", "139", "140", "141",
    "142", "143", "144", "145", "146", "150", "153", "154", "155", "157",
    "158", "159", "162", "163", "164", "167", "170", "171", "174", "175",
)

SHIFTS: dict[tuple[str, bool], int] = {}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
