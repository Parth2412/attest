"""Write the model-generated F-01 and F-09 schemas outside their pure packages."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from attest_core.schema import render_json_schema
from attest_policy import render_policy_json_schema

_SCHEMA_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "spec" / "schemas" / "ai-authorship-v0.1.schema.json"
)
_POLICY_SCHEMA_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "spec" / "schemas" / "policy-v1.schema.json"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Write or verify deterministic artifacts required by REQ-F01-130/REQ-F09-020."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the committed schema differs",
    )
    arguments = parser.parse_args(argv)
    schemas = {
        _SCHEMA_PATH: render_json_schema("0.1"),
        _POLICY_SCHEMA_PATH: render_policy_json_schema(),
    }
    for path, rendered in schemas.items():
        if arguments.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                parser.error(f"generated schema differs from {path}")
        else:
            path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
