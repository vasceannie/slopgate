"""Constants owned by the OpenCode projection formats."""

from __future__ import annotations

import re
from typing import Final

HASHLINE_NIBBLE_STR: Final[str] = "ZPMQVRWSNKTXJBYH"
HASHLINE_BUCKET_COUNT: Final[int] = 256
HASHLINE_NIBBLE_BITS: Final[int] = 4
HASHLINE_NIBBLE_STRIDE: Final[int] = 16
HASHLINE_UINT32_BITS: Final[int] = 32
HASHLINE_UINT32_MASK: Final[int] = 0xFFFFFFFF
XXHASH_PRIME32_1: Final[int] = 2654435761
XXHASH_PRIME32_2: Final[int] = 2246822519
XXHASH_PRIME32_3: Final[int] = 3266489917
XXHASH_PRIME32_4: Final[int] = 668265263
XXHASH_PRIME32_5: Final[int] = 374761393
XXHASH_BLOCK_SIZE: Final[int] = 16
XXHASH_WORD_SIZE: Final[int] = 4
XXHASH_LANES: Final[int] = 4
XXHASH_ROUND_ROTATE: Final[int] = 13
XXHASH_ROTATE_LANE_1: Final[int] = 1
XXHASH_ROTATE_LANE_2: Final[int] = 7
XXHASH_ROTATE_LANE_3: Final[int] = 12
XXHASH_ROTATE_LANE_4: Final[int] = 18
XXHASH_ROTATE_WORD: Final[int] = 17
XXHASH_ROTATE_BYTE: Final[int] = 11
XXHASH_FINALIZE_SHIFT_1: Final[int] = 15
XXHASH_FINALIZE_SHIFT_2: Final[int] = 13
XXHASH_FINALIZE_SHIFT_3: Final[int] = 16
HASHLINE_REF_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^([0-9]+)#([{HASHLINE_NIBBLE_STR}]{{2}})$"
)
HASHLINE_REF_EXTRACT_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"([0-9]+#[{HASHLINE_NIBBLE_STR}]{{2}})"
)
HASHLINE_PREFIX_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^\s*(?:>>>|>>)?\s*\d+\s*#\s*[{HASHLINE_NIBBLE_STR}]{{2}}\|"
)
DIFF_PLUS_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[+](?![+])")
