"""Acceptance tests for bounded, deterministic policy loading."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, cast

import pytest

from attest_policy import PolicyContext, PolicyError, evaluate, load_policy
from attest_policy.loader import MAX_POLICY_BYTES, _parse_yaml_document


@pytest.mark.ac("AC-F09-090")
def test_yaml_accepts_exact_byte_and_collection_depth_boundaries(
    valid_policy_raw: bytes,
) -> None:
    padding = MAX_POLICY_BYTES - len(valid_policy_raw)
    exact = valid_policy_raw + b"#" + (b"x" * (padding - 2)) + b"\n"

    assert len(exact) == MAX_POLICY_BYTES
    assert load_policy(exact).document is not None
    with pytest.raises(PolicyError) as oversized:
        load_policy(exact + b" ")
    assert oversized.value.code == "ERR-POLICY-601"

    depth_32 = (b"[" * 32) + b"value" + (b"]" * 32)
    depth_33 = b"[" + depth_32 + b"]"
    assert _parse_yaml_document(depth_32) is not None
    with pytest.raises(PolicyError) as too_deep:
        _parse_yaml_document(depth_33)
    assert too_deep.value.code == "ERR-POLICY-601"


@pytest.mark.ac("AC-F09-090")
def test_yaml_constructs_only_the_frozen_scalar_profile() -> None:
    value = _parse_yaml_document(b"[true, false, null, 0, -1, 'true', 01]")
    assert value == [True, False, None, 0, -1, "true", "01"]


@pytest.mark.ac("AC-F09-090")
@pytest.mark.parametrize(
    "raw",
    [
        b"version: 1\nversion: 1\npolicies: []\n",
        b"a: &anchor [1]\n",
        b"a: &anchor [1]\nb: *anchor\n",
        b"a: {x: 1}\nb: {<<: {x: 2}}\n",
        b"a: !!str value\n",
        b"%YAML 1.2\n---\na: value\n",
        b"---\na: 1\n---\nb: 2\n",
        b"a: 1.0\n",
        b"a: .inf\n",
        b"a: 2026-09-14\n",
        b"a: True\n",
        b"a: yes\n",
        b"a: NULL\n",
        b"a: !!python/object/new:tuple []\n",
        b"\xff",
    ],
)
def test_yaml_rejects_ambiguous_or_unsafe_construction(raw: bytes) -> None:
    with pytest.raises(PolicyError) as captured:
        load_policy(raw)
    assert captured.value.code == "ERR-POLICY-601"
    decoded = raw.decode("utf-8", errors="ignore")
    if decoded:
        assert decoded not in str(captured.value)


@pytest.mark.ac("AC-F09-100")
def test_source_preserves_display_path_and_exact_raw_digest(valid_policy_raw: bytes) -> None:
    loaded = load_policy(valid_policy_raw, "config/attest-policy.yml")
    assert loaded.source.path == "config/attest-policy.yml"
    assert loaded.source.sha256 == sha256(valid_policy_raw).hexdigest()

    empty = load_policy(b"", "config/empty.yml")
    assert empty.source.path == "config/empty.yml"
    assert empty.source.sha256 == sha256(b"").hexdigest()


@pytest.mark.ac("AC-F09-120")
def test_absent_and_configured_empty_policy_are_explicitly_reporting_only(
    verified_view: Any,
) -> None:
    context = PolicyContext(target_branch="main", changed_paths=())
    absent = load_policy(None)
    assert absent.document is None
    assert absent.source.path is None
    assert absent.source.sha256 is None
    assert absent.reporting_only_notice == "No policy configured; reporting only."
    absent_decision = evaluate(verified_view, absent, context)
    assert (absent_decision.outcome, absent_decision.exit_code, absent_decision.notice) == (
        "allow",
        0,
        "No policy configured; reporting only.",
    )

    configured = load_policy(b"  # intentionally empty\n", "policy.yml")
    assert configured.document is None
    assert configured.source.path == "policy.yml"
    assert configured.source.sha256 is not None
    assert configured.reporting_only_notice == "Policy contains no rules; reporting only."
    configured_decision = evaluate(verified_view, configured, context)
    assert (
        configured_decision.outcome,
        configured_decision.exit_code,
        configured_decision.notice,
    ) == ("allow", 0, "Policy contains no rules; reporting only.")

    with pytest.raises(PolicyError) as unreadable:
        load_policy(None, "policy.yml")
    assert unreadable.value.code == "ERR-POLICY-603"


@pytest.mark.ac("AC-F09-130")
@pytest.mark.parametrize(
    "raw",
    [
        b"policies: []\n",
        b"version: '1'\npolicies: []\n",
        b"version: true\npolicies: []\n",
    ],
)
def test_malformed_policy_version_is_input_error(raw: bytes) -> None:
    with pytest.raises(PolicyError) as captured:
        load_policy(raw)
    assert captured.value.code == "ERR-POLICY-601"


@pytest.mark.ac("AC-F09-130")
def test_unsupported_integer_policy_version_has_distinct_error() -> None:
    with pytest.raises(PolicyError) as captured:
        load_policy(b"version: 99\npolicies: []\n")
    assert captured.value.code == "ERR-POLICY-602"


def test_non_bytes_input_and_empty_display_path_fail_safely(valid_policy_raw: bytes) -> None:
    with pytest.raises(PolicyError) as non_bytes:
        load_policy(cast(Any, "version: 1"), None)
    assert non_bytes.value.code == "ERR-POLICY-601"
    with pytest.raises(PolicyError) as empty_path:
        load_policy(valid_policy_raw, "")
    assert empty_path.value.code == "ERR-POLICY-601"
