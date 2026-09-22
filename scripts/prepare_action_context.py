"""Stage and fingerprint the exact F-11 container build context."""

# ruff: noqa: TRY003  # Context-specific fail-closed diagnostics are intentional.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Final

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
RELEASE_MANIFEST: Final[PurePosixPath] = PurePosixPath("release/packages.toml")
FIXED_FILES: Final[tuple[PurePosixPath, ...]] = (
    PurePosixPath("pyproject.toml"),
    PurePosixPath("uv.lock"),
    PurePosixPath("action/Dockerfile"),
    PurePosixPath("action/entrypoint.py"),
)
PACKAGE_FILES: Final[tuple[str, ...]] = ("LICENSE", "README.md", "pyproject.toml")
PACKAGE_NAME: Final[re.Pattern[str]] = re.compile(r"attest-[a-z]+\Z")


class ContextError(ValueError):
    """The candidate image context violates its closed release contract."""


def _tracked_paths(repository: Path) -> frozenset[PurePosixPath]:
    git = shutil.which("git")
    if git is None:
        raise ContextError("Git executable is unavailable")
    try:
        result = subprocess.run(  # noqa: S603  # Fixed Git argv; no shell interpretation.
            [git, "-C", str(repository), "ls-files", "-z"],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ContextError("cannot enumerate the reviewed Git context") from error
    if result.returncode != 0:
        raise ContextError("repository root is not a readable Git worktree")
    try:
        names = result.stdout.decode("utf-8").split("\0")
    except UnicodeError as error:
        raise ContextError("tracked context paths must be UTF-8") from error
    return frozenset(PurePosixPath(name) for name in names if name)


def _release_packages(repository: Path) -> tuple[str, ...]:
    path = repository / RELEASE_MANIFEST
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        release = document["release"]
        packages = release["distributions"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise ContextError("release/packages.toml cannot be parsed") from error
    if (
        not isinstance(packages, list)
        or not packages
        or not all(
            isinstance(package, str) and PACKAGE_NAME.fullmatch(package) for package in packages
        )
        or len(packages) != len(set(packages))
    ):
        raise ContextError("release.distributions must be unique attest package names")
    return tuple(packages)


def _regular_source(
    repository: Path, relative: PurePosixPath, tracked: frozenset[PurePosixPath]
) -> Path:
    if relative not in tracked:
        raise ContextError(f"context source must be tracked by Git: {relative}")
    path = repository.joinpath(*relative.parts)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ContextError(f"required context file is unavailable: {relative}") from error
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise ContextError(f"context source must be a regular file: {relative}")
    return path


def _context_files(repository: Path) -> tuple[tuple[PurePosixPath, Path], ...]:
    tracked = _tracked_paths(repository)
    if RELEASE_MANIFEST not in tracked:
        raise ContextError("release/packages.toml must be tracked by Git")
    selected: list[tuple[PurePosixPath, Path]] = [
        (relative, _regular_source(repository, relative, tracked)) for relative in FIXED_FILES
    ]
    for package in _release_packages(repository):
        package_root = PurePosixPath("packages") / package
        for name in PACKAGE_FILES:
            relative = package_root / name
            selected.append((relative, _regular_source(repository, relative, tracked)))

        source_root = repository.joinpath(*package_root.parts, "src")
        try:
            source_metadata = source_root.lstat()
        except OSError as error:
            raise ContextError(f"package source tree is unavailable: {package_root}/src") from error
        if not stat.S_ISDIR(source_metadata.st_mode) or source_root.is_symlink():
            raise ContextError(f"package source tree must be a directory: {package_root}/src")

        source_prefix = f"{package_root}/src/"
        source_paths = sorted(
            relative for relative in tracked if relative.as_posix().startswith(source_prefix)
        )
        source_files = [
            (relative, _regular_source(repository, relative, tracked)) for relative in source_paths
        ]
        if not source_files:
            raise ContextError(f"package source tree is empty: {package_root}/src")
        selected.extend(source_files)

    relative_paths = [relative for relative, _ in selected]
    if len(relative_paths) != len(set(relative_paths)):
        raise ContextError("context contains a duplicate path")
    return tuple(sorted(selected, key=lambda item: item[0].as_posix()))


def _manifest(files: tuple[tuple[PurePosixPath, Path], ...]) -> tuple[dict[str, object], str]:
    entries: list[dict[str, object]] = []
    for relative, source in files:
        content = source.read_bytes()
        mode = stat.S_IMODE(source.stat().st_mode) & 0o777
        entries.append(
            {
                "path": relative.as_posix(),
                "mode": f"{mode:04o}",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "digestAlgorithm": "sha256",
        "files": entries,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    digest = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    return {**payload, "contextDigest": digest}, digest


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _stage(
    repository: Path,
    destination: Path,
    files: tuple[tuple[PurePosixPath, Path], ...],
) -> None:
    repository = repository.resolve()
    destination = destination.resolve()
    if destination == repository or destination in repository.parents:
        raise ContextError("destination must not replace or contain the repository")

    expected_paths = {relative for relative, _ in files}
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_dir():
            raise ContextError("existing destination must be a directory")
        existing_paths: set[PurePosixPath] = set()
        for path in destination.rglob("*"):
            relative = PurePosixPath(path.relative_to(destination).as_posix())
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ContextError(f"existing destination contains an unsafe path: {relative}")
            if path.is_file():
                existing_paths.add(relative)
        if existing_paths != expected_paths:
            raise ContextError("existing destination is not a prior closed Action context")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        for relative, source in files:
            target = temporary.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
            target.chmod(stat.S_IMODE(source.stat().st_mode) & 0o777)
        if destination.exists():
            shutil.rmtree(destination)
        temporary.replace(destination)
    except (OSError, ContextError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--digest-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Stage the closed context and emit its deterministic evidence."""
    arguments = _parser().parse_args(argv)
    repository = arguments.repository_root.resolve()
    try:
        files = _context_files(repository)
        _stage(repository, arguments.destination, files)
        staged_files = tuple(
            (relative, arguments.destination.resolve().joinpath(*relative.parts))
            for relative, _ in files
        )
        manifest, digest = _manifest(staged_files)
        if arguments.manifest_output is not None:
            _write_text(
                arguments.manifest_output,
                f"{json.dumps(manifest, indent=2, sort_keys=True)}\n",
            )
        if arguments.digest_output is not None:
            _write_text(arguments.digest_output, f"{digest}\n")
    except (ContextError, OSError, UnicodeError) as error:
        sys.stderr.write(f"action context error: {error}\n")
        return 1
    sys.stdout.write(f"action context: staged {len(files)} files ({digest})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
