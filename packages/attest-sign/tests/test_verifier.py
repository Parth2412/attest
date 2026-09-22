"""Acceptance tests for the ordered F-08 verification pipeline."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from cryptography.x509 import SubjectAlternativeName, UniformResourceIdentifier
from sigstore.errors import VerificationError

from attest_core import Statement, validate_statement_structure
from attest_core.constants import DSSE_PAYLOAD_TYPE, PREDICATE_TYPE_V0_1
from attest_sign import (
    IdentityConstraint,
    RepositoryConstraint,
    ServiceTrustRoot,
    VerificationEnvironment,
    verify,
)
from attest_sign import verifier as module
from attest_sign.verify_errors import VerifyError, VerifyErrorCode

IDENTITY = "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/main"
ISSUER = "https://token.actions.githubusercontent.com"
CHECK_NAMES = [
    "bundle-structure",
    "sigstore-dsse",
    "statement-payload",
    "structural-schema",
    "semantic-model",
    "changeset-recomputation",
]


def _bundle_wire(*, inclusion_proof: bool = True) -> bytes:
    entry: dict[str, object] = {}
    if inclusion_proof:
        entry["inclusionProof"] = {}
    return json.dumps(
        {
            "dsseEnvelope": {},
            "verificationMaterial": {
                "certificate": {},
                "tlogEntries": [entry],
            },
        }
    ).encode()


class _FakeSans:
    def __init__(self, identities: tuple[str, ...]) -> None:
        self._identities = identities

    def get_values_for_type(self, san_type: type[object]) -> list[str]:
        if san_type is UniformResourceIdentifier:
            return list(self._identities)
        return []


class _FakeExtensions:
    def __init__(self, identities: tuple[str, ...]) -> None:
        self._identities = identities

    def get_extension_for_class(self, extension_type: type[object]) -> SimpleNamespace:
        assert extension_type is SubjectAlternativeName
        return SimpleNamespace(value=_FakeSans(self._identities))


class _FakeBundle:
    def __init__(self, identities: tuple[str, ...] = (IDENTITY,)) -> None:
        self.signing_certificate = SimpleNamespace(extensions=_FakeExtensions(identities))


class _FakeIdentity:
    observed: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, *, identity: str, issuer: str) -> None:
        self.observed.append((identity, issuer))


class _FakeVerifier:
    def __init__(
        self,
        payload: bytes,
        *,
        failure: Exception | None = None,
    ) -> None:
        self._payload = payload
        self._failure = failure
        self.calls = 0
        self.expected_bundle: object | None = None
        self.observed_source: object | None = None

    def verify_dsse(self, bundle: object, policy: object) -> tuple[str, bytes]:
        assert bundle is self.expected_bundle
        assert isinstance(policy, _FakeIdentity)
        self.calls += 1
        if self._failure is not None:
            raise self._failure
        return DSSE_PAYLOAD_TYPE, self._payload


def _install_boundary(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    *,
    crypto_failure: Exception | None = None,
    identities: tuple[str, ...] = (IDENTITY,),
) -> _FakeVerifier:
    upstream = _FakeVerifier(payload, failure=crypto_failure)
    fake_bundle = _FakeBundle(identities)
    upstream.expected_bundle = fake_bundle

    def parse(raw: bytes) -> _FakeBundle:
        assert raw == _bundle_wire()
        return fake_bundle

    def load(source: object) -> _FakeVerifier:
        assert isinstance(source, ServiceTrustRoot)
        upstream.observed_source = source
        return upstream

    monkeypatch.setattr("attest_sign.verifier._SigstoreBundle.from_json", parse)
    monkeypatch.setattr(module, "load_verifier", load)
    monkeypatch.setattr(module, "Identity", _FakeIdentity)
    _FakeIdentity.observed = []
    return upstream


def _verify(payload: bytes, *, pattern: str = IDENTITY) -> module.VerificationResult:
    return verify(
        _bundle_wire(),
        IdentityConstraint(pattern, ISSUER),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
    )


@pytest.mark.ac("AC-F08-010")
@pytest.mark.ac("AC-F08-140")
def test_atomic_crypto_failure_aborts_before_payload_and_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-010/140: step 2 is atomic, terminal, and secret-safe."""
    secret = "private-certificate-and-key-material"
    upstream = _install_boundary(
        monkeypatch,
        json.dumps(valid_statement_data).encode(),
        crypto_failure=VerificationError(secret),
    )

    result = _verify(json.dumps(valid_statement_data).encode())

    assert result.status == "failed"
    assert [(check.name, check.result, check.code) for check in result.checks] == [
        ("bundle-structure", "passed", None),
        ("sigstore-dsse", "failed", "ERR-VERIFY-013"),
    ]
    assert result.statement is None
    assert result.failure_code == "ERR-VERIFY-013"
    assert secret not in repr(result)
    assert upstream.calls == 1


