# SPEC-001 — AI Authorship Provenance Predicate

| Field | Value |
|---|---|
| Document ID | `SPEC-001` |
| Version | `0.1.5` (draft for public RFC) |
| Status | **NORMATIVE** for attestation format, digests, canonicalisation, and verification |
| Predicate type URI | `https://parth2412.github.io/attest/ai-authorship/v0.1` — see §3.1 and `ADR-013` |
| Last updated | 2026-09-14 |

> This is the document that matters most. It is the asset. The CLI is an implementation of this
> specification; the specification is not a description of the CLI. Write it as though a second,
> independent implementation in another language must interoperate — because the strategy
> depends on exactly that happening.

---

## 1. Purpose and claim model

This specification defines a predicate for [in-toto Statements] that records **the provenance of
an authoring act**: which agents and models were claimed to have contributed to a set of code
changes, which humans reviewed it, and in what environment that record was collected.

### 1.1 What a conforming attestation asserts (NORMATIVE)

A verifier that successfully validates a conforming attestation **MAY** conclude:

> At the time recorded in `collection.collectedAt`, in the environment described by
> `collection.environment`, the authorship claims listed in `authorship.claims` were present in
> the repository and were bound to the ChangeSet identified by the subject digest, together with
> the review record in `review`. This binding was signed by the identity in the signing
> certificate.

### 1.2 What it does NOT assert (NORMATIVE)

A verifier **MUST NOT** conclude, and an implementation **MUST NOT** state, that a conforming
attestation proves:

- that a specific model actually generated any specific line of code;
- that the authorship claims are complete (unclaimed AI use is undetectable by this mechanism);
- that a human reviewer understood the change;
- that the code is secure, correct, or compliant.

This is a **chain-of-custody** format. Its integrity guarantee is that the record cannot be
altered after signing without detection, and that the signer is identifiable. It makes no
epistemic claim about the truth of self-reported inputs.

Implementations **MUST** surface this distinction in verification output.

---

## 2. Conformance

An implementation is conforming if it:

1. produces Statements whose `predicateType` equals a URI defined in §3.1;
2. computes ChangeSet Digests per algorithm `CSD-1` (§5) with bit-identical results;
3. canonicalises per §4 before digesting or signing;
4. validates the structural JSON Schema in §11 and every mandatory semantic invariant before
   signing and during verification;
5. performs all mandatory verification steps in §8 in order;
6. rejects any attestation failing any mandatory check, with a code from §10.

Partial implementations (e.g. verify-only) **MUST** state which conformance clauses they meet.

---

## 3. Statement structure

### 3.1 Predicate type URI

```
https://parth2412.github.io/attest/ai-authorship/v0.1
```

**Stability (NORMATIVE, `ADR-013`).** All `v0.x` URIs are **explicitly unstable** and MAY change
without a MAJOR bump, including a change of domain, while the format is in draft. Implementations
consuming v0.x attestations **MUST** treat the identifier as provisional, and verification output
**MUST** state this for v0.x predicates. The URI **freezes permanently at v1.0**; from that point
the rules below apply without exception and every previously published URI remains verifiable
forever.

The URI **MUST** exist as a single constant in the core package and **MUST NOT** appear as a
literal at any call site (`REQ-F05-040`), so that a domain change is a one-line edit.

Version rules:
- The URI encodes `vMAJOR.MINOR`.
- Adding an **optional** field is a MINOR change and reuses the MAJOR URI.
- Removing a field, making an optional field required, or changing any field's semantics is a
  MAJOR change and **MUST** use a new URI.
- Verifiers **MUST** reject predicate types they do not recognise, rather than attempting
  best-effort parsing.

### 3.2 Statement envelope

The Statement conforms to the in-toto Statement format:

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "changeset",
      "digest": {
        "sha256": "<ChangeSet Digest, 64 lowercase hex chars>"
      }
    }
  ],
  "predicateType": "https://parth2412.github.io/attest/ai-authorship/v0.1",
  "predicate": { }
}
```

**Subject rules (NORMATIVE):**
- `subject` **MUST** contain exactly one entry for v0.1.
- `subject[0].name` **MUST** be the literal string `changeset`.
- `subject[0].digest` **MUST** contain exactly the key `sha256`, whose value is the ChangeSet
  Digest defined in §5.
- The subject digest is the binding anchor. It is what prevents an attestation being replayed
  against a different set of changes.

The Statement fields are:

| Field | Required | Type and constraint |
|---|---|---|
| `_type` | yes | string; literal `https://in-toto.io/Statement/v1` |
| `subject` | yes | array containing exactly one `Subject` |
| `predicateType` | yes | string; literal URI from §3.1 |
| `predicate` | yes | `Predicate`, §6 |

A `Subject` contains required `name` and `digest` fields. `name` is the literal `changeset`.
`digest` is a closed object containing exactly one required property, `sha256`, whose value is
exactly 64 lowercase hexadecimal characters.

Ordinary wire properties follow the camel-case rule in `GLOSS-001 §4`. The in-toto property
`_type` and digest-map key `sha256` are protocol-defined exceptions (`ADR-029`).

