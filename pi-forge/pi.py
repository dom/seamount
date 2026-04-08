"""
pi.py — compute π to N decimal places using mpmath.
Returns a string like "3.14159265..." with exactly `digits` decimal places.
"""

from mpmath import mp


def compute_pi(digits: int) -> str:
    """
    Return π as a string with exactly `digits` decimal places.
    Uses truncation (not rounding) to avoid last-digit artifacts.
    """
    # Compute significantly more digits than requested so nstr never rounds
    # the digits we care about. +15 is conservative.
    mp.dps = digits + 15
    # Request digits+5 significant figures, giving us a safe overshoot to truncate
    pi_str = mp.nstr(mp.pi, digits + 5, strip_zeros=False)
    # Truncate to exactly `digits` decimal places
    dot_pos = pi_str.index(".")
    return pi_str[: dot_pos + 1 + digits]
