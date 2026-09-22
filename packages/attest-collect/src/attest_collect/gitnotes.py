"""Pinned Git AI authorship/3.0.0 note collection governed by BRD-F03."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Final, cast

from attest_collect._git_signals import GitSignalReader
from attest_collect._strict_json import decode_json
from attest_collect.authorship import (
    AuthorshipWarning,
    ClaimCollectorResult,
    CollectContext,
    authorship_warning,
    generate_uuid7,
)
from attest_core import (
    AgentRef,
    AuthorshipClaim,
    ClaimScope,
    ClaimSource,
    ClaimSourceKind,
    ModelRef,
    decode_git_path,
    encode_git_path,
)

_SCHEMA_VERSION: Final[str] = "authorship/3.0.0"
_SESSION_KEY: Final[re.Pattern[str]] = re.compile(r"s_[0-9A-Fa-f]{14}")
_TRACE_KEY: Final[re.Pattern[str]] = re.compile(
    r"(?P<session>s_[0-9A-Fa-f]{14})::t_[0-9A-Fa-f]{14}"
)
_HUMAN_KEY: Final[re.Pattern[str]] = re.compile(r"h_[0-9A-Fa-f]{14}")
_LEGACY_KEY: Final[re.Pattern[str]] = re.compile(r"(?:[0-9A-Fa-f]{7}|[0-9A-Fa-f]{16})")
_ENTRY: Final[re.Pattern[str]] = re.compile(r"  (?P<key>\S+) (?P<ranges>\S+)")
_RANGE: Final[re.Pattern[str]] = re.compile(r"(?P<start>[1-9][0-9]*)(?:-(?P<end>[1-9][0-9]*))?")
_PROMPT_COUNTS: Final[tuple[str, ...]] = (
    "total_additions",
    "total_deletions",
    "accepted_lines",
    "overriden_lines",
)
_SESSION_FORBIDDEN: Final[frozenset[str]] = frozenset({"messages", "messages_url", *_PROMPT_COUNTS})


@dataclass(frozen=True, slots=True)
class _Agent:
    tool: str
    session_id: str
    model: str


@dataclass(frozen=True, slots=True)
class _ParsedNote:
    paths: dict[str, tuple[str, ...]]
    agents: dict[str, _Agent]


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError
    return cast(dict[str, object], value)


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_string(value: object) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError


def _attributes(value: object) -> None:
    if value is None:
        return
    attributes = _object(value)
    if any(not isinstance(item, str) for item in attributes.values()):
        raise ValueError


def _agent(value: object) -> _Agent:
    fields = _object(value)
    return _Agent(
        tool=_string(fields.get("tool")),
        session_id=_string(fields.get("id")),
        model=_string(fields.get("model")),
    )


def _session_records(value: object) -> dict[str, _Agent]:
    records = _object(value)
    agents: dict[str, _Agent] = {}
    for key, raw_record in records.items():
        if _SESSION_KEY.fullmatch(key) is None:
            raise ValueError
        record = _object(raw_record)
        if set(record) & _SESSION_FORBIDDEN:
            raise ValueError
        agent = _agent(record.get("agent_id"))
        _optional_string(record.get("human_author"))
        _attributes(record.get("custom_attributes"))
        agents[key] = agent
    return agents


def _prompt_records(value: object) -> dict[str, _Agent]:
    records = _object(value)
    agents: dict[str, _Agent] = {}
    for key, raw_record in records.items():
        if _LEGACY_KEY.fullmatch(key) is None:
            raise ValueError
        record = _object(raw_record)
        if "messages" in record:
            raise ValueError
        agent = _agent(record.get("agent_id"))
        _optional_string(record.get("human_author"))
        _optional_string(record.get("messages_url"))
        _attributes(record.get("custom_attributes"))
        for field in _PROMPT_COUNTS:
            count = record.get(field)
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count < 1 << 32:
                raise ValueError
        agents[key] = agent
    return agents


def _human_records(value: object) -> frozenset[str]:
    records = _object(value)
    keys: set[str] = set()
    for key, raw_record in records.items():
        if _HUMAN_KEY.fullmatch(key) is None:
            raise ValueError
        record = _object(raw_record)
        _string(record.get("author"))
        keys.add(key)
    return frozenset(keys)


def _metadata(value: object) -> tuple[dict[str, _Agent], dict[str, _Agent], frozenset[str]]:
    metadata = _object(value)
    if _string(metadata.get("schema_version")) != _SCHEMA_VERSION:
        raise ValueError
    _string(metadata.get("base_commit_sha"))
    _optional_string(metadata.get("git_ai_version"))
    prompts = _prompt_records(metadata.get("prompts"))
    sessions = _session_records(metadata.get("sessions", {}))
    humans = _human_records(metadata.get("humans", {}))
    return prompts, sessions, humans


def _validate_ranges(value: str) -> None:
    starts: list[int] = []
    for item in value.split(","):
        match = _RANGE.fullmatch(item)
        if match is None:
            raise ValueError
        start = int(match.group("start"))
        end_value = match.group("end")
        if end_value is not None and int(end_value) < start:
            raise ValueError
        starts.append(start)
    if starts != sorted(starts):
        raise ValueError


def _parse_attestations(lines: list[str]) -> tuple[dict[str, set[str]], frozenset[str]]:
    paths: dict[str, set[str]] = {}
    human_references: set[str] = set()
    current_path: str | None = None
    current_has_entry = False
    for line in lines:
        if not line:
            continue
        entry = _ENTRY.fullmatch(line)
        if entry is not None:
            if current_path is None:
                raise ValueError
            key = entry.group("key")
            _validate_ranges(entry.group("ranges"))
            session_match = _TRACE_KEY.fullmatch(key)
            if session_match is not None:
                paths.setdefault(session_match.group("session"), set()).add(current_path)
            elif _HUMAN_KEY.fullmatch(key) is not None:
                human_references.add(key)
            elif _LEGACY_KEY.fullmatch(key) is not None:
                paths.setdefault(key, set()).add(current_path)
            else:
                raise ValueError
            current_has_entry = True
            continue
        if line[0].isspace() or (current_path is not None and not current_has_entry):
            raise ValueError
        if line.startswith('"') and line.endswith('"'):
            path = line[1:-1]
        else:
            if any(character.isspace() for character in line):
                raise ValueError
            path = line
        if not path:
            raise ValueError
        current_path = encode_git_path(path.encode("utf-8"))
        current_has_entry = False
    if current_path is not None and not current_has_entry:
        raise ValueError
    return paths, frozenset(human_references)


def _parse_note(raw: bytes) -> _ParsedNote:
    text = raw.decode("utf-8")
    lines = text.splitlines()
    dividers = [index for index, line in enumerate(lines) if line == "---"]
    if len(dividers) != 1:
        raise ValueError
    divider = dividers[0]
    paths, human_references = _parse_attestations(lines[:divider])
    metadata_text = "\n".join(lines[divider + 1 :])
    prompts, sessions, humans = _metadata(decode_json(metadata_text))
    if not human_references <= humans:
        raise ValueError

    agents: dict[str, _Agent] = {}
    for key in paths:
        records = sessions if _SESSION_KEY.fullmatch(key) is not None else prompts
        if key not in records:
            raise ValueError
        agents[key] = records[key]
    ordered_paths = {
        key: tuple(sorted(values, key=decode_git_path)) for key, values in paths.items()
    }
    return _ParsedNote(paths=ordered_paths, agents=agents)


def _model(value: str) -> ModelRef | None:
    if value.count("/") != 1:
        return None
    provider, name = value.split("/")
    if not provider or not name:
        return None
    return ModelRef(provider=provider, name=name)


def _claims(
    raw: bytes,
    parsed: _ParsedNote,
    notes_ref: str,
    commit: str,
) -> tuple[AuthorshipClaim, ...]:
    digest = hashlib.sha256(raw).hexdigest()
    claims: list[AuthorshipClaim] = []
    for key in sorted(parsed.paths):
        agent = parsed.agents[key]
        claims.append(
            AuthorshipClaim(
                claim_id=generate_uuid7(),
                agent=AgentRef(name=agent.tool),
                model=_model(agent.model),
                session_id=agent.session_id,
                scope=ClaimScope(paths=parsed.paths[key]),
                source=ClaimSource(
                    kind=ClaimSourceKind.GIT_NOTE,
                    reference=f"{notes_ref}:{commit}:{key}",
                    digest=digest,
                ),
            )
        )
    return tuple(claims)


class GitNoteCollector:
    """Collect pinned Git AI 3.0.0 note blobs exactly (REQ-F03-020/110)."""

    kind = ClaimSourceKind.GIT_NOTE

    def collect(self, ctx: CollectContext) -> ClaimCollectorResult:
        try:
            reader = GitSignalReader(ctx.repo_path)
            if not reader.notes_ref_exists(ctx.notes_ref):
                return ClaimCollectorResult(claims=(), warnings=())
            commits = reader.commit_oids(ctx.base_commit, ctx.head_commit)
        except Exception:
            warning = authorship_warning("ERR-COLLECT-116", ctx.notes_ref)
            return ClaimCollectorResult(claims=(), warnings=(warning,))

        claims: list[AuthorshipClaim] = []
        warnings: list[AuthorshipWarning] = []
        for commit in commits:
            reference = f"{ctx.notes_ref}:{commit}"
            try:
                raw = reader.note_blob(ctx.notes_ref, commit)
                if raw is None:
                    continue
                claims.extend(_claims(raw, _parse_note(raw), ctx.notes_ref, commit))
            except (OSError, UnicodeError, ValueError):
                warnings.append(authorship_warning("ERR-COLLECT-116", reference))
            except Exception:
                warnings.append(authorship_warning("ERR-COLLECT-116", reference))
        return ClaimCollectorResult(claims=tuple(claims), warnings=tuple(warnings))
