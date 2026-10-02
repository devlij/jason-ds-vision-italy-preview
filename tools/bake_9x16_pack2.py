#!/usr/bin/env python3
"""Bake Italy 9:16 pack2 portraits from the final 16:9 masters.

Finished canvas is true 9:16: 1080×1920 = photo 1080×1730 + 190px label bar.
See tools/portrait_9x16.py. Do not scale the photo to 1080×1920 and then add
the bar — that yields 1080×2110, which is not 9:16.

Offsets are the left edge of the 674px-wide source window and keep the same
window center as the previous 608px shifts (left' = left - 33), clamped to
the legal range. Nothing here writes approval_status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portrait_9x16 import bake_pack

PACK = (
    "036", "037", "038", "039", "041", "042", "044", "045", "046", "047",
    "048", "049", "051", "052", "053", "054", "058", "061", "064", "067",
    "068", "069", "070", "072", "076", "078", "079", "080", "082", "083",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("039", False): 1177,  # Palazzo Ducale and its twin towers sit on the right
    ("042", False): 1127,  # Buonconsiglio round tower is the right-hand mass
    ("045", False): 1177,  # Torre del Mangia rises at the right of the Campo
    ("047", False): 1227,  # Amalfi Duomo and campanile fill the right
    ("048", False): 1147,  # Castel dell'Ovo sits on the islet, right of the promenade
    ("051", False): 287,  # Lanterna stands on the left point; center is the port
    ("058", False): 847,  # Duomo and the tower sit right of the terrace center
    ("061", False): 207,  # Castelvecchio keep is on the left; center is the bridge span
    ("064", False): 1246,  # Ostuni crowns the right; clamped from 1280 on the old 608px window
    ("067", False): 1207,  # Cefalù's twin towers sit right of the lane
    ("068", False): 987,  # Orvieto facade runs wide; center clips the right pinnacles
    ("069", False): 167,  # Castel Sant'Angelo fills the left; center cuts the drum
    ("070", False): 187,  # Palazzo Vecchio's tower is on the left of the square
    ("076", False): 1246,  # Paestum's colonnade is on the right; clamped from 1280 on the old window
    ("080", False): 1207,  # Castello Ruffo stands on the right-hand rock
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
