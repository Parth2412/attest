"""Reject prohibited product claims outside the two bounded allowlist regions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
GLOSSARY_PATH: Final[Path] = REPOSITORY_ROOT / "docs/01-GLOSSARY-AND-CONVENTIONS.md"
START_MARKER: Final[str] = "# banned-language-allowlist:start"
END_MARKER: Final[str] = "# banned-language-allowlist:end"

# banned-language-allowlist:start
BANNED_PHRASES: Final[tuple[str, ...]] = (
    "detects AI-generated code",
    "proves an AI wrote this",
    "makes you compliant",
    "compliance guaranteed",
    "tamper-proof",
    "verified authorship",
    "AI percentage of your codebase",
)
# banned-language-allowlist:end

SCAN_PATTERNS: Final[tuple[str, ...]] = (
    "packages/**/*.py",
    "docs/**/*.md",
    "spec/**/*.md",
    "README.md",
    "action/**/*",
    "tests/**/*",
)


class AllowlistConfigurationError(ValueError):
    """Raised when an allowlist marker region is malformed."""

    def __init__(self, label: str) -> None:
        super().__init__(f"{label}: expected exactly one ordered allowlist marker pair")


def _bounded_region(text: str, label: str) -> tuple[int, int]:
    """Return the sole allowlist region and fail closed on malformed markers."""

    def marker_matches(marker: str) -> list[re.Match[str]]:
        line = rf"(?:{re.escape(marker)}|<!-- {re.escape(marker)} -->)"
        return list(re.finditer(rf"^{line}$", text, re.MULTILINE))

    starts = [match.start() for match in marker_matches(START_MARKER)]
    ends = [match.end() for match in marker_matches(END_MARKER)]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise AllowlistConfigurationError(label)
    return starts[0], ends[0]


def _canonical_phrases(glossary: str) -> tuple[str, ...]:
    """Extract quoted literals from the canonical table's Banned column."""
    start, end = _bounded_region(glossary, GLOSSARY_PATH.relative_to(REPOSITORY_ROOT).as_posix())
    phrases: list[str] = []
    for line in glossary[start:end].splitlines():
        if not line.startswith("|"):
            continue
        first_column = line.strip().strip("|").split("|", maxsplit=1)[0]
        phrases.extend(re.findall(r'"([^"]+)"', first_column))
    return tuple(phrases)


def _masked_glossary(text: str) -> str:
    """Mask the canonical table while preserving line offsets."""
    start, end = _bounded_region(text, GLOSSARY_PATH.relative_to(REPOSITORY_ROOT).as_posix())
    masked = "".join("\n" if character == "\n" else " " for character in text[start:end])
    return text[:start] + masked + text[end:]


def _scan_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in SCAN_PATTERNS:
        files.update(path for path in REPOSITORY_ROOT.glob(pattern) if path.is_file())
    return sorted(files)


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    words = phrase.split()
    return re.compile(r"\s+".join(re.escape(word) for word in words), re.IGNORECASE)


def main() -> int:
    """Run configuration-integrity and prohibited-language checks."""
    try:
        glossary = GLOSSARY_PATH.read_text(encoding="utf-8")
        source = Path(__file__).read_text(encoding="utf-8")
        _bounded_region(source, Path(__file__).name)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"banned-language configuration error: {error}")
        return 1

    canonical = _canonical_phrases(glossary)
    if canonical != BANNED_PHRASES:
        print("banned-language configuration error: script constants differ from GLOSS-001 §2.2")
        return 1

    findings: list[tuple[str, int, str]] = []
    for path in _scan_files():
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"banned-language scan error: {relative}: {error}")
            return 1
        searchable = _masked_glossary(text) if path == GLOSSARY_PATH else text
        for phrase in BANNED_PHRASES:
            for match in _phrase_pattern(phrase).finditer(searchable):
                line = searchable.count("\n", 0, match.start()) + 1
                findings.append((relative, line, phrase))

    for relative, line, phrase in findings:
        print(f'{relative}:{line}: prohibited phrase: "{phrase}"')
    if findings:
        return 1
    print(f"banned-language: passed ({len(_scan_files())} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
