"""Validate BRD requirement, acceptance-criterion, and test traceability."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
BRD_INDEX: Final[Path] = REPOSITORY_ROOT / "docs/06-BRD-INDEX-AND-TRACEABILITY.md"
VALID_STATUSES: Final[frozenset[str]] = frozenset({"Planned", "In progress", "Done"})
FEATURE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\| `(?P<feature>F-\d{2})` \| (?P<status>Planned|In progress|Done) \|$", re.MULTILINE
)


class FeatureRegistryError(ValueError):
    """Raised when the machine-readable feature registry is malformed."""


def _feature_statuses(text: str) -> dict[str, str]:
    matches = list(FEATURE_PATTERN.finditer(text))
    statuses = {match.group("feature"): match.group("status") for match in matches}
    expected = {f"F-{number:02d}" for number in range(1, 13)}
    if len(matches) != len(statuses) or set(statuses) != expected:
        raise FeatureRegistryError
    if not set(statuses.values()) <= VALID_STATUSES:
        raise FeatureRegistryError
    return statuses


def _test_markers() -> set[str]:
    marker_pattern = re.compile(r"@pytest\.mark\.ac\(\s*['\"](AC-F\d{2}-\d{3})['\"]\s*\)")
    markers: set[str] = set()
    paths = list((REPOSITORY_ROOT / "packages").glob("*/tests/**/*.py"))
    paths.extend((REPOSITORY_ROOT / "action/tests").glob("**/*.py"))
    for path in sorted(paths):
        markers.update(marker_pattern.findall(path.read_text(encoding="utf-8")))
    return markers


def main() -> int:
    """Check identifier pairing and test coverage for completed features."""
    try:
        statuses = _feature_statuses(BRD_INDEX.read_text(encoding="utf-8"))
        brd_paths = sorted((REPOSITORY_ROOT / "docs/brd").glob("BRD-F*.md"))
        markers = _test_markers()
    except (OSError, UnicodeError, ValueError) as error:
        print(f"traceability configuration error: {error}")
        return 1

    requirements: set[str] = set()
    criteria: set[str] = set()
    for path in brd_paths:
        text = path.read_text(encoding="utf-8")
        requirements.update(re.findall(r"REQ-F\d{2}-\d{3}", text))
        criteria.update(re.findall(r"AC-F\d{2}-\d{3}", text))

    requirement_numbers = {identifier.removeprefix("REQ-") for identifier in requirements}
    criterion_numbers = {identifier.removeprefix("AC-") for identifier in criteria}
    errors: list[str] = []
    for number in sorted(requirement_numbers - criterion_numbers):
        errors.append(f"REQ-{number} has no matching AC-{number}")
    for number in sorted(criterion_numbers - requirement_numbers):
        errors.append(f"AC-{number} has no matching REQ-{number}")

    print("Feature | Status | REQs | ACs | Referenced ACs | Missing when Done")
    print("---|---|---:|---:|---:|---:")
    for feature, status in sorted(statuses.items()):
        suffix = feature.removeprefix("F-")
        feature_requirements = {item for item in requirements if item.startswith(f"REQ-F{suffix}-")}
        feature_criteria = {item for item in criteria if item.startswith(f"AC-F{suffix}-")}
        referenced = feature_criteria & markers
        missing = feature_criteria - markers if status == "Done" else set()
        print(
            f"{feature} | {status} | {len(feature_requirements)} | {len(feature_criteria)} | "
            f"{len(referenced)} | {len(missing)}"
        )
        errors.extend(
            f"{criterion} has no test marker for completed {feature}"
            for criterion in sorted(missing)
        )

    for error in errors:
        print(f"traceability error: {error}")
    if errors:
        return 1
    print(
        f"traceability: passed ({len(requirements)} requirements, {len(criteria)} criteria, "
        f"{sum(status == 'Done' for status in statuses.values())} Done features)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
