# BRD-F09 — Policy Engine and CI Gate

| Field | Value |
|---|---|
| Document ID | `BRD-F09` |
| Feature | `F-09` |
| Milestone | M2 |
| Package | `attest-policy` |
| Depends on | `F-01`, `F-04`, `F-08` |
| Status | Done · completion reconciled by `ADR-045` |

---

## 1. Purpose

Turn a verified attestation into a deterministic policy decision. Verification proves the record
is genuine; policy decides whether what it records is acceptable. F-09 owns pure loading and
evaluation. F-10 maps the decision to a process exit and F-11 publishes the required GitHub status
check that can block a merge.

## 2. Scope trace

`SCOPE-08`.

## 3. Dependencies and package boundary

`F-01`, `F-04`, `F-08`. All three must be `Done`, including the `ADR-042` reviewer effective-state
and verified-evidence corrections, before F-09 implementation begins.

`attest-policy` may import `attest-core` and its own direct dependencies. It must not import the
peer `attest-sign` package. It declares a structural view of the verified fields it consumes and
uses `attest-core`'s pure identity-pattern validator/matcher so F-08 and F-09 cannot drift.

## 4. Policy document format

`NORMATIVE EXAMPLE` — this is the exact public shape accepted by policy version 1.

```yaml
version: 1
policies:
  - id: POL-MAIN-001
    description: Human review required for AI-authored changes on main
    match:
      branches: ["main", "release/*"]
      paths: ["**"]
    require:
      attestation: true
      environment:
        trusted: true
      signer:
        issuer: "https://token.actions.githubusercontent.com"
        identity: "https://github.com/acme/api/.github/workflows/attest.yml@refs/heads/main"
      transparencyLog: true
      review:
        when:
          authorshipMode: ["ai-authored", "ai-assisted"]
        minHumanApprovals: 1
        approverMustNotBeAuthor: true
      authorship:
        claimsRequired: true
      checks:
        mustPass: ["unit-tests"]
    onViolation: block

  - id: POL-DOCS-001
    match:
      branches: ["main"]
      paths: ["docs/**"]
    require:
      attestation: true
    onViolation: warn
```

### 4.1 Closed vocabulary and structural rules

| Key | Type and rule |
|---|---|
| `version` | Required strict integer; exactly `1` |
| `policies` | Required array; may be empty |
| `policies[].id` | Required non-empty string; unique within the document |
| `policies[].description` | Optional non-empty string |
| `policies[].match.branches` | Required non-empty array of unique branch patterns |
| `policies[].match.paths` | Required non-empty array of unique canonical path patterns |
| `policies[].require` | Required non-empty closed object |
| `require.attestation` | Boolean |
| `require.environment.trusted` | Boolean |
| `require.signer.issuer` | Required non-empty exact string when `signer` is configured |
| `require.signer.identity` | Required non-empty F-08 identity pattern when `signer` is configured |
| `require.transparencyLog` | Boolean |
| `require.review.when.authorshipMode` | Optional non-empty unique list of authorship modes |
| `require.review.minHumanApprovals` | Optional non-negative strict integer |
| `require.review.approverMustNotBeAuthor` | Optional boolean; `true` requires `minHumanApprovals >= 1` |
| `require.authorship.claimsRequired` | Boolean |
| `require.checks.mustPass` | Non-empty array of unique non-empty exact check names |
| `onViolation` | Required `block` or `warn` |

Unknown fields at every level are forbidden. Configuring any nested requirement requires
`require.attestation: true`, because those predicates have no trustworthy input without an
attestation. Boolean requirement values set to `false` are explicit no-ops: they report
`not-applicable` and never mean “require false”. No expressions, scripts, arbitrary field access,
path exclusions, or implicit defaults are supported.

### 4.2 Worked example — differentiated enforcement without excluded evidence

The ChangeSet Digest always covers every changed path. A policy can vary enforcement by path but
cannot exclude a path from the signed record or alter `CSD-1`.

```yaml
version: 1
policies:
  - id: POL-CRITICAL-001
    match:
      branches: ["main"]
      paths: ["contracts/**", "infra/**", "**/auth/**"]
    require:
      attestation: true
      environment: {trusted: true}
      review:
        minHumanApprovals: 2
        approverMustNotBeAuthor: true
      authorship: {claimsRequired: true}
    onViolation: block

  - id: POL-GENERATED-001
    match:
      branches: ["main"]
      paths: ["dist/**", "**/*.lock", "**/*.snap", "**/generated/**"]
    require:
      attestation: true
    onViolation: warn
```

