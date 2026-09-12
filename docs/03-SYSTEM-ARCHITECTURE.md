# attest — System Architecture

| Field | Value |
|---|---|
| Document ID | `ARCH-001` |
| Version | `1.3.0` |
| Status | **NORMATIVE** for component boundaries, data flow, and package rules |
| Last updated | 2026-09-12 |

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
| `builder.py` | Pure deterministic assembly and validation of a supplied `Collection` and collector outputs |
| `errors.py` | Error taxonomy with codes |
| `schema.py` | JSON Schema generation |

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
| `github.py` | GitHub REST/GraphQL | `Review`, `Check[]`, environment metadata |
| `environment.py` | CI environment variables, injected clock, installed `attest-collect` metadata | `Collection` |

Each collector is independently failable. A collector that fails **MUST** record a degradation
reason rather than aborting the run — except the git collector, whose failure is fatal because
there is nothing to attest without it.

`environment.py` is the impure edge for collection metadata. It reads process environment and
installed distribution metadata only when the caller does not inject replacements, and accepts
an injectable clock. `attest-core.builder` consumes the resulting `Collection` without reading
the environment, clock, package metadata, filesystem, or network (`ADR-036`).

### 3.3 `attest-sign`

| Module | Responsibility |
|---|---|
| `dsse.py` | Convert exact canonical payload bytes into Sigstore's public DSSE Statement type; no PAE or envelope construction |
| `sigstore_signer.py` | Process-isolated Sigstore-native keyless `sign_dsse`, ambient OIDC detection, Rekor submission, bounded bundle output |
| `verifier.py` | The §8 verification pipeline, in order |
| `trustroot.py` | Trust root management, offline trust bundle support |

`verifier.py` **MUST** implement the checks as an explicit ordered list, each returning a typed
result, so the order is auditable in code review and testable step-by-step.

### 3.4 `attest-store`

Uniform interface:

```python
class AttestationStore(Protocol):
    def put(self, digest: str, bundle: bytes) -> StoreRef: ...
    def get(self, digest: str) -> list[bytes]: ...
    def list(self, since: datetime | None = None) -> Iterator[StoreRef]: ...
```

Implementations: `GitRefStore`, `FilesystemStore`, `OciStore`.

### 3.5 `attest-policy`

Pure evaluation. Input: `Predicate` + `VerificationResult` + `Policy`. Output: `Decision`.

No I/O whatsoever, so policies are exhaustively testable with fixtures.

### 3.6 `attest-cli`

The top-level composition and presentation root. Owns configuration resolution, output rendering,
and exit codes. Contains no business logic — a command handler orchestrates calls and maps results
to exit codes. `attest-export` is the sole bounded lower application layer and may compose storage
and verification only for F-12 (`ADR-022`).

---

## 4. Primary flow — `attest run` in CI

```
 GitHub Actions job (id-token: write, contents: read, pull-requests: read)
    │
    ├─1─ environment.py       → Collection{kind=github-actions, trusted=true, workflowRef, …}
    ├─2─ git.py               → ChangeSetRecord (base = PR merge base, head = PR head)
    ├─3─ digest.py            → ChangeSet Digest        [pure]
    ├─4─ trailers/sidecar/    → AuthorshipClaim[]
    │    gitnotes
    ├─5─ github.py            → Review, Check[]
    ├─6─ builder              → sorted, schema-valid Statement (subject = digest)   [pure]
    ├─7─ runtime validation   → semantic invariants before signing                  [pure]
    ├─8─ sigstore_signer.py   → native sign_dsse → DSSE + Fulcio cert + Rekor entry → Bundle
    ├─9─ store.put()          → refs/attestations/<digest>
    ├─10─ verifier.py         → re-verify what we just produced  ◀── deliberate
    ├─11─ policy.evaluate()   → Decision
    └─12─ exit code           → 0 / 3 / 4 / 5
```

**Step 10 is deliberate and NORMATIVE.** The overall `attest run` operation always re-verifies
the signer's output before reporting success. This catches canonicalisation bugs, schema drift,
and clock problems at production time rather than at audit time — which is the only time that
matters and the worst time to discover them.

The wording above describes the overall `attest run` operation, not the F-06 `Signer.sign()`
adapter method. The CLI composition root owns step 10 after F-08 is available; F-06 validates its
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
    ├─ native verify_dsse with trusted root and mandatory Identity policy
    │      cert path/time + identity/issuer + transparency + DSSE   ERR-VERIFY-013
    ├─ returned payload type + Statement  ERR-VERIFY-007
    ├─ structural schema validation       ERR-VERIFY-008
    ├─ runtime semantic validation        ERR-VERIFY-009
    └─ (optional) recompute CSD-1 locally ERR-VERIFY-010
```

The Sigstore operation is an atomic cryptographic boundary (`ADR-020`). `verifier.py` may wrap its
public result and sanitise its diagnostic message, but **MUST NOT** call private verification
methods, reconstruct PAE, or classify failures by parsing exception text. Structural validation
precedes Pydantic semantic model construction (`ADR-021`).

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

Precedence, highest first:

1. CLI flags
2. Environment variables (`ATTEST_*`)
3. Repository config: `.attest/config.yaml`
4. Organisation policy (v1.1, fetched and cached)
5. Built-in defaults

Resolved configuration **MUST** be printable via `attest config show --resolved`, annotated with
the source of each value. Configuration debugging in CI is otherwise miserable.

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
| Full `attest run` in CI | < 15 s p95 | Dominated by network: Fulcio + Rekor + forge API |
| `attest verify` offline | < 2 s | Excluding trust root fetch |
| Cold start (container) | < 3 s | See `TECH-001 §9` on Python distribution |

Performance is not a differentiator here; predictability is. A gate that intermittently times out
gets disabled by the first frustrated engineer, and a disabled gate is worth nothing.
