"""
Formatting utilities for OpenSourceLens.
Provides formatting for metrics, byte counts, and timestamps.
"""

from typing import Optional


def format_metric_number(val: Optional[int]) -> str:
    """
    Formats large integer values to readable representations (e.g. 245K, 1.2M).
    Handles None and invalid types safely.
    """
    if val is None:
        return "0"
    try:
        val = int(val)
    except (ValueError, TypeError):
        return str(val)

    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M".replace(".0M", "M")
    if val >= 1_000:
        return f"{val / 1_000:.1f}K".replace(".0K", "K")
    return str(val)


def format_byte_size(num_bytes: int) -> str:
    """
    Formats byte counts to readable units (B, KB, MB, GB, TB).
    """
    if not num_bytes or num_bytes < 0:
        return "0 B"
    num = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}".replace(".0 ", " ")
        num /= 1024.0
    return f"{num:.1f} TB"