### 4.3 Glob grammar (NORMATIVE)

Matching is case-sensitive and anchored to the complete value. `/` is the only separator.

| Token | Meaning |
|---|---|
| `*` | Zero or more characters within one branch segment, or raw bytes within one path segment; never `/` |
| `**` | Zero or more complete segments; valid only as an entire segment |
| literal | Exact character for branches; exact decoded raw byte sequence for canonical paths |

When a `**` segment is followed by `/`, that following separator belongs to the globstar and is
omitted when zero segments match; a preceding separator remains. Thus `**/*.lock` matches a root
file, while `docs/**` requires at least one segment below `docs`. `?`, bracket expressions,
backslashes, `***`, and `**` embedded inside another segment are invalid. Path literal bytes use
the canonical percent encoding from `SPEC-001 §4.1`; an unescaped `*` is glob syntax and a literal
raw asterisk is `%2A`. Unicode decoding, normalization, locale rules, and case folding are never
applied to path matching.

| Pattern | Matches | Does not match |
|---|---|---|
| `release/*` | `release/v1` | `release/v1/hotfix`, `Release/v1` |
| `release/**` | `release/v1`, `release/v1/hotfix` | `release`, `releases/v1` |
| `docs/**` | `docs/a.md`, `docs/api/a.md` | `docs`, `src/docs/a.md` |
| `**/*.lock` | `uv.lock`, `nested/uv.lock` | `uv.lock.bak` |
| `**/auth/**` | `auth/a.py`, `src/auth/a.py` | `src/author/a.py` |
| `**` | Every non-empty canonical path | — |

A policy matches only when at least one branch pattern matches the target branch and at least one
path pattern matches a changed path. An empty ChangeSet matches no policy.

## 5. Data contracts

```python
class VerificationView(Protocol):
    status: Literal["verified", "verified-untrusted-environment", "failed"]
    statement: Statement | None
    failure_code: str | None
    verified_identity: str | None
    verified_issuer: str | None
    transparency_log_verified: bool

@dataclass(frozen=True)
class PolicyContext:
    target_branch: str
    changed_paths: tuple[CanonicalGitPath, ...]

@dataclass(frozen=True)
class PolicySource:
    path: str | None
    sha256: str | None          # SHA-256 of exact raw bytes

class PolicyDocument(BaseModel):
    version: Literal[1]
    policies: tuple[Policy, ...]

@dataclass(frozen=True)
class LoadedPolicy:
    document: PolicyDocument | None
    source: PolicySource
    reporting_only_notice: str | None

@dataclass(frozen=True)
class PredicateResult:
    name: str                  # stable closed predicate name
    status: Literal["passed", "failed", "not-applicable"]
    reason: str                # stable closed reason code
    detail: str | None         # sanitised policy/check/path identifier; never content or secrets

@dataclass(frozen=True)
class PolicyResult:
    policy_id: str
    matched: bool | None       # None when verification failure prevents matching
    on_violation: Literal["block", "warn"]
    predicates: tuple[PredicateResult, ...]

@dataclass(frozen=True)
class Decision:
    outcome: Literal["allow", "warn", "deny"]
    exit_code: Literal[0, 3, 4, 5]
    source: PolicySource
    notice: str | None
    policies: tuple[PolicyResult, ...]

def load_policy(raw: bytes | None, path: str | None = None) -> LoadedPolicy: ...

def evaluate(
    verification: VerificationView | None,
    policy: LoadedPolicy,
    context: PolicyContext,
) -> Decision: ...
```

The evaluator obtains the `Predicate` only from `verification.statement` after successful F-08
verification. It does not accept a separately supplied predicate. `PolicyContext.changed_paths`
is the complete canonical path set from the same caller-selected ChangeSet supplied to F-08
recomputation; it must not come from optional or truncated `Predicate.changeSet.paths`.
`target_branch` is non-empty. Changed paths are unique and sorted by decoded raw bytes in CSD-1
order. An invalid context or an internally inconsistent verification view raises
`ERR-POLICY-604`; it is never reclassified as an absent attestation.

`PolicySource.path`, when present, is non-empty. `PolicySource.sha256` is present exactly when raw
bytes were supplied. `LoadedPolicy.document is None` only for absent or content-empty input and is
paired with the exact reporting-only notice defined in §5.3.

A successful verification view is internally consistent only when `statement` is present and
`failure_code` is absent. A failed view is internally consistent only when `statement` is absent
and `failure_code` is present. `verification is None` is the sole representation of an absent
attestation. Verified identity/issuer may be absent and log evidence may be false in another
protocol-compatible implementation; configured signer/log predicates then fail closed.