> **Design note.** The subject is the ChangeSet Digest rather than the head commit SHA. Commit
> SHAs change on rebase, squash, and amend, which would silently invalidate every attestation in
> a squash-merge workflow. The ChangeSet Digest is stable across those operations because it is
> derived from the resulting tree differences, not from commit identity. The head commit is still
> recorded, inside the predicate, for human traceability.

---

## 4. Canonicalisation (NORMATIVE)

Any JSON that is digested or signed **MUST** first be canonicalised using **RFC 8785 JSON
Canonicalization Scheme (JCS)**.

Requirements:
- Object keys sorted by UTF-16 code unit as specified by RFC 8785.
- No insignificant whitespace.
- Numbers serialised per RFC 8785 (which constrains them to the ECMAScript number model).
- **Implementations MUST NOT emit floating-point numbers in any signed field.** All numeric
  fields in this specification are integers. This avoids the entire class of float
  canonicalisation ambiguity.
- Strings encoded as UTF-8, escaped per RFC 8785.

Implementations **MUST** produce byte-identical canonical output for semantically identical
input. This is verified by the cross-implementation test vectors in §12.

### 4.1 Canonical Git path representation (NORMATIVE)

Git paths are raw byte strings. Every Git path in a signed or digested field **MUST** use the
canonical percent-encoded representation defined by `ADR-018`:

- bytes for ASCII letters, digits, `-`, `.`, `_`, `~`, and separator `/` are emitted unchanged;
- every other byte is emitted as `%HH` with uppercase hexadecimal digits, including `%` itself
  and every byte at or above `0x80`;
- Unicode decoding, case folding, locale collation, and Unicode normalisation **MUST NOT** be
  applied before encoding;
- malformed escapes, lowercase hexadecimal escapes, and percent-encoded bytes from the unchanged
  set are non-canonical and **MUST** be rejected; and
- decoding the canonical representation **MUST** reproduce the original bytes exactly.

For example, raw bytes `b"docs/caf\xC3\xA9-\xFF.md"` are represented as
`docs/caf%C3%A9-%FF.md`. Human-facing renderers may decode valid UTF-8 for display, but display
text is never an input to digesting, sorting, scope matching, or policy evaluation.

---

## 5. ChangeSet Digest — algorithm `CSD-1` (NORMATIVE)

This is the core algorithm. It **MUST** be implemented exactly.

### 5.1 Rationale

The digest **MUST NOT** be computed over rendered diff text. Rendered diffs depend on the diff
algorithm (`myers`, `patience`, `histogram`), context line count, whitespace-handling flags,
rename detection heuristics, and renderer version. None of those are stable across tools or
time.

Git object identities are stable, content-addressed, and reproducible by any git implementation.
`CSD-1` therefore digests the *set of (path, mode, blob-OID) transitions*, not the textual diff.
Commit identities are inputs used to derive that set, but are excluded from the digest per
`ADR-019` so rebases and squash merges do not change the identity of an unchanged transition set.

### 5.2 Inputs

| Input | Constraint |
|---|---|
| `baseCommit` | Full 40-hex commit OID, **MUST** be an ancestor-side reference point |
| `headCommit` | Full 40-hex commit OID |
| Repository | **MUST** contain both commits and all reachable trees/blobs |

### 5.3 Procedure

1. Resolve the tree of `baseCommit` (`T_base`) and of `headCommit` (`T_head`).
2. Compute the recursive difference between `T_base` and `T_head` with:
   - **rename detection DISABLED**,
   - **copy detection DISABLED**,
   - **no similarity heuristics**.
   Renames therefore appear as one deletion and one addition. This is intentional: rename
   detection is a similarity heuristic and is not reproducible across implementations.
3. For each differing path, emit an **entry object**:

   ```json
   {
     "path": "<canonical percent-encoded raw Git path, '/' separated>",
     "changeType": "added" | "modified" | "deleted" | "typechange",
     "oldMode": "<6-digit octal string>" | null,
     "newMode": "<6-digit octal string>" | null,
     "oldBlob": "<40-hex OID>" | null,
     "newBlob": "<40-hex OID>" | null
   }
   ```

   Rules:
   - For `added`: `oldMode` and `oldBlob` are `null`.
   - For `deleted`: `newMode` and `newBlob` are `null`.
   - For `modified`: all four are non-null. A mode-only change with identical blob OIDs is
     `modified`.
   - `typechange` is used when the entry type changes (e.g. file ↔ symlink).
   - Submodule (gitlink, mode `160000`) entries are included; the "blob" OID is the recorded
     commit OID of the submodule.
   - Symlinks are included; the blob OID is the OID of the blob containing the link target.
4. Decode each canonical `path` per §4.1 and sort the entry objects by the resulting **raw Git
   path bytes**, ascending, using unsigned byte comparison. Sorting **MUST NOT** use the encoded
   strings, locale collation, Unicode decoding, or Unicode normalisation.
5. Construct the **ChangeSet Record**:

   ```json
   {
     "algorithm": "CSD-1",
     "entries": [ <sorted entry objects> ]
   }
   ```
   The record **MUST NOT** contain `baseCommit`, `headCommit`, `mergeBase`, repository identity,
   timestamps, or any other contextual field. Those values belong in the signed predicate.
