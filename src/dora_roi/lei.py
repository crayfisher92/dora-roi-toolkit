"""Legal Entity Identifier (ISO 17442) helpers.

An LEI is 20 alphanumeric characters: 18 characters of identifier followed by two numeric
check digits computed with ISO/IEC 7064 MOD 97-10 (the same scheme as IBAN). The check is:
convert letters to numbers (A=10 … Z=35), interpret the resulting digit string as an integer,
and verify ``n mod 97 == 1``.
"""

from __future__ import annotations

import re
from functools import lru_cache

LEI_PATTERN = re.compile(r"^[A-Z0-9]{18}[0-9]{2}$")


def _to_digits(value: str) -> int:
    return int("".join(str(int(ch, 36)) for ch in value))


def is_valid_lei_format(value: str) -> bool:
    """True if ``value`` has the LEI shape (20 chars, uppercase alnum, numeric check digits)."""
    return bool(LEI_PATTERN.match(value))


@lru_cache(maxsize=65_536)  # registers repeat the same few thousand LEIs many times
def is_valid_lei(value: str) -> bool:
    """True if ``value`` is a syntactically valid LEI with a correct MOD 97-10 checksum."""
    return is_valid_lei_format(value) and _to_digits(value) % 97 == 1


def lei_check_digits(base: str) -> str:
    """Compute the two check digits for an 18-character LEI base."""
    base = base.upper()
    if not re.fullmatch(r"[A-Z0-9]{18}", base):
        raise ValueError("LEI base must be exactly 18 uppercase alphanumeric characters")
    return f"{98 - _to_digits(base + '00') % 97:02d}"


def make_lei(base: str) -> str:
    """Return a full, valid LEI for an 18-character base."""
    base = base.upper()
    return base + lei_check_digits(base)


@lru_cache(maxsize=65_536)
def explain_lei_error(value: str) -> str:
    """Human-readable reason why ``value`` is not a valid LEI (empty string if it is valid)."""
    if len(value) != 20:
        return f"LEI must be 20 characters long, got {len(value)}"
    if not re.fullmatch(r"[A-Z0-9]{20}", value):
        return "LEI may only contain uppercase letters A-Z and digits 0-9"
    if not value[18:].isdigit():
        return "LEI check digits (positions 19-20) must be numeric"
    if not is_valid_lei(value):
        expected = lei_check_digits(value[:18])
        return f"LEI checksum (ISO 17442 / MOD 97-10) failed; expected check digits {expected}"
    return ""
