#!/usr/bin/env python3
"""Bake Italy 9:16 pack5 portraits from the final 16:9 masters.

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
    "176", "177", "179", "181", "182", "184", "185", "186", "188", "190",
    "192", "194", "195", "197", "198", "199", "200", "202", "206", "209",
    "212", "214", "215", "216", "217", "219", "220", "222", "227", "228",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("212", False): 487,  # Superga: center clips the left tower
    ("219", False): 787,  # Ostia theatre: center drops the brick scaenae frons
    ("220", False): 747,  # San Miniato: center clips the dome
    ("222", False): 147,  # Pozzo di San Patrizio: the well mouth sits left of center
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
