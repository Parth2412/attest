# attest — System Architecture

| Field | Value |
|---|---|
| Document ID | `ARCH-001` |
| Version | `1.9.0` |
| Status | **NORMATIVE** for component boundaries, data flow, and package rules |
| Last updated | 2026-09-16 |

---

## 1. Architectural principles

| # | Principle | Consequence |
|---|---|---|
| P1 | **The specification is the product.** | The CLI is one implementation. No behaviour may exist in code that is not derivable from `SPEC-001`. |
| P2 | **Pure core, impure edges.** | Digest, canonicalisation, model, and policy evaluation are pure functions. All I/O lives in adapters. |
| P3 | **Verification never trusts the producer.** | The verifier shares no code path with the signer beyond the pure core. |
| P4 | **Fail closed in the gate, fail open in collection.** | A missing signal degrades the record (`unknown`); a failed verification blocks the merge. |
| P5 | **Everything signed is reproducible.** | No timestamps, ordering, or floats that cannot be recomputed. |
| P6 | **Offline verification must be possible.** | Given a bundle and a trust root, verification requires no network except optional log freshness. |
| P7 | **No hidden network calls.** | Any egress is explicit, documented, and disableable. Security tools that phone home do not get adopted. |

---

## 2. Package structure (NORMATIVE)

```
attest/
├── packages/
│   ├── attest-core/          # pure: models, schema, canonicalisation, digest, errors
│   ├── attest-collect/       # adapters: git, trailers, sidecar, forge APIs
│   ├── attest-sign/          # adapters: sigstore, dsse, bundle
│   ├── attest-store/         # adapters: git-ref, oci, filesystem
│   ├── attest-policy/        # pure: policy model + evaluation
│   ├── attest-export/        # evidence bundles, control mapping
│   └── attest-cli/           # composition root: commands, config, output, exit codes
├── spec/
│   ├── schemas/              # generated JSON Schema
│   └── testvectors/          # normative test vectors
├── action/                   # GitHub Action wrapper
└── docs/
```

### 2.1 Dependency rule (enforced in CI)

```
                         attest-cli
                    /        |        \
                   /    attest-export  \
                  /        /     \      \
     attest-collect  attest-sign  attest-store  attest-policy
                  \        |       /           /
                   \       |      /           /
                         attest-core
```

- `attest-core` **MUST NOT** import any sibling package.
- `attest-core` **MUST NOT** import any I/O library (no `httpx`, no `pygit2`, no filesystem
  access). Its dependency set is limited to Pydantic, JSON Schema validation, and
  canonicalisation/hash primitives.
- Peer adapters (`attest-collect`, `attest-sign`, `attest-store`, `attest-policy`) **MUST NOT**
  import each other.
- `attest-export` **MAY** import exactly `attest-core`, `attest-store`, and `attest-sign` as the
  bounded evidence-export application layer (`ADR-022`).
- `attest-cli` is the top-level composition and presentation root and may import every package.
  Its `0.1.0` published distribution does not depend on the unfinished `attest-export` package;
  that dependency and command activate only when F-12 is Done (`ADR-046`).
- Enforced by an import-linter contract in CI (`QA-001 §6`). A violation fails the build.

**Why this matters for AI-assisted implementation:** the most common failure mode of an agent
working on a codebase like this is quietly importing a git library into the pure core "for
convenience", which destroys testability and reproducibility. The linter makes that impossible
rather than merely discouraged.

---

## 3. Component responsibilities

### 3.1 `attest-core`

| Module | Responsibility |
|---|---|
| `models/statement.py` | `Statement`, `Subject` |
| `models/predicate.py` | `Predicate`, `ChangeSetInfo`, `Authorship`, `AuthorshipClaim`, `Review`, `Reviewer`, `Check`, `Collection` |
| `models/changeset.py` | `ChangeSetRecord`, `ChangeSetEntry` |
| `canonical.py` | RFC 8785 canonicalisation |
| `digest.py` | `CSD-1` implementation, operating on already-extracted entries |
| `identity.py` | Pure shared validation/matching for the bounded GitHub workflow identity-pattern grammar |
| `builder.py` | Pure deterministic assembly and validation of a supplied `Collection` and collector outputs |
| `errors.py` | Error taxonomy with codes |
| `schema.py` | JSON Schema generation and version-exact structural validation |

`digest.py` takes a list of `ChangeSetEntry` — it does **not** talk to git. The git adapter
produces the entries. This is what makes the digest testable against fixed vectors with no
repository.

