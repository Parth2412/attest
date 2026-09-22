"""Run strict mypy independently for every workspace package."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from mypy import api

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
PACKAGES_ROOT: Final[Path] = REPOSITORY_ROOT / "packages"
ACTION_ROOT: Final[Path] = REPOSITORY_ROOT / "action"


def main() -> int:
    """Check each package without merging equal test-module names."""
    targets = sorted(
        path for path in PACKAGES_ROOT.iterdir() if (path / "pyproject.toml").is_file()
    )
    if ACTION_ROOT.is_dir():
        targets.append(ACTION_ROOT)
    if not targets:
        print("mypy: no workspace packages discovered")
        return 1

    failed = False
    for target in targets:
        print(f"mypy: checking {target.name}")
        standard_output, standard_error, status = api.run([str(target)])
        if standard_output:
            print(standard_output, end="")
        if standard_error:
            print(standard_error, end="")
        failed = failed or status != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
