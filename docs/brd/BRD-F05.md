# BRD-F05 — Attestation Builder

| Field | Value |
|---|---|
| Document ID | `BRD-F05` |
| Feature | `F-05` |
| Milestone | M1 |
| Packages | `attest-core`, `attest-collect` |
| Depends on | `F-01`, `F-02`, `F-03` |
| Status | In progress · New-statement effective review evidence governed by `ADR-042` |

---

## 1. Purpose

Assemble collector outputs into a complete, schema-valid in-toto `Statement`. The builder is a
pure function with no I/O. A bounded `attest-collect` adapter produces environment metadata using
injected or runtime inputs. Both operations are fully deterministic for supplied inputs and
exhaustively testable from fixtures.

## 2. Scope trace

`SCOPE-04`. Implements `SPEC-001 §3`, §6.1, §6.6.

## 3. Dependencies

`F-01` (types), `F-02` (ChangeSet), `F-03` (claims). `F-04` (review) is optional at M1. When it is
absent, the composition root supplies an explicit `Review` whose `state` is `unknown`; the
builder never synthesises one.

## 4. Data contract

```python
def build_statement(
    change_set: ChangeSetInfo,
    authorship: Authorship,
    review: Review,
    checks: Sequence[Check],
    collection: Collection,
) -> Statement: ...
```

The environment adapter owned by this feature is:

```python
def collect_environment(
    environ: Mapping[str, str] | None = None,
    *,
    clock: Callable[[], datetime] = utc_now,
) -> Collection: ...
```

`environ=None` reads the process environment at call time. An explicit mapping is used exactly
as supplied. The default clock returns an aware UTC `datetime`; any clock is called exactly once.
The result is normalised to UTC seconds. Missing installed distribution metadata, a missing
required argument, or an unusable required runtime value raises `ERR-BUILD-211`.

The adapter uses collector name `attest` and
`importlib.metadata.version("attest-collect")`. Environment classification uses these exact,
case-sensitive rules in precedence order:

1. `GITHUB_ACTIONS == "true"` produces `kind="github-actions"`.
2. Otherwise, `GITLAB_CI == "true"` produces `kind="gitlab-ci"`.
3. Otherwise, `CI == "true"` produces `kind="other"`.
4. Otherwise, it produces `kind="local"`.