### 3.2 `attest-collect`

| Adapter | Input | Output |
|---|---|---|
| `git.py` | repository path, base and head refs | `ChangeSetRecord` |
| `trailers.py` | commit messages in range | `AuthorshipClaim[]` |
| `sidecar.py` | `.attest/claims.d/*.json` | `AuthorshipClaim[]` |
| `gitnotes.py` | notes refs (Git AI compatibility) | `AuthorshipClaim[]` |
| `github.py` | GitHub REST/GraphQL and exact PR event/record/Compare context | `GitHubChangeSetContext`, `Review`, `Check[]` |
| `environment.py` | CI environment variables, injected clock, installed `attest-collect` metadata | `Collection` |

Each collector is independently failable. A collector that fails **MUST** record a degradation
reason rather than aborting the run — except the git collector, whose failure is fatal because
there is nothing to attest without it.

`environment.py` is the impure edge for collection metadata. It reads process environment and
installed distribution metadata only when the caller does not inject replacements, and accepts
an injectable clock. `attest-core.builder` consumes the resulting `Collection` without reading
the environment, clock, package metadata, filesystem, or network (`ADR-036`).

`identity.py` is syntax only: it validates and matches the bounded string grammar shared by F-08
and F-09. It does not parse certificates, select SANs, verify issuers, or perform cryptography.
F-08 remains the sole owner of those security operations (`ADR-042`).

GitHub event parsing and PR/Compare semantics stay in `github.py`, not the CLI. The public context
resolver binds repository, PR number, base, head, and target to GitHub's current PR response, then
returns the forge merge base and a proven-complete immutable numeric author/committer ID set for the
exact base/head pair. Incomplete, changed, or unmapped context fails before ChangeSet collection;
the existing component-wise fail-open boundary applies only to review/check evidence after context
is complete (`ADR-045`).

### 3.3 `attest-sign`

| Module | Responsibility |
|---|---|
| `dsse.py` | Convert exact canonical payload bytes into Sigstore's public DSSE Statement type; no PAE or envelope construction |
| `sigstore_signer.py` | Process-isolated Sigstore-native keyless `sign_dsse`, ambient OIDC detection, Rekor submission, bounded bundle output |
| `verifier.py` | The §8 verification pipeline and separately labelled parse-only inspection |
| `trustroot.py` | Explicit production/staging or supplied trust configuration; offline support |
| `repository.py` | Independent, bounded, read-only Git CLI recomputation for verification |
| `verify_errors.py` | Verification-only public diagnostics; no signer dependency |

`verifier.py` **MUST** implement the checks as an explicit ordered list, each returning a typed
result, so the order is auditable in code review and testable step-by-step.

Parse-only inspection reuses Bundle/payload/schema/model parsing but never enters Sigstore
verification, trust-root, identity, transparency, or repository-recomputation paths. Its only
successful status is `unverified-identity`, and it cannot construct F-09 policy evidence
(`ADR-045`).

### 3.4 `attest-store`

Uniform interface:

```python
@dataclass(frozen=True, slots=True)
class StoreRef:
    backend: Literal["git-ref", "filesystem", "oci"]
    digest: str
    bundle_digest: str
    location: str
    stored_at: datetime

class AttestationStore(Protocol):
    def put(self, digest: str, bundle: bytes) -> StoreRef: ...
    def get(self, digest: str) -> list[bytes]: ...
    def list(self, since: datetime | None = None) -> Iterator[StoreRef]: ...
```

Implementations: `GitRefStore`, `FilesystemStore`, `OciStore`.

All backends preserve exact Bundle bytes and expose content-idempotent, create-only behavior.
`get` and `list` validate storage integrity but never perform F-08 verification. Git storage uses
hash-bound metadata tag objects and writes only its object database plus `refs/attestations/`;
before allocation for publication it imports one stable, exact-digest remote snapshot through
source-only object fetches and create-only local refs, then performs a separate non-force push.
Neither import nor push overwrites an attestation ref, and import does not write `FETCH_HEAD`.
Filesystem storage uses atomically published Bundle files plus closed companion metadata inside
one configured directory. OCI storage attaches a one-layer Sigstore Bundle manifest to one
explicitly configured immutable subject descriptor and discovers it through the OCI 1.1 Referrers
API.

