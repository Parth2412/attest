"""Write the model-generated F-01 structural schema outside the pure core package."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from attest_core.schema import render_json_schema

_SCHEMA_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "spec" / "schemas" / "ai-authorship-v0.1.schema.json"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Write or verify the deterministic schema artifact required by REQ-F01-130."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the committed schema differs",
    )
    arguments = parser.parse_args(argv)
    rendered = render_json_schema("0.1")
    if arguments.check:
        if not _SCHEMA_PATH.is_file() or _SCHEMA_PATH.read_text(encoding="utf-8") != rendered:
            parser.error(f"generated schema differs from {_SCHEMA_PATH}")
        return 0
    _SCHEMA_PATH.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