Only a GitHub Actions result can be trusted in v0.1. It has `trusted=true` exactly when
`GITHUB_SERVER_URL == "https://github.com"`; `GITHUB_RUN_ID`, `GITHUB_WORKFLOW_REF`, and
`GITHUB_EVENT_NAME` are non-empty; `GITHUB_RUN_ATTEMPT` is a base-10 integer of at least one; and
both `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` are non-empty. The
adapter records `runId`, `runAttempt`, `workflowRef`, `eventName`, and the fixed issuer
`https://token.actions.githubusercontent.com` only from a trusted GitHub result. It never records
either OIDC request credential. An incomplete GitHub environment remains `github-actions` with
`trusted=false`; values which independently satisfy their model constraints may still be
recorded. GitLab CI, other CI, and local results are always untrusted in v0.1.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F05-010` | `build_statement` **MUST** be pure: same inputs, byte-identical canonical output. It **MUST NOT** read environment variables, a clock, installed-package metadata, the filesystem, or the network. |
| `REQ-F05-020` | `subject[0].digest["sha256"]` **MUST** be set from `change_set.digest`; the function **MUST NOT** recompute it. |
| `REQ-F05-030` | The assembled wire object **MUST** be validated against the generated JSON Schema before final Pydantic model construction. Runtime semantic validation follows. Either failure raises `ERR-BUILD-210` with no raw diagnostic in its public message. |
| `REQ-F05-040` | `predicateType` **MUST** be the constant from `attest-core`, never a literal string at the call site. |
| `REQ-F05-050` | `collect_environment` **MUST** set collector name to `attest` and version to the real installed `attest-collect` distribution version read at runtime. Missing distribution metadata raises `ERR-BUILD-211`. |
| `REQ-F05-060` | `collect_environment` **MUST** apply the exact environment precedence and GitHub trust predicate in §4. `local`, GitLab CI, and other CI are always untrusted in v0.1. OIDC request credentials **MUST NOT** enter the returned model or diagnostics. A verifier **MUST NOT** rely on the producer flag before F-08 validates the signed workload identity and issuer. |
| `REQ-F05-070` | `collect_environment` **MUST** call its injectable clock exactly once and set `collectedAt` to that instant in UTC at second precision. A naive or non-`datetime` result raises `ERR-BUILD-211`. |
| `REQ-F05-080` | Optional fields with no data **MUST** be omitted from serialisation, never emitted as `null` or empty string. Empty optional `checks` and `automatedReviews` arrays are omitted; semantically distinct path arrays are preserved exactly as supplied. |
| `REQ-F05-090` | The builder **MUST NOT** invent, infer, or default any value not supplied by a collector. The caller **MUST** supply an explicit `Review(state="unknown", ...)` when F-04 data is absent. |
| `REQ-F05-100` | Arrays **MUST** have a total deterministic order: claims by unique `claimId`; reviewers by `submittedAt`, identity, then canonical object bytes; automated reviews by `submittedAt`, tool, then canonical object bytes; checks by name then canonical object bytes. |
| `REQ-F05-110` | Every Reviewer in a newly built Statement **MUST** carry an explicit `effective` boolean. The builder **MUST** reject an unmarked or mixed Review with `ERR-BUILD-210`; accepting fully unmarked Reviews is limited to historical F-08 verification. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F05-010` | Building twice from identical inputs yields byte-identical canonical output. |
| `AC-F05-020` | A mutated `change_set.digest` propagates to the subject without recomputation. |
| `AC-F05-030` | Schema-invalid and semantic-invalid assembled objects each raise `ERR-BUILD-210` before return without exposing raw validation details in the public error. |
| `AC-F05-040` | Grep confirms no hard-coded predicate type string outside the constant definition. |
| `AC-F05-050` | The emitted collector name is `attest`; its version matches `importlib.metadata.version("attest-collect")`; missing metadata raises `ERR-BUILD-211`. |
| `AC-F05-060` | Complete GitHub Actions metadata plus OIDC request availability yields `trusted: true` and the recorded GitHub fields; removing each required signal yields `trusted: false`; local, GitLab CI, and other CI are untrusted; neither OIDC request credential is serialised or exposed by errors. |
| `AC-F05-070` | An injected aware clock is called once and produces the expected UTC second exactly; a naive or non-`datetime` result raises `ERR-BUILD-211`. |
| `AC-F05-080` | Serialised output contains no `null` values or empty strings, omits empty optional checks and automated reviews, and preserves supplied empty path arrays. |
| `AC-F05-090` | An explicitly supplied unknown review remains unknown; passing a missing required input raises `ERR-BUILD-211`; the builder never creates a review. |
| `AC-F05-100` | Shuffling every input array, including arrays whose primary sort keys tie, yields identical canonical output. |
| `AC-F05-110` | The golden Statement contains `effective` on every Reviewer; fully unmarked and mixed Review inputs both fail `ERR-BUILD-210` before signing. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-BUILD-210` | Assembled Statement fails structural or semantic validation | Report as a bug; inspect the chained private diagnostic |
| `ERR-BUILD-211` | Required collector output or runtime metadata is missing or unusable | Ensure the collector ran and the `attest-collect` package and injected inputs are valid |

## 8. Out of scope

Signing (F-06), storage (F-07), policy (F-09).

## 9. Definition of Done

- [ ] All `REQ-F05-*` implemented, all `AC-F05-*` green, including `REQ-F05-110`
- [x] Golden-file test: a fixed input set produces a committed golden Statement, byte-compared
- [x] Coverage ≥ 95% (`attest-core`: 99%; `environment.py`: 100%)
- [x] Cross-cutting obligations satisfied