The application uses `put_with_fallback` with an explicit `FilesystemStore`. Primary failure
remains visible as a coded `StoreError` whose `fallback_path` lets the CLI report the preserved
local bytes. Every network or subprocess operation has a hard deadline; ORAS operations run in a
terminable worker because the locked client has no supported request-timeout parameter. Exact
formats, ordering, collision behavior, errors, and concurrency rules are governed by `ADR-043`,
the sibling-ref correction in `ADR-044`, remote discovery in `ADR-052`, and `BRD-F07`.

### 3.5 `attest-policy`

Pure loading and evaluation. Input: optional structural `VerificationView` + `LoadedPolicy` +
`PolicyContext`; output: `Decision`. The view includes the successfully verified Statement and
verified signer/log evidence, so the evaluator never accepts a separately substitutable Predicate.
The context carries the caller-selected target branch and complete canonical paths from the same
ChangeSet used for verification. `attest-policy` imports `attest-core`, not peer `attest-sign`.

The loader receives raw policy bytes and a display path but performs no I/O. The CLI reads files,
distinguishes unreadable configuration from absence, and supplies those bytes. This keeps parsing,
source digesting, glob matching, and policy evaluation exhaustively testable with fixtures
(`ADR-042`).

For `attest gate` and `attest run`, the CLI resolves one base/head pair, derives the complete path
context from it, and supplies that same pair as a mandatory F-08 `RepositoryConstraint`. Policy
evaluation starts only after recomputation succeeds; the signed optional path summary is never an
enforcement input.

### 3.6 `attest-cli`

The top-level composition and presentation root. Owns the strict configuration model, bounded safe
file I/O, intermediate application artifacts, output rendering, and exit codes. Contains no
business logic—a handler orchestrates public calls and maps typed results/errors. Config,
Collection Artifact, and machine-output schemas are generated from runtime models and independently
drift-checked. `attest-export` is the sole bounded lower application layer for F-12; `export` is not
registered until that feature exists (`ADR-022`, `ADR-045`).

### 3.7 `action/`

The GitHub Action is a presentation and orchestration adapter around the F-10 CLI, not a new
domain layer. Its Python entry point validates the closed Action inputs and event, checks OIDC and
repository completeness in the required order, invokes only public CLI operations, maps their
typed reports to Action outputs, and writes an escaped job summary. It contains no signing,
verification, policy, git, or storage business logic.

The Action container is a locked release artifact. `action.yml` references a public
multi-platform GHCR image only by manifest digest. The container uses an exec-form entry point,
disables user-site and current-directory Python imports, and never sources or executes repository
content. `run` checks OIDC before any repository-controlled read; `verify` and `gate` do not acquire
OIDC. Only validated branch `pull_request` and branch `push` events cross the boundary. Exact
inputs, outputs, failure treatment, and two-phase release ownership are governed by `ADR-046` and
`BRD-F11`.

---

## 4. Primary flow — `attest run` in CI

```
 GitHub Actions job (id-token: write, contents: write, pull-requests/checks: read)
    │
    ├─1─ environment.py       → Collection{kind=github-actions, trusted=true, workflowRef, …}
    ├─2─ github.py            → exact PR base/head, forge merge base, author/committer IDs
    ├─3─ git.py               → ChangeSetRecord (base = forge merge base, head = PR head)
    ├─4─ digest.py            → ChangeSet Digest        [pure]
    ├─5─ trailers/sidecar/    → AuthorshipClaim[]
    │    gitnotes
    ├─6─ github.py            → Review, Check[] using the resolved immutable IDs
    ├─7─ builder              → sorted, schema-valid Statement (subject = digest)   [pure]
    ├─8─ runtime validation   → semantic invariants before signing                  [pure]
    ├─9─ sigstore_signer.py   → native sign_dsse → DSSE + Fulcio cert + Rekor entry → Bundle
    ├─10─ store.put()         → refs/attestations/<digest>
    ├─11─ verifier.py        → re-verify exact identity, log, and ChangeSet  ◀── deliberate
    ├─12─ policy.evaluate()  → Decision using same target + complete changed paths
    └─13─ exit code          → 0 / 3 / 4 / 5
```

**Step 11 is deliberate and NORMATIVE.** The overall `attest run` operation always re-verifies
the signer's output before reporting success. This catches canonicalisation bugs, schema drift,
and clock problems at production time rather than at audit time — which is the only time that
matters and the worst time to discover them.

