"""Run a marker-specific pytest gate with lifecycle-aware empty-suite handling."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Final

import pytest

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
BRD_INDEX: Final[Path] = REPOSITORY_ROOT / "docs/06-BRD-INDEX-AND-TRACEABILITY.md"
FEATURE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\| `(?P<feature>F-\d{2})` \| (?P<status>Planned|In progress|Done) \|$", re.MULTILINE
)
MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]*")
FEATURE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"F-\d{2}")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("marker")
    parser.add_argument("owners", nargs="+")
    return parser.parse_args()


def main() -> int:
    """Run pytest and permit an empty selection only before every owner is complete."""
    arguments = _arguments()
    marker: str = arguments.marker
    owners: list[str] = arguments.owners
    if MARKER_PATTERN.fullmatch(marker) is None:
        print(f"test-group configuration error: invalid pytest marker {marker!r}")
        return int(pytest.ExitCode.USAGE_ERROR)
    if any(FEATURE_ID_PATTERN.fullmatch(owner) is None for owner in owners):
        print("test-group configuration error: owners must use F-NN identifiers")
        return int(pytest.ExitCode.USAGE_ERROR)

    try:
        text = BRD_INDEX.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"test-group configuration error: {error}")
        return int(pytest.ExitCode.USAGE_ERROR)
    matches = list(FEATURE_PATTERN.finditer(text))
    statuses = {match.group("feature"): match.group("status") for match in matches}
    if len(matches) != len(statuses) or any(owner not in statuses for owner in owners):
        print("test-group configuration error: BRD-INDEX §7.1 is missing an owner")
        return int(pytest.ExitCode.USAGE_ERROR)

    result = int(pytest.main(["-m", marker]))
    if result != int(pytest.ExitCode.NO_TESTS_COLLECTED):
        return result
    completed = [owner for owner in owners if statuses[owner] == "Done"]
    if completed:
        print(f"{marker}: empty suite is invalid because {', '.join(completed)} is Done")
        return result
    print(f"{marker}: not applicable until one of {', '.join(owners)} is Done")
    return int(pytest.ExitCode.OK)


if __name__ == "__main__":
    raise SystemExit(main())