@pytest.mark.ac("AC-F08-020")
@pytest.mark.ac("AC-F08-120")
def test_success_lists_all_ordered_checks_and_distinguishes_trust(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-020/120: output is ordered and preserves environment trust."""
    _install_boundary(monkeypatch, json.dumps(valid_statement_data).encode())

    trusted = _verify(json.dumps(valid_statement_data).encode())
    local_wire = copy.deepcopy(valid_statement_data)
    local_wire["predicate"]["collection"]["environment"]["trusted"] = False
    _install_boundary(monkeypatch, json.dumps(local_wire).encode())
    untrusted = _verify(json.dumps(local_wire).encode())

    assert trusted.status == "verified"
    assert [check.name for check in trusted.checks] == CHECK_NAMES
    assert [check.result for check in trusted.checks] == [
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
        "skipped",
    ]
    assert all(check.code is None for check in trusted.checks)
    assert isinstance(trusted.statement, Statement)
    assert trusted.failure_code is None
    assert untrusted.status == "verified-untrusted-environment"


@pytest.mark.ac("AC-F08-050")
@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "*",
        "https://github.com/*/Repo/.github/workflows/a.yml@refs/heads/main",
        "https://github.com/Org/Repo/.github/workflows/a.yml@refs/heads/**",
        "https://github.com/Org/Repo/.github/workflows/a.yml@refs/heads/ma?n",
        "https://github.com/Org/Repo/.github/workflows/a.yml@refs/heads/[main]",
    ],
)
def test_unbounded_identity_patterns_are_rejected_at_construction(pattern: str) -> None:
    """REQ-F08-050: only exact identities and bounded workflow globs exist."""
    with pytest.raises(VerifyError) as captured:
        IdentityConstraint(pattern, ISSUER)

    assert captured.value.code == "ERR-VERIFY-011"


@pytest.mark.ac("AC-F08-050")
def test_exact_and_anchored_single_segment_glob_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-050: a glob resolves one URI SAN and becomes an exact policy."""
    payload = json.dumps(valid_statement_data).encode()
    _install_boundary(monkeypatch, payload)

    exact = _verify(payload)
    globbed = _verify(
        payload,
        pattern="https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/*",
    )

    assert exact.status == "verified"
    assert globbed.status == "verified"
    assert _FakeIdentity.observed == [(IDENTITY, ISSUER), (IDENTITY, ISSUER)]
    for result in (exact, globbed):
        assert result.verified_identity == IDENTITY
        assert result.verified_issuer == ISSUER
        assert result.transparency_log_verified is True


@pytest.mark.ac("AC-F08-050")
def test_glob_is_case_sensitive_anchored_and_requires_one_san(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-050: zero or multiple whole-SAN matches fail closed."""
    payload = json.dumps(valid_statement_data).encode()
    pattern = "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/*"
    _install_boundary(monkeypatch, payload, identities=(IDENTITY.upper(),))
    no_match = _verify(payload, pattern=pattern)
    _install_boundary(monkeypatch, payload, identities=(IDENTITY, IDENTITY))
    duplicate = _verify(payload, pattern=pattern)

    assert no_match.failure_code == "ERR-VERIFY-013"
    assert duplicate.failure_code == "ERR-VERIFY-013"
    assert _FakeIdentity.observed == []


@pytest.mark.ac("AC-F08-060")
@pytest.mark.parametrize("issuer", ["", None, 3, False])
def test_empty_or_non_string_issuer_never_reaches_identity_policy(
    monkeypatch: pytest.MonkeyPatch,
    issuer: object,
) -> None:
    """REQ-F08-060: reject the Sigstore empty-issuer bypass before policy use."""
    monkeypatch.setattr(module, "Identity", _FakeIdentity)
    _FakeIdentity.observed = []

    with pytest.raises(VerifyError) as captured:
        IdentityConstraint(IDENTITY, cast(str, issuer))

    assert captured.value.code == "ERR-VERIFY-011"
    assert _FakeIdentity.observed == []


@pytest.mark.ac("AC-F08-060")
def test_nonempty_issuer_is_passed_unchanged_to_sigstore(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-060: issuer matching is exact and delegated atomically."""
    payload = json.dumps(valid_statement_data).encode()
    _install_boundary(monkeypatch, payload)

    result = _verify(payload)

    assert result.status == "verified"
    assert _FakeIdentity.observed == [(IDENTITY, ISSUER)]


@pytest.mark.ac("AC-F08-070")
def test_missing_inclusion_proof_is_a_step_two_failure(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-070: omitted proof retains its normative crypto classification."""
    parse_calls = 0

    def parse(raw: bytes) -> object:
        nonlocal parse_calls
        del raw
        parse_calls += 1
        return object()

    monkeypatch.setattr("attest_sign.verifier._SigstoreBundle.from_json", parse)
    result = verify(
        _bundle_wire(inclusion_proof=False),
        IdentityConstraint(IDENTITY, ISSUER),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
    )

    assert [(check.name, check.result, check.code) for check in result.checks] == [
        ("bundle-structure", "passed", None),
        ("sigstore-dsse", "failed", "ERR-VERIFY-013"),
    ]
    assert parse_calls == 0


@pytest.mark.ac("AC-F08-090")
def test_unknown_predicate_type_aborts_before_schema(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-090: unknown versions never receive best-effort parsing."""
    wire = copy.deepcopy(valid_statement_data)
    wire["predicateType"] = "https://parth2412.github.io/attest/ai-authorship/v9.9"
    payload = json.dumps(wire).encode()
    _install_boundary(monkeypatch, payload)

    result = _verify(payload)

    assert result.failure_code == "ERR-VERIFY-007"
    assert [check.name for check in result.checks] == CHECK_NAMES[:3]


@pytest.mark.ac("AC-F08-100")
def test_exact_version_schema_precedes_semantic_model(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-100/150: URI dispatch is exact and structural validation is first."""
    sentinel_uri = "https://parth2412.github.io/attest/ai-authorship/v0.2"
    monkeypatch.setitem(module._PREDICATE_REGISTRY, sentinel_uri, ("0.2", Statement))
    selected: list[str] = []

    def capture(value: object, predicate_version: str) -> None:
        selected.append(predicate_version)
        validate_statement_structure(value, predicate_version)

    monkeypatch.setattr("attest_sign.verifier._validate_statement_structure", capture)
    extra = copy.deepcopy(valid_statement_data)
    extra["predicate"]["unexpected"] = True
    extra_payload = json.dumps(extra).encode()
    _install_boundary(monkeypatch, extra_payload)

    structural = _verify(extra_payload)

    mismatch = copy.deepcopy(valid_statement_data)
    mismatch["subject"][0]["digest"]["sha256"] = "f" * 64
    mismatch_payload = json.dumps(mismatch).encode()
    _install_boundary(monkeypatch, mismatch_payload)
    semantic = _verify(mismatch_payload)

    assert structural.failure_code == "ERR-VERIFY-008"
    assert [check.name for check in structural.checks] == CHECK_NAMES[:4]
    assert semantic.failure_code == "ERR-VERIFY-009"
    assert [check.name for check in semantic.checks] == CHECK_NAMES[:5]
    assert selected == ["0.1", "0.1"]
    assert PREDICATE_TYPE_V0_1 in module._PREDICATE_REGISTRY


@pytest.mark.ac("AC-F08-010")
def test_structure_and_trust_initialization_fail_at_their_exact_steps(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-010: parsing and trust material retain distinct codes."""
    malformed = verify(
        b"{",
        IdentityConstraint(IDENTITY, ISSUER),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
    )
    monkeypatch.setattr("attest_sign.verifier._SigstoreBundle.from_json", lambda raw: _FakeBundle())

    class PrivateTrustError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("private trust diagnostic")

    def unavailable(source: object) -> object:
        del source
        raise PrivateTrustError

    monkeypatch.setattr(module, "load_verifier", unavailable)
    trust = _verify(json.dumps(valid_statement_data).encode())

    assert malformed.failure_code == "ERR-VERIFY-001"
    assert len(malformed.checks) == 1
    assert trust.failure_code == "ERR-VERIFY-012"
    assert [check.name for check in trust.checks] == CHECK_NAMES[:2]
    assert "private trust diagnostic" not in repr(trust)


@pytest.mark.ac("AC-F08-010")
@pytest.mark.parametrize(
    "wire",
    [
        [],
        {"verificationMaterial": {}},
        {"dsseEnvelope": {}, "verificationMaterial": {}},
        {
            "dsseEnvelope": {},
            "verificationMaterial": {"certificate": {}, "tlogEntries": []},
        },
    ],
)
def test_malformed_preflight_shapes_fail_only_bundle_structure(wire: object) -> None:
    """REQ-F08-010: malformed top-level structures never enter Sigstore."""
    result = verify(
        json.dumps(wire).encode(),
        IdentityConstraint(IDENTITY, ISSUER),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
    )

    assert result.failure_code == "ERR-VERIFY-001"
    assert [(check.name, check.result) for check in result.checks] == [
        ("bundle-structure", "failed")
    ]


@pytest.mark.ac("AC-F08-010")
@pytest.mark.parametrize(
    "wire",
    [
        {
            "dsseEnvelope": [],
            "verificationMaterial": {
                "certificate": {},
                "tlogEntries": [{"inclusionProof": {}}],
            },
        },
        {"dsseEnvelope": {}, "verificationMaterial": []},
        {
            "dsseEnvelope": {},
            "verificationMaterial": {"certificate": {}, "tlogEntries": {}},
        },
        {
            "dsseEnvelope": {},
            "verificationMaterial": {
                "certificate": {},
                "tlogEntries": [{"inclusionProof": {}}, {"inclusionProof": {}}],
            },
        },
    ],
)
def test_preflight_rejects_each_malformed_member_before_sigstore(
    monkeypatch: pytest.MonkeyPatch,
    wire: object,
) -> None:
    """REQ-F08-010: a malformed member cannot be delegated as a parse attempt."""
    parse_calls = 0

    def parse(raw: bytes) -> object:
        nonlocal parse_calls
        del raw
        parse_calls += 1
        return object()

    monkeypatch.setattr("attest_sign.verifier._SigstoreBundle.from_json", parse)

    with pytest.raises(module._MalformedBundleError):
        module._parse_bundle(json.dumps(wire).encode())
    assert parse_calls == 0


@pytest.mark.ac("AC-F08-150")
def test_legacy_certificate_chain_shape_reaches_the_public_parser(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F08-150: preflight retains Sigstore's historical chain representation."""
    payload = json.dumps(valid_statement_data).encode()
    upstream = _FakeVerifier(payload)
    fake_bundle = _FakeBundle()
    upstream.expected_bundle = fake_bundle
    raw = json.dumps(
        {
            "dsseEnvelope": {},
            "verificationMaterial": {
                "x509CertificateChain": {},
                "tlogEntries": [{"inclusionProof": {}}],
            },
        }
    ).encode()

    def parse(candidate: bytes) -> _FakeBundle:
        assert candidate == raw
        return fake_bundle

    monkeypatch.setattr("attest_sign.verifier._SigstoreBundle.from_json", parse)
    monkeypatch.setattr(module, "load_verifier", lambda source: upstream)
    monkeypatch.setattr(module, "Identity", _FakeIdentity)

    result = verify(
        raw,
        IdentityConstraint(IDENTITY, ISSUER),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
    )

    assert result.status == "verified"


@pytest.mark.ac("AC-F08-040")
def test_explicit_null_identity_constraint_is_a_usage_error() -> None:
    """REQ-F08-040: a typed-call escape cannot become a verification result."""
    with pytest.raises(VerifyError) as captured:
        verify(
            _bundle_wire(),
            cast(IdentityConstraint, None),
            ServiceTrustRoot(VerificationEnvironment.STAGING, True),
        )

    assert captured.value.code == "ERR-VERIFY-011"


@pytest.mark.ac("AC-F08-090")
@pytest.mark.parametrize(
    ("payload_type", "payload"),
    [("text/plain", b"{}"), (DSSE_PAYLOAD_TYPE, b"[]")],
)
def test_non_statement_verified_payloads_fail_step_three(
    monkeypatch: pytest.MonkeyPatch,
    payload_type: str,
    payload: bytes,
) -> None:
    """REQ-F08-090: media type and Statement object shape are mandatory."""
    upstream = _install_boundary(monkeypatch, payload)
    monkeypatch.setattr(upstream, "verify_dsse", lambda bundle, policy: (payload_type, payload))

    result = _verify(payload)

    assert result.failure_code == "ERR-VERIFY-007"
    assert [check.name for check in result.checks] == CHECK_NAMES[:3]


@pytest.mark.ac("AC-F08-110")
def test_repository_digest_mismatch_is_the_final_check(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    """REQ-F08-110: explicit repository recomputation is terminal step 6."""
    payload = json.dumps(valid_statement_data).encode()
    _install_boundary(monkeypatch, payload)
    monkeypatch.setattr(module, "recompute_changeset_digest", lambda constraint: "f" * 64)

    result = verify(
        _bundle_wire(),
        IdentityConstraint(IDENTITY, ISSUER),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
        RepositoryConstraint(tmp_path, "a" * 40, "b" * 40),
    )

    assert result.failure_code == "ERR-VERIFY-010"
    assert [check.name for check in result.checks] == CHECK_NAMES
    assert result.checks[-1].result == "failed"
    assert result.statement is None


@pytest.mark.ac("AC-F08-110")
@pytest.mark.parametrize("mode", ["error", "match"])
def test_repository_recomputation_error_or_match_has_exact_outcome(
    monkeypatch: pytest.MonkeyPatch,
    valid_statement_data: dict[str, Any],
    tmp_path: Path,
    mode: str,
) -> None:
    """REQ-F08-110: recomputation errors fail; an exact digest passes step 6."""
    payload = json.dumps(valid_statement_data).encode()
    _install_boundary(monkeypatch, payload)

    if mode == "error":
        observed: list[RepositoryConstraint] = []

        def recompute(constraint: RepositoryConstraint) -> str:
            observed.append(constraint)
            raise RuntimeError

        monkeypatch.setattr(module, "recompute_changeset_digest", recompute)
    else:
        observed = []

        def recompute(constraint: RepositoryConstraint) -> str:
            observed.append(constraint)
            return "0" * 64

        monkeypatch.setattr(module, "recompute_changeset_digest", recompute)

    constraint = RepositoryConstraint(tmp_path, "a" * 40, "b" * 40)
    result = verify(
        _bundle_wire(),
        IdentityConstraint(IDENTITY, ISSUER),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
        constraint,
    )

    assert observed == [constraint]
    if mode == "error":
        assert result.failure_code == "ERR-VERIFY-010"
        assert result.checks[-1].result == "failed"
        assert result.checks[-1].name == "changeset-recomputation"
        assert result.statement is None
    else:
        assert result.status == "verified"
        assert result.failure_code is None
        assert result.checks[-1].result == "passed"
        assert result.checks[-1].name == "changeset-recomputation"


@pytest.mark.ac("AC-F08-160")
@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("bundle-structure", "ERR-VERIFY-001"),
        ("sigstore-dsse", "ERR-VERIFY-013"),
        ("statement-payload", "ERR-VERIFY-007"),
        ("structural-schema", "ERR-VERIFY-008"),
        ("semantic-model", "ERR-VERIFY-009"),
        ("changeset-recomputation", "ERR-VERIFY-010"),
    ],
)
def test_every_failure_step_clears_verified_policy_evidence(
    name: module.CheckName,
    code: VerifyErrorCode,
) -> None:
    """REQ-F08-160: partial verification progress is never exposed as trusted evidence."""
    result = module._failure([], name, code)

    assert result.status == "failed"
    assert result.statement is None
    assert result.verified_identity is None
    assert result.verified_issuer is None
    assert result.transparency_log_verified is False