### 5.1 Loading boundary

The pure loader receives bytes and never opens `path`. It computes `PolicySource.sha256` over the
exact raw bytes before parsing. Input is bounded to 1 MiB, strict UTF-8, exactly one YAML document,
and no more than 32 nested collection levels. Duplicate keys, anchors, aliases, merge keys,
explicit tags or directives, multiple documents, floats, timestamps, and custom scalar
construction are `ERR-POLICY-601`. Exactly 1,048,576 input bytes are allowed; one more byte is not.
The root mapping has collection depth 1, each nested mapping or list adds 1, and a scalar adds no
depth. Plain lowercase `true`, `false`, and `null` are the only boolean/null spellings; decimal
integers match `0|-?[1-9][0-9]*`; quoted scalars are strings. Other non-floating,
non-timestamp plain scalars are strings. Error details may identify a field location but must not
repeat its value.

`raw is None` with no path means no configured policy. Empty, whitespace-only, or comment-only
bytes mean a configured but empty policy and retain the path and digest. Both are reporting-only
with an explicit notice. An explicitly configured path that the CLI cannot read is
`ERR-POLICY-603` and exit `2`; the CLI must not convert it to policy absence.

### 5.2 Predicate semantics

Every loaded policy is reported. `match.branches` and `match.paths` each produce a result.
Requirements under a nonmatching policy are `not-applicable`. For a matching policy:

| Predicate | Pass condition |
|---|---|
| `attestation` | A successful verification view contains its verified Statement |
| `environment.trusted` | `predicate.collection.environment.trusted is true` |
| `signer.issuer` | `verified_issuer` exactly equals the configured issuer |
| `signer.identity` | `verified_identity` matches the bounded F-08 identity pattern |
| `transparencyLog` | `transparency_log_verified is true` |
| `review.when.authorshipMode` | The signed authorship mode is listed; otherwise dependent review predicates are `not-applicable` |
| `review.minHumanApprovals` | Signed `humanApprovals` is at least the configured integer |
| `review.approverMustNotBeAuthor` | Effective markers are present and at least `minHumanApprovals` distinct effective approved immutable reviewer IDs have `isChangeAuthor is false` |
| `authorship.claimsRequired` | Signed `claimsPresent is true` |
| `checks.mustPass` | Each configured exact name exists and every retained terminal record with that name has conclusion `success` |

The immutable reviewer ID is the numeric middle component of the namespaced identity. Logins are
never used for equality or deduplication. Only records with `effective is true` and verdict
`approved` count for separation of duties. Check names are exact and case-sensitive. F-09 does not
infer a latest check from run ID or array order. At least one matching check record is required.
An all-unmarked legacy Review may satisfy `minHumanApprovals` from its signed aggregate but fails an
active `approverMustNotBeAuthor` predicate because effective non-author approvals are unprovable.

Stable predicate names and reason codes are part of the v1 machine-readable Decision contract. The
closed predicate-name vocabulary is:

| Predicate name |
|---|
| `match.branches` |
| `match.paths` |
| `require.attestation` |
| `require.environment.trusted` |
| `require.signer.issuer` |
| `require.signer.identity` |
| `require.transparencyLog` |
| `require.review.when.authorshipMode` |
| `require.review.minHumanApprovals` |
| `require.review.approverMustNotBeAuthor` |
| `require.authorship.claimsRequired` |
| `require.checks.mustPass` |

`require.checks.mustPass` produces one result per configured check name, in policy declaration
order, with the exact check name in sanitised `detail`. Every other configured key produces one
result. Results are ordered as the table above, independent of YAML mapping order. The closed
reason vocabulary is:

| Reason |
|---|
| `matched` |
| `not-matched` |
| `verification-failed` |
| `policy-not-matched` |
| `requirement-disabled` |
| `review-condition-met` |
| `review-condition-not-met` |
| `attestation-present` |
| `attestation-missing` |
| `environment-trusted` |
| `environment-untrusted-or-unknown` |
| `signer-issuer-matched` |
| `signer-issuer-mismatched` |
| `signer-identity-matched` |
| `signer-identity-mismatched` |
| `transparency-log-verified` |
| `transparency-log-unverified` |
| `approvals-satisfied` |
| `approvals-insufficient` |
| `non-author-approvals-satisfied` |
| `non-author-approvals-insufficient` |
| `effective-review-state-missing` |
| `claims-present` |
| `claims-missing` |
| `checks-passed` |
| `check-missing` |
| `check-not-successful` |