6. Canonicalise the ChangeSet Record per §4.
7. The **ChangeSet Digest** is the SHA-256 of the canonical bytes, rendered as 64 lowercase hex
   characters.

### 5.4 Edge cases (NORMATIVE)

| Case | Required behaviour |
|---|---|
| Empty ChangeSet (no differences) | `entries` is `[]`. Every empty ChangeSet has the same `CSD-1` digest by design; signed predicate metadata distinguishes contexts. It **MAY** be attested, and policy decides whether to allow it. |
| Merge commits | `baseCommit` **MUST** be the merge base used by the forge for the pull request. Implementations **MUST** record which merge base was used and **MUST NOT** guess. |
| Binary files | Treated identically. Only OIDs are used, so content type is irrelevant. |
| Paths with invalid UTF-8 | Represented using canonical percent encoding per §4.1. Implementations **MUST** round-trip such paths byte-identically and **MUST NOT** place surrogate code points in JSON. |
| Case-insensitive filesystems | The digest uses the paths as recorded in the git tree, not as rendered by the filesystem. |
| Very large ChangeSets | No limit is imposed by this spec. Implementations **SHOULD** stream rather than buffer. |

---

## 6. Predicate fields

The field tables in this section are the complete v0.1 structural contract (`ADR-029`). A required
field must be present. An optional field may be omitted or set to JSON `null`; conforming emitters
**MUST** omit optional fields whose value is null so that they produce one canonical shape. Unless
stated otherwise, strings are non-empty, integer counts are non-negative, and arrays may be empty.

### 6.1 Top-level structure

```json
{
  "schemaVersion": "0.1.0",
  "changeSet": { },
  "authorship": { },
  "review": { },
  "checks": [ ],
  "collection": { }
}
```

| Field | Required | Type |
|---|---|---|
| `schemaVersion` | yes | string, SemVer |
| `changeSet` | yes | object, §6.2 |
| `authorship` | yes | object, §6.3 |
| `review` | yes | object, §6.4 |
| `checks` | no | array, §6.5 |
| `collection` | yes | object, §6.6 |

Unknown top-level fields **MUST** cause validation failure. Strict schemas prevent silent data
loss and prevent an implementation inventing fields.

### 6.2 `changeSet`

```json
{
  "repository": "https://github.com/org/repo",
  "algorithm": "CSD-1",
  "baseCommit": "aaaa…",
  "headCommit": "bbbb…",
  "mergeBase": "aaaa…",
  "digest": "<ChangeSet Digest>",
  "stats": {
    "filesChanged": 12,
    "filesAdded": 3,
    "filesModified": 8,
    "filesDeleted": 1
  },
  "paths": [ "src/a.py", "src/b.py" ]
}
```

| Field | Required | Notes |
|---|---|---|
| `repository` | yes | Canonical clone URL, normalised: `https`, no credentials, no `.git` suffix, no trailing slash |
| `algorithm` | yes | **MUST** be `CSD-1` for this spec version |
| `baseCommit`, `headCommit` | yes | Full 40-hex |
| `mergeBase` | no | Present when the ChangeSet derives from a pull request |
| `digest` | yes | **MUST** equal `subject[0].digest.sha256`. A verifier **MUST** check this equality. |
| `stats` | yes | Integers only. Line counts are deliberately **excluded** — they are diff-algorithm dependent and would be non-reproducible. |
| `paths` | no | Canonical Git paths per §4.1. **MAY** be omitted or truncated for very large ChangeSets; if truncated, `pathsTruncated: true` **MUST** be set. Renderers may provide decoded display text separately. |
| `pathsTruncated` | no | Boolean. When `true`, `paths` **MUST** be present and contains only the retained prefix. When absent or `false`, no truncation is asserted. |

`stats` is a `ChangeSetStats` object with four required non-negative integer fields:
`filesChanged`, `filesAdded`, `filesModified`, and `filesDeleted`. `filesChanged` counts every
entry, including `typechange`; the other three fields count only their named change types.

> **Note on line counts.** Every AI-analytics tool reports "lines added by AI". We deliberately
> do not, in signed fields, because line counts cannot be reproduced deterministically. Reporting
> layers may compute them; they are not part of the signed record.

### 6.3 `authorship`