The wording above describes the overall `attest run` operation, not the F-06 `Signer.sign()`
adapter method. The CLI composition root owns step 11; F-06 validates its
bundle postconditions but does not import or partially implement the independent verifier. This
keeps the F-06 → F-08 dependency acyclic and preserves verifier isolation (`ADR-037`).

Sigstore 4.5.0 does not place explicit timeouts on its Fulcio and Rekor requests and exposes no
supported timeout injection point. F-06 therefore executes each signing attempt in a terminable
child process under a hard parent-enforced deadline. A pre-Rekor timeout may be attempted once
more; a Rekor-stage timeout is never retried because log submission is non-idempotent. No private
Sigstore HTTP client is imported or mutated (`ADR-037`).

The builder performs structural JSON Schema validation before constructing the final runtime
model. It then applies Pydantic semantic validation. `ERR-BUILD-210` contains only a safe public
message and remediation; raw validation details remain in the chained private exception and
**MUST NOT** be copied into user-facing diagnostics (`ADR-030`, `ADR-036`).

---

## 5. Verification flow — `attest verify`

```
 bundle (file | git ref | OCI | store)
    │
    ├─ parse bundle + required material   ERR-VERIFY-001
    ├─ load explicit trust source             ERR-VERIFY-012
    ├─ native verify_dsse with mandatory exact Identity policy
    │      cert path/time + identity/issuer + transparency + DSSE   ERR-VERIFY-013
    ├─ returned payload type + Statement  ERR-VERIFY-007
    ├─ structural schema validation       ERR-VERIFY-008
    ├─ runtime semantic validation        ERR-VERIFY-009
    └─ (optional) recompute caller-selected ChangeSet locally ERR-VERIFY-010
```

The Sigstore operation is an atomic cryptographic boundary (`ADR-020`). `verifier.py` may wrap its
public result and sanitise its diagnostic message, but **MUST NOT** call private verification
methods, reconstruct PAE, or classify failures by parsing exception text. Structural validation
precedes Pydantic semantic model construction (`ADR-021`).

The trust source is a required input. A service trust source names production or staging and
requires the caller to state whether a TUF refresh is allowed; a supplied client trust
configuration is offline. The verifier never infers an environment from a bundle or tries roots
until one accepts. A bounded workflow-identity glob is resolved to exactly one certificate URI SAN,
then that exact value and the exact issuer are passed to Sigstore's public `Identity` policy
(`ADR-038`).

Repository verification receives an explicit path, base revision, and head revision. Its
read-only Git CLI implementation is deliberately independent of `attest-collect`, uses only pure
`attest-core` ChangeSet construction and digest functions, and bounds every process invocation.
This preserves peer-adapter isolation while preventing the verifier from guessing that the current
`HEAD` is the ChangeSet the caller meant to check.

A successful result exposes the exact resolved certificate URI SAN, exact verified issuer, and an
affirmative transparency-log flag. Failed results expose no partial trusted evidence. F-09 consumes
only these fields and the verified Statement through its structural protocol; it does not repeat
certificate, signature, or transparency-log verification (`ADR-042`).

---

## 6. Trust boundaries

```
┌────────────────────────────── UNTRUSTED ───────────────────────────────┐
│  Repository contents · commit trailers · sidecar claim files ·         │
│  git notes · prompt digests · agent-reported timestamps                │
│  → Recorded faithfully. Never used to make a security decision.        │
└─────────────────────────────────────────────────────────────────────────┘

┌────────────────────────── SEMI-TRUSTED (API-verified) ─────────────────┐
│  Forge review records · check runs · reviewer identities               │
│  → Trusted to the extent the forge API is trusted. Response digest     │
│    recorded so the basis is traceable.                                 │
└─────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────── TRUSTED ──────────────────────────────────┐
│  CI workload OIDC identity · Fulcio certificate · Rekor inclusion      │
│  → The actual root of trust. Everything else is payload.               │
└─────────────────────────────────────────────────────────────────────────┘
```

The single most important architectural sentence in this project:

> **We are not trusting the claims. We are cryptographically binding an untrusted claim set to a
> trusted identity, a trusted timestamp, and an immutable change digest.**

Any design discussion that drifts toward "how do we make sure the AI claim is true" has left the
architecture. The correct answer is: we do not, and the format says so explicitly.

---

## 7. The sidecar claim protocol

This is the integration surface for agent harnesses, and the mechanism that makes attest
cross-vendor. It is a file-drop protocol precisely because it requires no vendor cooperation.