When an attestation is missing, `require.attestation` fails and every other configured requirement
is `not-applicable` with reason `attestation-missing`. When a configured review condition does not
match, that condition and its dependent review results are `not-applicable` with reason
`review-condition-not-met`; a matching condition is `passed` with `review-condition-met`.

### 5.3 Decision and exit precedence

All loaded policies are reported in policy declaration order and all matching policies are
evaluated; no first-policy short circuit is permitted.

| Precedence | Condition | Outcome | Exit |
|---:|---|---|---:|
| 1 | F-08 verification failed | `deny` | 4 |
| 2 | Attestation missing and at least one violated matching policy is `block` | `deny` | 5 |
| 3 | Any other violation under a matching `block` policy | `deny` | 3 |
| 4 | One or more violations, all under matching `warn` policies | `warn` | 0 |
| 5 | No blocking or warning violation | `allow` | 0 |

On verification failure, policies are still enumerated but matching and requirements report
`not-applicable` with a verification-failed reason. Missing attestations under warning-only
policies report violations but exit `0`. An absent or empty policy yields `allow`, exit `0`, and a
reporting-only notice. The exact absent notice is `No policy configured; reporting only.` The exact
configured-empty notice is `Policy contains no rules; reporting only.`

## 6. Requirements

| ID | Requirement |
|---|---|
| `REQ-F09-010` | Policy loading and evaluation **MUST** be pure functions of their explicit inputs and perform no filesystem, process, clock, environment, or network I/O. The evaluator **MUST** obtain the predicate only from a successful verification view. |
| `REQ-F09-020` | Policy models **MUST** be strict immutable Pydantic v2 models with unknown fields forbidden; `policy-v1.schema.json` **MUST** be generated from them and drift-checked. |
| `REQ-F09-030` | Exit precedence **MUST** follow §5.3: a missing attestation exits `5` only for a matching blocking policy and exits `0` for warning-only policy. |
| `REQ-F09-040` | A verification failure **MUST** yield exit `4` before matching or policy predicate evaluation. |
| `REQ-F09-050` | All loaded policies **MUST** be reported and all matching policies **MUST** be evaluated; the most severe result determines the Decision. |
| `REQ-F09-060` | The Decision **MUST** enumerate match results and every configured predicate with `passed`, `failed`, or `not-applicable`, a stable reason code, and sanitised detail. |
| `REQ-F09-070` | `onViolation: warn` **MUST** report violations and exit `0`. |
| `REQ-F09-080` | Branch and canonical raw-path matching **MUST** implement §4.3 exactly and **MUST NOT** delegate semantics to library glob defaults. |
| `REQ-F09-090` | YAML loading **MUST** enforce every construction, scalar, and resource rule in §5.1 and **MUST NOT** execute code, access I/O, expand aliases, or accept ambiguous duplicate keys. |
| `REQ-F09-100` | The Decision **MUST** identify the policy source by supplied display path and the SHA-256 of exact raw bytes. |
| `REQ-F09-110` | Separation of duties **MUST** use distinct effective approved immutable reviewer IDs and **MUST NOT** compare mutable logins or infer effective state from array order. A legacy all-unmarked Review **MUST** fail an active separation predicate with `effective-review-state-missing`. |
| `REQ-F09-120` | An absent or configured-empty policy **MUST** exit `0` with an explicit reporting-only notice; an unreadable configured path **MUST** remain `ERR-POLICY-603`, never absence. |
| `REQ-F09-130` | Only strict integer policy `version: 1` is supported; another integer is `ERR-POLICY-602`, while a malformed version is `ERR-POLICY-601`. |
| `REQ-F09-140` | Policy **MUST NOT** expose a mechanism to exclude paths from or otherwise alter the ChangeSet Digest. |
| `REQ-F09-150` | `PolicyContext` **MUST** carry a non-empty caller-selected target branch and unique complete canonical changed paths in decoded raw-byte order from the same ChangeSet used for F-08 recomputation; truncated predicate paths **MUST NOT** be used for matching. Invalid context **MUST** raise `ERR-POLICY-604`. |
| `REQ-F09-160` | Signer and transparency predicates **MUST** consume only F-08's verified exact identity, verified exact issuer, and affirmative log evidence; identity matching **MUST** use the shared `attest-core` grammar utility, and policy **MUST NOT** repeat or weaken cryptographic verification. |
| `REQ-F09-170` | Structural and cross-field invariants in §4.1 **MUST** be enforced, including unique IDs/lists, paired signer fields, nested-requirement attestation, and review separation minimums. |
| `REQ-F09-180` | `checks.mustPass` **MUST** use exact case-sensitive names, require at least one retained record per name, and require every retained record for that name to be `success`; no latest-run inference is permitted. |

