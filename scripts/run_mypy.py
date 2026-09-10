"""Run strict mypy independently for every workspace package."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from mypy import api

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
PACKAGES_ROOT: Final[Path] = REPOSITORY_ROOT / "packages"


def main() -> int:
    """Check each package without merging equal test-module names."""
    packages = sorted(
        path for path in PACKAGES_ROOT.iterdir() if (path / "pyproject.toml").is_file()
    )
    if not packages:
        print("mypy: no workspace packages discovered")
        return 1

    failed = False
    for package in packages:
        print(f"mypy: checking {package.name}")
        standard_output, standard_error, status = api.run([str(package)])
        if standard_output:
            print(standard_output, end="")
        if standard_error:
            print(standard_error, end="")
        failed = failed or status != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