**Location:** `.attest/claims.d/<claimId>.json`, gitignored by default, written by a harness hook.

```json
{
  "schemaVersion": "0.1.0",
  "claimId": "01J8…",
  "agent": { "name": "claude-code", "version": "2.4.1" },
  "model": { "provider": "anthropic", "name": "claude-opus-4-6" },
  "sessionId": "sess_9f2c…",
  "promptDigest": "<64 lowercase hex characters>",
  "scope": { "paths": ["src/a.py"] },
  "claimedAt": "2026-07-20T09:14:03Z"
}
```

The accepted sidecar object is closed and versioned (`ADR-035`):

| Field | Required | Constraint |
|---|---|---|
| `schemaVersion` | yes | Literal `0.1.0` |
| `claimId` | yes | ULID or UUIDv7 per `SPEC-001 §6.3` |
| `agent` | yes | `AgentRef` |
| `model` | no | `ModelRef`; both provider and name required when present |
| `sessionId` | no | Non-empty opaque string |
| `promptDigest` | no | 64 lowercase hexadecimal characters |
| `scope` | no | `ClaimScope`; every path canonical per `SPEC-001 §4.1` |
| `claimedAt` | no | RFC 3339 timestamp |

The UTF-8 filename **MUST** be exactly `<claimId>.json`, and the filename identifier **MUST**
equal the body identifier. `source` is collector-owned and **MUST NOT** appear in the sidecar.
Unknown properties make the file malformed, with one exception: an input `prompt` property of
any JSON type is removed before closed-object validation and reported as `WARN-COLLECT-003`.
Its value is never copied into an Authorship Claim. Sidecars **MUST** be regular files;
directories, devices, and symbolic links are rejected without following them. Files are read as
UTF-8 JSON with no byte-order mark, and `source.digest` covers the exact file bytes before parsing.

Wired via each harness's existing hook mechanism (post-tool-use hooks, git hooks, or a wrapper
command). One small integration per harness; the format is identical across all of them.

**Why file-drop rather than an API:** it works with any tool that can write a file, requires no
network, no auth, no vendor partnership, and no permission from Anthropic or OpenAI. That
independence is the moat.

---

## 8. Configuration resolution

Precedence, highest first for v0.1:

1. CLI flags
2. Environment variables (`ATTEST_*`)
3. Repository config: `.attest/config.yaml`
4. Built-in defaults

Resolved configuration **MUST** be printable via `attest config show --resolved`, annotated with
the source of each value. The organisation policy layer is reserved for v1.1, reported as
unsupported, and never fetched by v0.1. The closed YAML vocabulary, environment mapping, strict
scalar rules, secret redaction, artifact formats, and safe file operations are normative in
`BRD-F10 §4`–§7 and `ADR-045`.

---

## 9. Extension points

| Point | Mechanism | v1.0 |
|---|---|---|
| Claim source | Collector protocol | Yes |
| Forge | Forge adapter protocol | GitHub only |
| Storage backend | `AttestationStore` protocol | Yes |
| Control framework mapping | Declarative YAML mapping files | Yes |
| Policy predicate | Fixed vocabulary, **not** a scripting language | Yes |

> **Deliberate non-extension:** the policy language is declarative and closed. No embedded
> scripting. A gate that can execute arbitrary code in CI with signing permissions is a supply
> chain vulnerability, not a feature.

---

## 10. Deployment topology

**v1.0 — fully decentralised.** No server. The CLI runs in CI, signs with the CI identity, stores
in the repository and the public transparency log. Verification is offline-capable.

This is a genuine adoption advantage: a security tool that requires sending your data to a
startup's servers loses most enterprise evaluations before it starts.

**v1.1 — optional hosted evidence store.** Adds retention management, cross-repository search, and
auditor access, without becoming a dependency for the core loop.

---

## 11. Performance targets

| Operation | Target | Notes |
|---|---|---|
| `CSD-1` on 1,000 changed files | < 500 ms | Pure computation over OIDs |
| Full Action step in CI | < 15 s nearest-rank p95 over 20 hosted jobs | Includes image pull and wrapper/CLI work; excludes checkout (`ADR-046`) |
| `attest verify` offline | < 2 s | Excluding trust root fetch |

Performance is not a differentiator here; predictability is. A gate that intermittently times out
gets disabled by the first frustrated engineer, and a disabled gate is worth nothing.