## 7. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F09-010` | A no-syscall harness proves load and evaluate perform no I/O; the evaluator has no separately supplied Predicate argument. |
| `AC-F09-020` | Unknown keys fail `ERR-POLICY-601`; generated policy schema validates the example and a manual schema edit fails drift checking. |
| `AC-F09-030` | Missing attestation under otherwise identical block and warn policies yields exits `5` and `0` respectively. |
| `AC-F09-040` | A failed/tampered verification view yields exit `4` and every policy predicate is `not-applicable`. |
| `AC-F09-050` | Two matching policies, one warning and one blocking, are both present in the result and yield `deny`. |
| `AC-F09-060` | A snapshot covers every policy and every closed predicate/reason value in §5.2, including one ordered result per configured required check. |
| `AC-F09-070` | A warning-only predicate failure yields `warn`, exit `0`, and the violation in output. |
| `AC-F09-080` | A table test covers every valid example in §4.3, invalid token, root-level `**`, raw-byte percent encoding, case, and whole-string anchoring. |
| `AC-F09-090` | The exact byte/depth boundaries and scalar forms pass; oversize/deep input, duplicate keys, aliases, anchors, merges, tags, directives, extra documents, floats, timestamps, legacy boolean spellings, and construction payloads all fail safely without I/O. |
| `AC-F09-100` | Source output contains the supplied path and an independently computed raw-byte SHA-256, including empty bytes. |
| `AC-F09-110` | Superseded self-approval does not count; the effective non-author approval does; a renamed login cannot change immutable-ID equality; an all-unmarked historical Review fails separation with `effective-review-state-missing`. |
| `AC-F09-120` | No source and an empty configured source each exit `0` with reporting-only notice; the CLI integration keeps unreadable configuration at `ERR-POLICY-603`. |
| `AC-F09-130` | `version: 99` fails `ERR-POLICY-602`; missing, string, and boolean versions fail `ERR-POLICY-601`. |
| `AC-F09-140` | Changing among all example policies leaves the supplied predicate and ChangeSet digest byte-identical. |
| `AC-F09-150` | A predicate with missing/truncated path summary still matches from complete context; empty target, duplicate/non-canonical/unsorted paths, and inconsistent verification view fail `ERR-POLICY-604`; a context/digest mismatch is rejected before policy by F-08. |
| `AC-F09-160` | Near-miss verified issuer/identity and false log evidence fail their predicates; F-08 and F-09 pass the shared identity table; no policy module imports Sigstore or parses certificates/bundles. |
| `AC-F09-170` | A parametrised invalid-policy matrix covers every structural and cross-field rule in §4.1. |
| `AC-F09-180` | Missing, case-mismatched, failed, neutral, and mixed-rerun checks fail; one or multiple all-success exact-name records pass. |

## 8. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-POLICY-601` | Unsafe, unknown, malformed, ambiguous, or resource-limit-exceeding policy input | Correct the named location using the v1 closed vocabulary |
| `ERR-POLICY-602` | Unsupported integer policy version | Upgrade attest or use policy version `1` |
| `ERR-POLICY-603` | Explicitly configured policy file unreadable at the CLI I/O boundary | Check the exact configured path and permissions |
| `ERR-POLICY-604` | Invalid PolicyContext or internally inconsistent verification view | Supply the exact validated target and complete CSD-1-ordered ChangeSet context |
| `ERR-POLICY-610` | Blocking policy violation; informational code accompanying exit `3` | Address the named failed predicate |

## 9. Out of scope

Organisation-wide policy distribution (v1.1), automatic remediation, scripting (`ADR-008`),
policy-controlled ChangeSet exclusions, GitHub check publication, and branch-protection mutation.

## 10. Definition of Done

- [x] All `REQ-F09-*` implemented and all `AC-F09-*` green
- [x] Decision-table tests cover every predicate, status, violation mode, and exit `0`/`3`/`4`/`5`
- [x] Generated policy schema is committed and drift-checked
- [x] Safe-YAML, no-I/O, import-boundary, and no-egress tests are green
- [x] Coverage ≥ 95% for the pure package
- [x] Cross-cutting obligations satisfied

The real required-status-check blocked-merge demonstration is an F-11 completion gate, because
F-11 owns the GitHub Action and status-check integration (`ADR-042`).
