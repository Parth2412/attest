"""Pure exact-or-bounded workload identity pattern handling."""

from __future__ import annotations

import re
from typing import Final

_GITHUB_WORKFLOW_IDENTITY: Final[re.Pattern[str]] = re.compile(
    r"https://github\.com/[^/]+/[^/]+/\.github/workflows/[^/]+@refs/.+"
)
_INVALID_PATTERN_CHARACTERS: Final[tuple[str, ...]] = ("?", "[", "]")
_INVALID_IDENTITY_PATTERN: Final[str] = "invalid workload identity pattern"


def validate_identity_pattern(pattern: object) -> str:
    """Return a valid exact or bounded GitHub workflow identity pattern (REQ-F01-200)."""
    if (
        not isinstance(pattern, str)
        or not pattern
        or any(character in pattern for character in _INVALID_PATTERN_CHARACTERS)
        or "**" in pattern
    ):
        raise ValueError(_INVALID_IDENTITY_PATTERN)
    if "*" not in pattern:
        return pattern
    if _GITHUB_WORKFLOW_IDENTITY.fullmatch(pattern) is None:
        raise ValueError(_INVALID_IDENTITY_PATTERN)
    prefix, separator, reference = pattern.partition("@refs/")
    if separator != "@refs/" or "*" in prefix or "*" not in reference:
        raise ValueError(_INVALID_IDENTITY_PATTERN)
    return pattern


def identity_pattern_matches(pattern: object, identity: object) -> bool:
    """Match one exact identity using the validated bounded grammar (REQ-F01-200)."""
    validated = validate_identity_pattern(pattern)
    if not isinstance(identity, str):
        return False
    if "*" not in validated:
        return identity == validated
    expression = re.escape(validated).replace(r"\*", r"[^/]+")
    return re.fullmatch(expression, identity) is not None
