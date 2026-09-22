"""Deterministic policy glob validation and matching governed by BRD-F09 §4.3."""

from __future__ import annotations

from typing import Final, cast

from attest_core import decode_git_path

_STAR: Final[int] = -1
_GLOBSTAR: Final[None] = None
_INVALID_CHARACTERS: Final[tuple[str, ...]] = ("?", "[", "]", "\\")
_INVALID_PATTERN: Final[str] = "invalid policy glob pattern"

type _SegmentPattern = tuple[int, ...] | None


def _segments(pattern: object) -> tuple[str, ...]:
    if (
        not isinstance(pattern, str)
        or not pattern
        or any(character in pattern for character in _INVALID_CHARACTERS)
    ):
        raise ValueError(_INVALID_PATTERN)
    segments = tuple(pattern.split("/"))
    if any("**" in segment and segment != "**" for segment in segments):
        raise ValueError(_INVALID_PATTERN)
    return segments


def _branch_segment(segment: str) -> tuple[int, ...]:
    return tuple(_STAR if character == "*" else ord(character) for character in segment)


def _path_segment(segment: str) -> tuple[int, ...]:
    tokens: list[int] = []
    fragments = segment.split("*")
    for index, fragment in enumerate(fragments):
        try:
            tokens.extend(decode_git_path(fragment))
        except (TypeError, ValueError):
            raise ValueError(_INVALID_PATTERN) from None
        if index + 1 < len(fragments):
            tokens.append(_STAR)
    return tuple(tokens)


def _compile(pattern: object, *, path: bool) -> tuple[_SegmentPattern, ...]:
    compiled: list[_SegmentPattern] = []
    for segment in _segments(pattern):
        if segment == "**":
            compiled.append(_GLOBSTAR)
        else:
            compiled.append(_path_segment(segment) if path else _branch_segment(segment))
    return tuple(compiled)


def _segment_matches(pattern: tuple[int, ...], value: tuple[int, ...]) -> bool:
    pattern_index = 0
    value_index = 0
    last_star = -1
    retry_index = 0
    while value_index < len(value):
        if pattern_index < len(pattern) and pattern[pattern_index] == value[value_index]:
            pattern_index += 1
            value_index += 1
        elif pattern_index < len(pattern) and pattern[pattern_index] == _STAR:
            last_star = pattern_index
            pattern_index += 1
            retry_index = value_index
        elif last_star >= 0:
            pattern_index = last_star + 1
            retry_index += 1
            value_index = retry_index
        else:
            return False
    return all(token == _STAR for token in pattern[pattern_index:])


def _matches(
    pattern: tuple[_SegmentPattern, ...],
    value: tuple[tuple[int, ...], ...],
) -> bool:
    reachable = [True, *([False] * len(value))]
    for pattern_index, segment in enumerate(pattern):
        following = [False] * (len(value) + 1)
        if segment is _GLOBSTAR:
            minimum = 1 if pattern_index + 1 == len(pattern) else 0
            prior_reachable = False
            for value_index in range(len(value) + 1):
                prior_index = value_index - minimum
                if prior_index >= 0:
                    prior_reachable = prior_reachable or reachable[prior_index]
                following[value_index] = prior_reachable
        else:
            for value_index, value_segment in enumerate(value, start=1):
                following[value_index] = reachable[value_index - 1] and _segment_matches(
                    segment, value_segment
                )
        reachable = following
    return reachable[-1]


def validate_branch_pattern(pattern: object) -> str:
    """Validate one branch pattern without matching platform globs (REQ-F09-080)."""
    _compile(pattern, path=False)
    return cast(str, pattern)


def validate_path_pattern(pattern: object) -> str:
    """Validate one canonical raw-path pattern (REQ-F09-080)."""
    _compile(pattern, path=True)
    return cast(str, pattern)


def branch_pattern_matches(pattern: object, branch: object) -> bool:
    """Match one target branch with exact case and separator semantics (REQ-F09-080)."""
    if not isinstance(branch, str) or not branch:
        return False
    value = tuple(tuple(ord(character) for character in segment) for segment in branch.split("/"))
    return _matches(_compile(pattern, path=False), value)


def path_pattern_matches(pattern: object, path: object) -> bool:
    """Match one canonical path as decoded raw bytes (REQ-F09-080)."""
    if not isinstance(path, str) or not path:
        return False
    try:
        raw_segments = decode_git_path(path).split(b"/")
    except (TypeError, ValueError):
        return False
    value = tuple(tuple(segment) for segment in raw_segments)
    return _matches(_compile(pattern, path=True), value)
