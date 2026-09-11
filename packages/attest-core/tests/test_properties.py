"""Required Hypothesis properties for canonicalisation, CSD-1, and aliases."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from attest_core.canonical import JsonScalar, JsonValue, canonicalize
from attest_core.constants import (
    DIGEST_ALGORITHM,
    IN_TOTO_STATEMENT_TYPE,
    PREDICATE_TYPE_V0_1,
    SCHEMA_VERSION,
)
from attest_core.digest import build_changeset_record, compute_changeset_digest
from attest_core.models import (
    Authorship,
    AuthorshipMode,
    ChangeSetEntry,
    ChangeSetInfo,
    ChangeSetStats,
    ChangeType,
    Collection,
    CollectorRef,
    DigestSet,
    EnvironmentKind,
    EnvironmentRef,
    Predicate,
    Review,
    ReviewState,
    Statement,
    Subject,
)

_SURROGATE_CATEGORIES: tuple[Literal["Cs"], ...] = ("Cs",)
JSON_SCALARS: st.SearchStrategy[JsonScalar] = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**53) + 1, max_value=2**53 - 1)
    | st.text(alphabet=st.characters(exclude_categories=_SURROGATE_CATEGORIES), max_size=30)
)
JSON_VALUES = cast(
    st.SearchStrategy[JsonValue],
    st.recursive(
        JSON_SCALARS,
        lambda children: (
            st.lists(children, max_size=5)
            | st.dictionaries(
                st.text(
                    alphabet=st.characters(exclude_categories=_SURROGATE_CATEGORIES), max_size=15
                ),
                children,
                max_size=5,
            )
        ),
        max_leaves=20,
    ),
)
OID = st.from_regex(r"[0-9a-f]{40}", fullmatch=True)
SHA256 = st.from_regex(r"[0-9a-f]{64}", fullmatch=True)
SAFE_PATH = st.from_regex(r"[A-Za-z0-9._~/-]{1,30}", fullmatch=True).filter(
    lambda value: not value.startswith("/")
)


def _entry_strategy() -> st.SearchStrategy[ChangeSetEntry]:
    return st.builds(
        lambda path, change_type, old_mode, new_mode, old_blob, new_blob: ChangeSetEntry(
            path=path,
            change_type=change_type,
            old_mode=old_mode,
            new_mode=new_mode,
            old_blob=old_blob,
            new_blob=new_blob,
        ),
        path=SAFE_PATH,
        change_type=st.just(ChangeType.MODIFIED),
        old_mode=st.sampled_from(("100644", "100755")),
        new_mode=st.sampled_from(("100644", "100755")),
        old_blob=OID,
        new_blob=OID,
    )


@pytest.mark.ac("AC-F01-030")
@given(JSON_VALUES)
def test_canonicalization_is_deterministic(value: JsonValue) -> None:
    """REQ-F01-030: parsing canonical bytes cannot change canonical bytes."""
    rendered = canonicalize(value)
    assert canonicalize(json.loads(rendered)) == rendered


@pytest.mark.ac("AC-F01-050")
@given(st.lists(_entry_strategy(), min_size=1, max_size=8, unique_by=lambda entry: entry.path))
def test_digest_is_stable_under_entry_permutation(entries: list[ChangeSetEntry]) -> None:
    """REQ-F01-050: input ordering has no effect on CSD-1."""
    expected = compute_changeset_digest(build_changeset_record(entries))
    assert compute_changeset_digest(build_changeset_record(list(reversed(entries)))) == expected


@pytest.mark.ac("AC-F01-050")
@given(_entry_strategy())
def test_digest_is_sensitive_to_every_entry_field(entry: ChangeSetEntry) -> None:
    """REQ-F01-050: changing any single entry field changes its digest."""
    baseline = compute_changeset_digest(build_changeset_record([entry]))
    replacements = {
        "path": f"x/{entry.path}",
        "change_type": ChangeType.TYPECHANGE,
        "old_mode": "100755" if entry.old_mode == "100644" else "100644",
        "new_mode": "100755" if entry.new_mode == "100644" else "100644",
        "old_blob": "f" * 40 if entry.old_blob != "f" * 40 else "e" * 40,
        "new_blob": "d" * 40 if entry.new_blob != "d" * 40 else "c" * 40,
    }
    for field_name, replacement in replacements.items():
        mutated = entry.model_copy(update={field_name: replacement})
        assert compute_changeset_digest(build_changeset_record([mutated])) != baseline, field_name


@pytest.mark.ac("AC-F01-020")
@given(OID, OID, SHA256)
def test_statement_alias_round_trip(base_oid: str, head_oid: str, digest: str) -> None:
    """REQ-F01-020: generated model instances survive a wire-keyed round trip."""
    statement = Statement.model_validate(
        {
            "type_": IN_TOTO_STATEMENT_TYPE,
            "subject": (Subject(name="changeset", digest=DigestSet(sha256=digest)),),
            "predicate_type": PREDICATE_TYPE_V0_1,
            "predicate": Predicate(
                schema_version=SCHEMA_VERSION,
                change_set=ChangeSetInfo(
                    repository="https://github.com/example/repo",
                    algorithm=DIGEST_ALGORITHM,
                    base_commit=base_oid,
                    head_commit=head_oid,
                    digest=digest,
                    stats=ChangeSetStats(
                        files_changed=0,
                        files_added=0,
                        files_modified=0,
                        files_deleted=0,
                    ),
                ),
                authorship=Authorship(mode=AuthorshipMode.UNKNOWN, claims_present=False, claims=()),
                review=Review(
                    required="unknown",
                    state=ReviewState.UNKNOWN,
                    human_approvals=0,
                    reviewers=(),
                ),
                collection=Collection(
                    collector=CollectorRef(name="attest", version="0.1.0"),
                    collected_at=datetime(2026, 9, 11, tzinfo=UTC),
                    environment=EnvironmentRef(kind=EnvironmentKind.LOCAL, trusted=False),
                ),
            ),
        }
    )
    assert Statement.model_validate(statement.model_dump()) == statement
