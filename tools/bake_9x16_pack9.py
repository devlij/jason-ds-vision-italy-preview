#!/usr/bin/env python3
"""Bake Italy 9:16 pack9 portraits from the final 16:9 masters.

Finished canvas is true 9:16: 1080×1920 = photo 1080×1730 + 190px label bar.
See tools/portrait_9x16.py. Do not scale the photo to 1080×1920 and then add
the bar — that yields 1080×2110, which is not 9:16.

Offsets are the left edge of the 674px-wide source window and keep the same
window center as the previous 608px shifts (left' = left - 33). Left-edge
subjects that already used left 0 stay at 0. Nothing here writes approval_status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portrait_9x16 import bake_pack

PACK = (
    "351", "352", "353", "354", "355", "356", "357", "358", "359", "360",
    "361", "362", "363", "364", "365",
)

# Left edge of the 674px-wide source window. Absent → center (623).
SHIFTS = {
    ("351", False): 367,  # Conversano: center misses the castle; both landmarks sit across the ridge
    ("352", False): 267,  # Jesi: center cuts through the palazzo tower
    ("355", False): 0,  # Urbania: the ducal palace is the left mass; center is the river
    ("357", False): 847,  # Pacentro: Caldora towers sit right of center
    ("358", False): 0,  # Vasto: Palazzo d'Avalos is the left mass; center is the beach
    ("359", False): 1007,  # Ortona: the cliff castle is right of center
    ("362", False): 107,  # Popoli: Cantelmo castle peak is left of center
    ("364", False): 767,  # Santo Stefano: the Medici tower sits on the right edge of center
}


if __name__ == "__main__":
    bake_pack(PACK, SHIFTS)
