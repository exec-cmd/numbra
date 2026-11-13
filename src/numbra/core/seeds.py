"""Seed constraints imposed by SQLite's INTEGER storage."""

SQLITE_INTEGER_MIN = -(1 << 63)
SQLITE_INTEGER_MAX = (1 << 63) - 1


def validate_seed(seed: int, field: str) -> int:
    if not SQLITE_INTEGER_MIN <= seed <= SQLITE_INTEGER_MAX:
        raise ValueError(f"{field} must be between {SQLITE_INTEGER_MIN} and {SQLITE_INTEGER_MAX}")
    return seed
