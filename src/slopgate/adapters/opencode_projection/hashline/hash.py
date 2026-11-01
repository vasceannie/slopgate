"""OMO-compatible xxHash32 line-anchor computation."""

from __future__ import annotations

import re
import unicodedata

from slopgate.util import logger

from ..constants import (
    HASHLINE_BUCKET_COUNT,
    HASHLINE_NIBBLE_BITS,
    HASHLINE_NIBBLE_STR,
    HASHLINE_NIBBLE_STRIDE,
    HASHLINE_UINT32_BITS,
    HASHLINE_UINT32_MASK,
    XXHASH_BLOCK_SIZE,
    XXHASH_FINALIZE_SHIFT_1,
    XXHASH_FINALIZE_SHIFT_2,
    XXHASH_FINALIZE_SHIFT_3,
    XXHASH_LANES,
    XXHASH_PRIME32_1,
    XXHASH_PRIME32_2,
    XXHASH_PRIME32_3,
    XXHASH_PRIME32_4,
    XXHASH_PRIME32_5,
    XXHASH_ROTATE_BYTE,
    XXHASH_ROTATE_LANE_1,
    XXHASH_ROTATE_LANE_2,
    XXHASH_ROTATE_LANE_3,
    XXHASH_ROTATE_LANE_4,
    XXHASH_ROTATE_WORD,
    XXHASH_ROUND_ROTATE,
    XXHASH_WORD_SIZE,
)


def _hash_block(data: bytes, seed: int) -> tuple[int, int]:
    logger.debug("Hashline block hash requested", byte_length=len(data), seed=seed)
    values = [
        (seed + XXHASH_PRIME32_1 + XXHASH_PRIME32_2) & HASHLINE_UINT32_MASK,
        (seed + XXHASH_PRIME32_2) & HASHLINE_UINT32_MASK,
        seed & HASHLINE_UINT32_MASK,
        (seed - XXHASH_PRIME32_1) & HASHLINE_UINT32_MASK,
    ]
    offset = 0
    while offset <= len(data) - XXHASH_BLOCK_SIZE:
        for index in range(XXHASH_LANES):
            word = int.from_bytes(data[offset : offset + XXHASH_WORD_SIZE], "little")
            added = (values[index] + word * XXHASH_PRIME32_2) & HASHLINE_UINT32_MASK
            rotated = (
                (added << XXHASH_ROUND_ROTATE)
                | (added >> (HASHLINE_UINT32_BITS - XXHASH_ROUND_ROTATE))
            ) & HASHLINE_UINT32_MASK
            values[index] = rotated * XXHASH_PRIME32_1 & HASHLINE_UINT32_MASK
            offset += XXHASH_WORD_SIZE
    hashed = (
        (
            (values[0] << XXHASH_ROTATE_LANE_1)
            | (values[0] >> (HASHLINE_UINT32_BITS - XXHASH_ROTATE_LANE_1))
        )
        + (
            (values[1] << XXHASH_ROTATE_LANE_2)
            | (values[1] >> (HASHLINE_UINT32_BITS - XXHASH_ROTATE_LANE_2))
        )
        + (
            (values[2] << XXHASH_ROTATE_LANE_3)
            | (values[2] >> (HASHLINE_UINT32_BITS - XXHASH_ROTATE_LANE_3))
        )
        + (
            (values[3] << XXHASH_ROTATE_LANE_4)
            | (values[3] >> (HASHLINE_UINT32_BITS - XXHASH_ROTATE_LANE_4))
        )
    ) & HASHLINE_UINT32_MASK
    return hashed, offset


def _hash_tail(data: bytes, hashed: int, offset: int) -> int:
    logger.debug("Hashline tail hash requested", byte_length=len(data), offset=offset)
    while offset + XXHASH_WORD_SIZE <= len(data):
        word = int.from_bytes(data[offset : offset + XXHASH_WORD_SIZE], "little")
        hashed = (hashed + word * XXHASH_PRIME32_3) & HASHLINE_UINT32_MASK
        rotated = (
            (hashed << XXHASH_ROTATE_WORD)
            | (hashed >> (HASHLINE_UINT32_BITS - XXHASH_ROTATE_WORD))
        ) & HASHLINE_UINT32_MASK
        hashed = rotated * XXHASH_PRIME32_4 & HASHLINE_UINT32_MASK
        offset += XXHASH_WORD_SIZE
    while offset < len(data):
        hashed = (hashed + data[offset] * XXHASH_PRIME32_5) & HASHLINE_UINT32_MASK
        rotated = (
            (hashed << XXHASH_ROTATE_BYTE)
            | (hashed >> (HASHLINE_UINT32_BITS - XXHASH_ROTATE_BYTE))
        ) & HASHLINE_UINT32_MASK
        hashed = rotated * XXHASH_PRIME32_1 & HASHLINE_UINT32_MASK
        offset += 1
    return hashed


def _finalize_hash(hashed: int) -> int:
    logger.debug("Hashline hash finalization requested")
    hashed ^= hashed >> XXHASH_FINALIZE_SHIFT_1
    hashed = hashed * XXHASH_PRIME32_2 & HASHLINE_UINT32_MASK
    hashed ^= hashed >> XXHASH_FINALIZE_SHIFT_2
    hashed = hashed * XXHASH_PRIME32_3 & HASHLINE_UINT32_MASK
    return (hashed ^ (hashed >> XXHASH_FINALIZE_SHIFT_3)) & HASHLINE_UINT32_MASK


def _xxhash32(content: str, seed: int) -> int:
    logger.debug("Hashline xxhash requested", content_length=len(content), seed=seed)
    data = content.encode("utf-8")
    if len(data) >= XXHASH_BLOCK_SIZE:
        hashed, offset = _hash_block(data, seed)
    else:
        hashed, offset = (seed + XXHASH_PRIME32_5) & HASHLINE_UINT32_MASK, 0
    hashed = (hashed + len(data)) & HASHLINE_UINT32_MASK
    return _finalize_hash(_hash_tail(data, hashed, offset))


def line_hash(line_number: int, content: str, *, legacy: bool = False) -> str:
    """Return the OMO two-character line hash for one source line."""
    logger.debug("Hashline line hash requested", line=line_number, legacy=legacy)
    normalized = content.replace("\r", "")
    normalized = re.sub(r"\s+", "", normalized) if legacy else normalized.rstrip()
    has_significant = any(
        unicodedata.category(character)[0] in "LN" for character in normalized
    )
    seed = 0 if has_significant else line_number
    value = _xxhash32(normalized, seed) % HASHLINE_BUCKET_COUNT
    high = value >> HASHLINE_NIBBLE_BITS
    low = value & (HASHLINE_NIBBLE_STRIDE - 1)
    return HASHLINE_NIBBLE_STR[high] + HASHLINE_NIBBLE_STR[low]
