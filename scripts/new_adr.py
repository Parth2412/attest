"""Append a sequential proposed ADR to the repository decision log."""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ADR_LOG: Final[Path] = Path(__file__).resolve().parent.parent / "docs/05-ADR-LOG.md"


def _title() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    title: str = parser.parse_args().title.strip()
    if not title or "\n" in title or "\r" in title:
        parser.error("TITLE must be a non-empty single line")
    return title


def main() -> int:
    """Append the next ADR without rewriting existing decision text."""
    title = _title()
    try:
        existing = ADR_LOG.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"ADR creation error: {error}")
        return 1
    numbers = [int(number) for number in re.findall(r"^## ADR-(\d{3})\b", existing, re.MULTILINE)]
    if not numbers:
        print("ADR creation error: no existing ADR definitions found")
        return 1
    identifier = max(numbers) + 1
    date = datetime.now(UTC).date().isoformat()
    entry = f"""

---

## ADR-{identifier:03d} — {title}

**Status:** Proposed · **Date:** {date} · **Affects:** <documents/features>

**Context.** <Describe the forcing constraint.>

**Decision.** <State the proposed rule.>

**Rationale.** <Explain why this rule best satisfies the constraint.>

**Rejected alternatives.** <Record the alternatives and why they lost.>

**Consequences.** <Record costs and limitations.>
"""
    try:
        with ADR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    except OSError as error:
        print(f"ADR creation error: {error}")
        return 1
    print(f"Appended ADR-{identifier:03d} to {ADR_LOG.relative_to(ADR_LOG.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