```json
{
  "mode": "ai-assisted",
  "claimsPresent": true,
  "claims": [
    {
      "claimId": "01J8…",
      "agent":  { "name": "claude-code", "version": "2.4.1" },
      "model":  { "provider": "anthropic", "name": "claude-opus-4-6", "version": "20260401" },
      "sessionId": "sess_9f2c…",
      "promptDigest": "<64 lowercase hex characters>",
      "scope": { "paths": ["src/a.py"] },
      "source": {
        "kind": "sidecar",
        "reference": ".attest/claims.d/01J8….json",
        "digest": "<64 lowercase hex characters>"
      },
      "claimedAt": "2026-07-20T09:14:03Z"
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `mode` | yes | Enum: `human-authored`, `ai-assisted`, `ai-authored`, `unknown`. **MUST** be `unknown` when no claims are present and the collector cannot determine the mode. **MUST NOT** default to `human-authored`. |
| `claimsPresent` | yes | Boolean. Explicit, so "no claims" is affirmatively recorded rather than inferred from an empty array. |
| `claims` | yes | Array, possibly empty |
| `claims[].claimId` | yes | ULID or UUIDv7, unique within the attestation |
| `claims[].agent` | yes | The harness (e.g. `claude-code`, `cursor`, `codex-cli`, `copilot`, `aider`). Free-form string; a registry of known values is maintained in §13 but unknown values are permitted. |
| `claims[].model` | no | Absent when the harness does not disclose it. **MUST NOT** be guessed. |
| `claims[].sessionId` | no | Opaque identifier from the harness |
| `claims[].promptDigest` | no | Digest of prompt text. **Raw prompt text MUST NOT appear in this predicate.** See `SEC-001 C-06`. |
| `claims[].scope.paths` | no | Canonical Git paths per §4.1. Absent means the claim is ChangeSet-wide; coverage comparison is over decoded raw bytes. |
| `claims[].source` | yes | Provenance of the claim itself: how the collector learned it |
| `claims[].source.kind` | yes | Enum: `trailer`, `sidecar`, `git-note`, `forge-api`, `manual` |
| `claims[].source.digest` | yes | Digest of the raw source material, so the claim can be traced back |
| `claims[].claimedAt` | no | Timestamp asserted by the claiming tool. **Untrusted** — it is the tool's clock. |

`mode`, `claimsPresent`, and `claims` are required. `mode` has no wire-model default. A collector
that has no authorship evidence **MUST** explicitly emit `unknown`; it must not omit `mode`.

Nested authorship objects have these fields:

| Object | Required fields | Optional fields | Constraints |
|---|---|---|---|
| `AuthorshipClaim` | `claimId`, `agent`, `source` | `model`, `sessionId`, `promptDigest`, `scope`, `claimedAt` | `claimId` is a ULID or UUIDv7; `promptDigest`, when present, is 64 lowercase hex |
| `AgentRef` | `name` | `version` | Free-form harness name; unknown names are valid |
| `ModelRef` | `provider`, `name` | `version` | Values **MUST NOT** be guessed |
| `ClaimScope` | `paths` | — | Every item is a canonical Git path per §4.1 |
| `ClaimSource` | `kind`, `reference`, `digest` | — | `kind` uses the closed enum above; `digest` is 64 lowercase hex |

When a conforming collector receives a source that has no native `claimId`, it **MUST** generate
a standards-valid UUIDv7 (`ADR-035`). The generated identifier is source identity only: it
**MUST NOT** populate `claimedAt`, serve as evidence of source time, or affect a trust decision.
Source-specific reference strings and raw digest boundaries are defined by the owning collector
BRD.

**Mode derivation (NORMATIVE).** The collector **MUST** derive `mode` as follows and **MUST NOT**
apply any other heuristic:

| Condition | `mode` |
|---|---|
| The ChangeSet is non-empty and at least one claim with `source.kind` in {`trailer`,`sidecar`,`git-note`,`forge-api`} independently covers all changed paths | `ai-authored` |
| The ChangeSet is non-empty, the preceding row does not match, and at least one such claim independently covers a non-empty proper subset of changed paths | `ai-assisted` |
| Claims are present but neither preceding coverage row matches, including manual-only claims and every claim-bearing empty ChangeSet | `unknown` |
| No claims, and the repository has an `.attest/` marker indicating claim collection is active | `human-authored` |
| No claims, and no marker | `unknown` |

Scope absence covers the entire ChangeSet only when the ChangeSet is non-empty. Coverage is
evaluated per claim over decoded raw path bytes; scopes from multiple claims **MUST NOT** be
unioned to satisfy a coverage row. Paths outside the ChangeSet do not prevent a claim from
covering all changed paths, but the collector retains and warns about those paths per
`REQ-F03-070`. The marker is an existing `.attest/` directory at the repository root and is
consulted only when no claims are present (`ADR-035`).

### 6.4 `review`

```json
{
  "required": true,
  "state": "approved",
  "humanApprovals": 1,
  "reviewers": [
    {
      "identity": "github:12345:bob",
      "identityProvider": "github",
      "verdict": "approved",
      "submittedAt": "2026-07-20T11:02:44Z",
      "effective": true,
      "isChangeAuthor": false,
      "evidence": { "kind": "forge-api", "digest": "<64 lowercase hex characters>" }
    }
  ],
  "automatedReviews": [
    {
      "tool": "coderabbit",
      "verdict": "commented",
      "findingsDigest": "<64 lowercase hex characters>",
      "submittedAt": "2026-07-20T10:31:00Z"
    }
  ],
  "reviewLatencySeconds": 6521
}
```

| Field | Required | Notes |
|---|---|---|
| `required` | yes | Boolean or the literal string `unknown`; whether the forge required review for this merge |
| `state` | yes | Enum: `approved`, `changes-requested`, `commented`, `none`, `unknown` |
| `humanApprovals` | yes | Integer count of distinct latest human approvals; when effective markers are present, must equal the number of effective records whose verdict is `approved` |
| `reviewers` | yes | Array of `Reviewer`, possibly empty |
| `reviewers[].identity` | yes | Stable, namespaced identity: `<provider>:<immutable-id>:<login>`. The immutable numeric ID **MUST** be included — logins are renameable and are insufficient for audit. |
| `reviewers[].effective` | conditional | Whether this is the latest supported submitted record for the immutable reviewer ID. It **MUST** be present on every Reviewer in newly emitted Statements. Its absence on every Reviewer is accepted only for legacy v0.1 Statements emitted before `ADR-042`. |
| `reviewers[].isChangeAuthor` | yes | Whether this reviewer also authored the change. Enables separation-of-duties policy. |
| `reviewers[].evidence.digest` | yes | Digest of the forge API response that established this record, so the claim is traceable |
| `automatedReviews` | no | Bot reviews. **MUST NOT** be counted in `humanApprovals`. |
| `reviewLatencySeconds` | no | Integer seconds between change readiness and approval |

Nested review objects have these fields:

| Object | Required fields | Optional fields | Constraints |
|---|---|---|---|
| `Reviewer` | `identity`, `identityProvider`, `verdict`, `submittedAt`, `isChangeAuthor`, `evidence` | `effective` only for legacy input compatibility | `submittedAt` is a timestamp; when present, `effective` is boolean and exactly one record per immutable reviewer ID is effective; `isChangeAuthor` is boolean; `verdict` is `ReviewVerdict` |
| `ReviewEvidence` | `kind`, `digest` | — | `kind` is the literal `forge-api`; `digest` is 64 lowercase hex |
| `AutomatedReview` | `tool`, `verdict`, `findingsDigest`, `submittedAt` | — | `findingsDigest` is 64 lowercase hex; `submittedAt` is a timestamp |

Effective markers are all-or-none within a Review. Mixed marked/unmarked records are invalid. When
markers are present, runtime semantic validation rejects zero or multiple effective records for a
represented immutable reviewer ID and rejects a `humanApprovals` count that differs from the
effective approved-record count. The generated structural schema keeps `effective` optional only
so historical signed v0.1 bundles remain verifiable; the official builder rejects its omission on
new output (`ADR-042`).

> **Design note.** Separating `humanApprovals` from `automatedReviews` is deliberate and is the
> field an auditor will care about most. A bot approving a bot's code is the exact failure mode
> the industry is drifting into.

### 6.5 `checks`

```json
[
  { "name": "unit-tests", "conclusion": "success", "runId": "1029384756", "detailsDigest": "<64 lowercase hex characters>" }
]
```

The predicate-level `checks` array is optional. Every `Check` contains the required fields `name`,
`conclusion`, `runId`, and `detailsDigest`. `conclusion` is one of `success`, `failure`, `neutral`,
`cancelled`, `skipped`, `timed_out`; `detailsDigest` is 64 lowercase hexadecimal characters.

### 6.6 `collection`

```json
{
  "collector": { "name": "attest", "version": "0.4.0" },
  "collectedAt": "2026-07-20T11:03:10Z",
  "environment": {
    "kind": "github-actions",
    "trusted": true,
    "runId": "1029384756",
    "runAttempt": 1,
    "workflowRef": "org/repo/.github/workflows/attest.yml@refs/heads/main",
    "oidcIssuer": "https://token.actions.githubusercontent.com",
    "eventName": "pull_request_target"
  }
}
```

| Field | Required | Notes |
|---|---|---|
| `collector` | yes | Name and version of the implementation |
| `collectedAt` | yes | Collector's clock. Trust anchor is the transparency log timestamp, not this. |
| `environment.kind` | yes | Enum: `github-actions`, `gitlab-ci`, `local`, `other` |
| `environment.trusted` | yes | `false` **MUST** be set for `local`. Policies **SHOULD** refuse to gate on untrusted-environment attestations. |

`Collection` contains required `collector`, `collectedAt`, and `environment` fields.
`CollectorRef` contains required non-empty `name` and `version` strings. `EnvironmentRef` contains
required `kind` and `trusted` fields and optional `runId`, `runAttempt`, `workflowRef`, `oidcIssuer`,
and `eventName` fields. `runAttempt`, when present, is an integer of at least one. An environment
whose `kind` is `local` **MUST** have `trusted: false`; this is enforced as a runtime semantic
invariant as well as during collection.

`environment.trusted` is producer context, not independent proof of trust. A producer **MUST NOT**
set it to `true` unless it recognises the CI platform and a workload-identity credential is
available for the recorded run. A verifier **MUST NOT** rely on `trusted: true` until the
attestation signature has been verified against the caller's expected workload identity and
issuer. Environment-variable presence alone is not a verifier trust anchor because a local
process can reproduce those variables.

The Python v0.1 reference implementation recognises only GitHub Actions on `github.com` as a
trusted environment. It requires the exact signals and records the exact non-secret metadata in
`ADR-036`; GitLab CI and every other CI environment remain untrusted until a workload-identity
contract is specified for that platform. OIDC request credentials **MUST NOT** be copied into the
predicate or diagnostics.

> **Critical.** An attestation produced on a developer laptop is not worthless — it is a
> developer-asserted record. But it must be distinguishable from one produced by a CI job whose
> identity is cryptographically bound. The `trusted` flag makes that distinction explicit and
> machine-checkable rather than leaving it implied.

---

## 7. Signing (NORMATIVE)

1. Serialise the Statement and canonicalise per §4.
2. Supply those exact canonical bytes to a conforming **DSSE** implementation with `payloadType`
   = `application/vnd.in-toto+json`.
3. Obtain an ephemeral signing key and a Fulcio certificate via **Sigstore keyless** flow, using
   an ambient OIDC identity (in CI, the workload identity token).
4. Delegate DSSE pre-authentication encoding (PAE), envelope construction, and signing to the
   DSSE implementation; none may be hand-constructed.
5. Submit the signed envelope to the **Rekor** transparency log; retain the inclusion proof and
   signed entry timestamp.
6. Emit a **Sigstore bundle** containing the DSSE envelope, leaf signing certificate,
   transparency-log entry and inclusion proof, and any timestamp verification material emitted by
   Sigstore. The configured trusted root supplies the certificate chain; the bundle is not required
   to embed that chain (`ADR-020`).

The Python reference implementation **MUST** use Sigstore's native `sign_dsse` operation and the
single-context ephemeral-key rules in `ADR-020`. Direct `securesystemslib` envelope handling and
hand-written PAE are non-conforming for that implementation.

Implementations **MAY** additionally support long-lived key signing for air-gapped environments,
but keyless **MUST** be the default and long-lived keys **MUST** be flagged in verification
output.

---

## 8. Verification (NORMATIVE)

Verification **MUST** perform these steps, in this order, and **MUST** abort at the first failure.
The cryptographic properties in step 2 are one atomic Sigstore verification boundary; an
implementation **MUST NOT** duplicate private Sigstore internals merely to expose finer failure
codes (`ADR-020`).

| # | Check | Failure code |
|---|---|---|
| 1 | Bundle is well-formed, parseable, and contains a DSSE envelope plus required signing-certificate and transparency verification material | `ERR-VERIFY-001` |
| 2 | Explicit trust material is available, then Sigstore-native DSSE verification succeeds against it and the caller's mandatory expected identity and issuer, establishing certificate path/time validity, identity policy, transparency inclusion/checkpoint, DSSE signature/PAE, and log-entry consistency | `ERR-VERIFY-012` when trust initialization fails; otherwise `ERR-VERIFY-013` |
| 3 | Returned payload type is `application/vnd.in-toto+json`, and payload bytes parse as an in-toto Statement with a recognised `predicateType` | `ERR-VERIFY-007` |
| 4 | Statement validates against the structural JSON Schema for that predicate version | `ERR-VERIFY-008` |
| 5 | Runtime semantic validation succeeds, including `predicate.changeSet.digest == subject[0].digest.sha256` | `ERR-VERIFY-009` |
| 6 | If an explicit local repository, base revision, and head revision are supplied: `CSD-1` recomputed from that caller-selected ChangeSet equals the attested digest | `ERR-VERIFY-010` |

### 8.0 Offline inclusion proof (NORMATIVE, `ADR-015`)

The inclusion proof and signed entry timestamp **MUST** be embedded in the bundle at signing time.
Step 2 **MUST** verify the proof cryptographically from bundle contents alone.

- Querying the transparency log at verification time **MUST NOT** be used as a substitute.
- No configuration option may make verification depend on log reachability.
- A bundle lacking an embedded inclusion proof **MUST** fail with `ERR-VERIFY-013`.

Trust-root selection is explicit. A caller **MUST** either select the production or staging
Sigstore environment and state whether a bounded TUF refresh is permitted, or supply a complete
Sigstore client trust configuration. A verifier **MUST NOT** infer the environment from untrusted
bundle contents, try multiple environments until one succeeds, or perform an undisclosed refresh.
Offline mode uses packaged or cached TUF material only; a supplied client trust configuration also
performs no network operation. Trust initialization failure is `ERR-VERIFY-012` in step 2.

Sigstore 4.5.0 rejects a bundle with an omitted inclusion proof while parsing it. To retain the
normative `ERR-VERIFY-013` classification above, the reference implementation performs a bounded
standard-JSON preflight: an otherwise present transparency-log entry whose proof member is absent
is recorded as a failed step 2 without calling private Sigstore APIs. Other malformed bundle
structures remain `ERR-VERIFY-001` in step 1.

Rationale: audit evidence must remain verifiable years later, without depending on any service
being reachable or any log operator continuing to exist.

### 8.1 Identity checking is mandatory

The identity policy inside step 2 is what makes this product meaningful, and it is the constraint
that is easiest to omit.

- The caller **MUST** supply an expected identity pattern and an expected OIDC issuer.
- The identity pattern and issuer **MUST** each be a non-empty string. The reference implementation
  rejects an empty or non-string issuer during constraint construction with `ERR-VERIFY-011`, before
  constructing Sigstore's policy; Sigstore 4.5.0 otherwise treats an empty issuer as no issuer
  policy (`ADR-039`).
- Implementations **MUST NOT** provide a default that accepts any identity.
- Implementations **MUST NOT** offer a flag that skips the identity policy while still reporting
  success.
- A request with no identity constraint **MUST** be rejected before verification as a usage or
  configuration error. An inspect-only surface that has not performed verification **MAY** label
  its state `unverified-identity`, but that label is never a verification success result.

Identity comparison is case-sensitive and anchored to the whole certificate identity. Exact
identities are accepted for any issuer. A bounded glob is accepted only for a GitHub Actions
workflow identity URI: everything before `@refs/` is literal and `*` may occur only in the ref,
where each `*` matches one or more non-`/` characters. `**`, `?`, bracket expressions, empty
values, and a wildcard before `@refs/` are invalid. For a bounded glob, the implementation resolves
exactly one matching URI SAN from the leaf certificate, then supplies that resolved exact value and
the caller's exact issuer to Sigstore's public `Identity` policy. Zero or multiple matching SANs
fail the atomic cryptographic step with `ERR-VERIFY-013` (`ADR-038`).

Rationale: anyone can obtain a Fulcio certificate. A signature alone proves only that *some*
identity signed. Without the mandatory identity policy, an attacker signs their own attestation
and it "verifies".

### 8.2 Structural and semantic validation (NORMATIVE, `ADR-021`)

The JSON Schema check in step 4 establishes structural validity only. Cross-field invariants that
standard generated JSON Schema cannot express are mandatory semantic checks in step 5.

- A producer **MUST** run both structural and semantic validation before signing.
- A verifier **MUST** apply the versioned structural schema before constructing the semantic
  Pydantic model, so an invalid structure fails with `ERR-VERIFY-008` rather than being collapsed
  into a semantic error.
- A verifier **MUST** reject a subject/predicate digest mismatch with `ERR-VERIFY-009`, even though
  that mismatch can pass the generated JSON Schema.
- Passing the JSON Schema alone **MUST NOT** be described as full Statement conformance.

### 8.3 Reporting

Verification output **MUST** distinguish:
- `verified` — all mandatory checks passed against a constrained identity;
- `verified-untrusted-environment` — all checks passed but `collection.environment.trusted` is false;
- `failed` — with the specific failing check and code.

The six stable check names, in order, are `bundle-structure`, `sigstore-dsse`,
`statement-payload`, `structural-schema`, `semantic-model`, and `changeset-recomputation`. Each
attempted check records `passed` or `failed`; a successful verification records the optional sixth
check as `skipped` when no repository constraint is supplied. Passed and skipped checks have no
code. The first failed check records its failure code and is the final entry; later, unattempted
checks are absent (`ADR-038`).

---

## 9. Storage and discovery

| Backend | Location | Status |
|---|---|---|
| Git ref | `refs/attestations/<changeset-digest>` | **Default** (`ADR-014`) |
| OCI registry | Referrers API, subject = image or artifact digest | Optional |
| Filesystem | `<dir>/<changeset-digest>.sigstore.json` | Always available |
| Hosted store | HTTP API | v1.1 |

**Git ref namespace (NORMATIVE, `ADR-014`, `ADR-044`).** Storage uses one ref per attestation under
`refs/attestations/`. Git notes **MUST NOT** be used for storage, because a single notes ref
produces merge conflicts under concurrent CI writes. Where more than one attestation exists for a
digest, refs are sibling names: `refs/attestations/<digest>-<log-index>`. A ref named
`refs/attestations/<digest>` and a child beneath `<digest>/` cannot coexist in Git.

Reading git notes as a *claim source* is unrelated and remains supported (`SPEC-001 §6.3`,
`BRD-F03`).

Discovery is by ChangeSet Digest. Implementations **MUST** support retrieving all attestations
for a given digest, since multiple attestations for one ChangeSet are legitimate (e.g. one at PR
time, one at merge time).

Stored Bundle bytes are opaque to this layer and **MUST** be returned unchanged even when they are
not a valid Bundle. Storage metadata **MUST** bind the ChangeSet Digest, SHA-256 of the exact Bundle
bytes, byte size, and UTC storage time. Retrieval validates that storage binding but **MUST NOT**
perform signature, identity, transparency-log, structural, semantic, or ChangeSet verification.
The metadata is RFC 8785 canonical JSON containing exactly `version` with integer value `1`,
`changeSetDigest`, `bundleDigest`, `size`, and `storedAt`. Filesystem metadata uses
`<bundle-filename>.store.json`; Git uses the same canonical bytes followed by LF as its tag message.

Git attestation refs point to metadata tag objects whose targets are exact Bundle blobs. The first
Bundle uses the base ref. Additional Bundles use `-<log-index>` when available, add the Bundle
digest when that locator collides, or use `-sha256-<bundle-digest>` when no usable log index exists.
No `refs/tags/`, notes, branch, index, HEAD, or working-tree state is modified. Publishing a ref to
a remote is an explicit non-force operation and is never part of local storage.

Filesystem storage writes exact Bundle files as `<digest>.sigstore.json` and then
`<digest>.<n>.sigstore.json`, with hash-bound companion metadata in the same configured directory.
Bundle and metadata publication is create-only and atomic to cooperating store operations.

OCI storage requires an explicitly supplied immutable subject descriptor containing media type,
manifest digest, and byte size. It attaches an OCI image manifest using the OCI 1.1 subject and
Referrers API. The artifact type and sole Bundle layer media type are
`application/vnd.dev.sigstore.bundle.v0.3+json`. Manifest annotations bind the ChangeSet Digest,
Bundle digest, and storage time as defined by `ADR-043`. Mutable subject tags **MUST NOT** be
resolved implicitly.

---

## 10. Error codes

Defined per `GLOSS-001 §6`. Verification codes are enumerated in §8. Full per-feature error
tables are in the BRDs.

---

## 11. JSON Schema

The authoritative machine-readable **structural** schema **MUST** be generated from the
implementation's Pydantic models and published at
`spec/schemas/ai-authorship-v0.1.schema.json`.

Generation, not hand-authoring, is required so the schema and the implementation cannot drift.
The CI pipeline **MUST** fail if the committed schema differs from the generated one
(`QA-001 §5`).

The schema governs required fields, types, shapes, enumerations, patterns, cardinality, and unknown
field rejection. It does not supersede semantic invariants elsewhere in this specification.
Cross-field equality, including the subject/predicate digest invariant, **MUST** be enforced by
runtime validators and verification step 5 (`ADR-021`).

The reference `generate_json_schema(predicate_version)` function produces the complete structural
schema for a `Statement`. `predicate_version` **MUST** be the exact string `0.1`. Any other value
**MUST** fail with `ERR-BUILD-205`; version fallback or best-effort generation is prohibited.
Writing the returned schema to the repository is tooling I/O outside the pure core package and is
performed by `just schema` (`ADR-029`).

---

## 12. Test vectors (NORMATIVE)

The repository **MUST** ship, under `spec/testvectors/`, at minimum:

| Vector | Purpose |
|---|---|
| `csd1-empty` | Empty ChangeSet digest |
| `csd1-single-add` | One added file |
| `csd1-modify-delete` | Mixed operations |
| `csd1-rename` | Rename represented as delete + add |
| `csd1-mode-change` | Mode-only change |
| `csd1-unicode-paths` | Non-ASCII and non-UTF-8 paths |
| `csd1-submodule` | Gitlink entry |
| `csd1-symlink` | Symlink entry |
| `csd1-path-ordering` | Paths whose byte order differs from locale order |
| `jcs-canonical` | Canonicalisation fixtures |
| `statement-valid` | A fully-populated valid Statement |
| `statement-invalid-schema-*` | One fixture per structural validation failure; must fail JSON Schema and runtime validation |
| `statement-invalid-semantic-*` | One fixture per semantic invariant; may pass JSON Schema but must fail runtime and verifier semantic validation |

Each vector is a directory containing inputs and the expected digest or outcome. Any second
implementation must pass these unchanged. **These vectors are the definition of correctness.**

---

## 13. Known agent identifier registry (informative)

Non-normative. Unknown values are permitted; this exists only to encourage consistency.

| `agent.name` | Harness |
|---|---|
| `claude-code` | Claude Code |
| `cursor` | Cursor |
| `github-copilot` | GitHub Copilot |
| `codex-cli` | OpenAI Codex CLI |
| `gemini-cli` | Gemini CLI |
| `aider` | Aider |
| `cline` | Cline |
| `human` | Explicitly human-authored |

---

## 14. Security considerations

Full treatment in `SEC-001`. Summary:

- Authorship claims are **self-reported and forgeable**. The format's guarantee is integrity of
  the record, not truth of its contents.
- Prompt text is excluded by default because prompts routinely contain secrets, customer data,
  and personal data.
- Attestation **absence** is the easiest attack. Absence is only meaningful if a required CI
  check enforces presence — the policy gate, not the format, provides that property.
- The transparency log makes suppression detectable but does not prevent it.

---

## 15. Change log

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-07-25 | Initial draft |
| 0.1.0 | 2026-07-25 | URI stability (`ADR-013`), offline inclusion proof (`ADR-015`), git-ref storage (`ADR-014`) folded in before first publication |
| 0.1.0 | 2026-09-10 | Canonical percent-encoded Git paths adopted before first publication (`ADR-018`) |
| 0.1.0 | 2026-09-10 | Commit identities removed from the ChangeSet Digest before first publication (`ADR-019`) |
| 0.1.0 | 2026-09-10 | DSSE and bundle handling delegated to Sigstore-native APIs; bundle and atomic verification semantics corrected before first publication (`ADR-020`) |
| 0.1.0 | 2026-09-10 | Structural JSON Schema and runtime semantic validation contracts separated before first publication (`ADR-021`) |
| 0.1.0 | 2026-09-11 | Nested wire shapes, digest encoding, protocol-key exceptions, and schema-version handling completed before first implementation (`ADR-029`) |
| 0.1.0 | 2026-09-12 | Collector-generated identifiers and complete authorship-mode edge cases defined before F-03 implementation (`ADR-035`) |
| 0.1.0 | 2026-09-12 | Builder purity, environment trust classification, and total array ordering completed before F-05 implementation (`ADR-036`) |
| 0.1.3 | 2026-09-13 | Effective human-review state made mandatory for new output and optional only for historical v0.1 verification so policy can enforce separation of duties without breaking signed bundles (`ADR-042`) |
| 0.1.4 | 2026-09-14 | Git, filesystem, and OCI storage formats, metadata binding, discovery, and verification separation completed before F-07 implementation (`ADR-043`) |
| 0.1.5 | 2026-09-14 | Additional Git attestation locators changed from impossible child refs to coexisting sibling refs after executable Git and libgit2 probes (`ADR-044`) |

[in-toto Statements]: https://in-toto.io/
