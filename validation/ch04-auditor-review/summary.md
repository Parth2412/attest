# CH-04 Mock Evidence Bundle

> **DRAFT — PRACTITIONER REVIEW REQUIRED**
>
> This is a deliberately hand-built mock for the `CH-04` validation experiment. No framework
> mapping in this directory has been reviewed by a qualified practitioner. It is not customer-ready,
> is not an audit conclusion, and must not be presented as evidence that a control is satisfied.
>
> The files under `policy-exceptions/` are synthetic and unsigned. They validate a proposed
> lifecycle shape only and must not be represented as real or cryptographically verified events.

## Review purpose

This mock asks practising auditors whether attest's evidence shape is usable as change-management
evidence for AI-assisted code changes. It contains five real Sigstore Bundles produced by the public
[`Parth2412/attest-action-proof`](https://github.com/Parth2412/attest-action-proof) repository.
The sample includes two before/after review transitions and one later approved ChangeSet. It also
contains synthetic open, overdue, and closed policy-exception lifecycles proposed by `ADR-070`.

Please read the candidate narrative in `controls/change-management.md`, run `verify.sh`, inspect the
raw Bundles in `attestations/`, and answer the questions in `feedback.md`.

## Sample inventory

| Bundle SHA-256 prefix | Collected (UTC) | ChangeSet Digest prefix | Authorship mode | Review state | Workflow run / attempt |
|---|---|---|---|---|---|
| `e39d6cb916ca` | 2026-09-24 12:00:15 | `7356fbb663dc` | `human-authored` | `none` | `35996154567` / 2 |
| `e60df59e1a27` | 2026-09-24 12:16:02 | `7356fbb663dc` | `human-authored` | `approved` | `35996154567` / 3 |
| `1e43cd876d32` | 2026-10-15 12:31:54 | `ed8d845eebb4` | `human-authored` | `approved` | `38711403197` / 3 |
| `ef80b71e6031` | 2026-10-16 07:52:34 | `9b369576434d` | `ai-authored` | `none` | `38869963939` / 1 |
| `7a6a5ec34871` | 2026-10-16 08:45:28 | `9b369576434d` | `ai-authored` | `approved` | `38869963939` / 2 |

The `ai-authored` pair contains one self-reported `codex-cli` Authorship Claim scoped to the two
paths in that ChangeSet. The paired Bundles show that review evidence can change while the
ChangeSet Digest remains stable.

## Synthetic Policy Exception Record lifecycle

The lifecycle examples are evaluated against the fixed mock generation timestamp
`2026-10-16T08:50:23Z`.

| Exception | Authorization | Review deadline | Closure | Derived state |
|---|---|---|---|---|
| `validation-exception-001` | `policy-exceptions/validation-exception-001-authorized.json` | `2026-10-16T12:00:00Z` | `policy-exceptions/validation-exception-001-reviewed.json` | `closed` |
| `validation-exception-002` | `policy-exceptions/validation-exception-002-authorized.json` | `2026-10-16T08:00:00Z` | none | `overdue` |
| `validation-exception-003` | `policy-exceptions/validation-exception-003-authorized.json` | `2026-10-17T08:30:00Z` | none | `open` |

The closed example links its retrospective-review event to the exact authorization-file digest
and to the real approved Bundle for the same ChangeSet. The original authorization remains
unchanged. The overdue example remains outstanding even though a deployment could have succeeded;
the open example shows an obligation whose deadline has not elapsed.

The shape asks practitioners whether a future signed record preserves the required Decision
Owner, reason, separation-of-duties facts, deadline, later reviewer, disposition, and remediation
evidence. The placeholder identities and inner source/Decision digests are deliberately synthetic.
Only the file digests indexed by `manifest.json` are computed from real bytes.

## Independent verification

Prerequisites:

- Docker with access to `ghcr.io`
- `bash`, `jq`, and `sha256sum`

Run:

```console
./verify.sh
```

The script first checks every indexed file digest. It then runs attest CLI `0.1.4` from the
immutable production image
`ghcr.io/parth2412/attest@sha256:6e1656ab5da1d5abc43c0ec36e6f3010f1f52c2528ff0e868eb2f62b5754906a`
with container networking disabled. For each Bundle it requires the exact workflow identity and
issuer, validates the embedded transparency-log evidence, checks the Statement model, and checks
the expected ChangeSet Digest, authorship mode, review state, run, and attempt.

`verify.sh` does not cryptographically verify the synthetic Policy Exception Records. No public
predicate or verifier for that record exists. Their `integrityStatus` remains
`synthetic-unsigned-validation-only`, including after the file-digest check succeeds.

The mock does not include repository source. Consequently, `verify.sh` requires
`changeset-recomputation` to report `skipped`; it does not claim to recompute a ChangeSet from Git
objects. The source repository and full commit identifiers remain named inside each signed
Statement for a separate replay by an authorised reviewer.

## Exceptions and scope boundary

This is a curated five-Bundle sample, not an exhaustive export of every change in a reporting
period. It therefore cannot identify every unattested change in the date range. No input Bundle was
excluded for a verification failure while assembling this mock. Those evidence failures are a
different collection from the three synthetic authorized policy exceptions and are not resolved
by them.

The approved `CH-04` Bundle records the earlier failed `attest` check visible when attempt 2 began;
a running job cannot include its own future terminal state. GitHub run `38869963939`, attempt 2,
completed successfully. This distinction is intentionally exposed for practitioner feedback.

## Limitations

- Authorship Claims are self-reported. A valid signature establishes integrity and Signing
  Identity; it does not independently establish that an Authorship Claim is true.
- Three sample Bundles are `human-authored` and contain no Authorship Claims. They remain useful for
  evaluating ChangeSet and Review Record presentation, but do not exercise AI claim collection.
- A Review Record establishes what the forge reported at collection time. It does not establish
  review quality, software correctness, security, or satisfaction of a framework control.
- The raw Bundles carry Sigstore verification material. `manifest.json` is an unsigned convenience
  index and intentionally excludes itself from its own file-digest list to avoid a circular digest.
- Policy Exception Record examples are unsigned synthetic data. Their candidate field names,
  placeholder identities, and placeholder inner digests are not a public format and may change
  after practitioner review.
- The mock does not enforce what happens when retrospective review is overdue. Whether a later
  release is blocked, escalated, or both remains a practitioner question and future Policy choice.
- No customer source code is included. Paths, commit identifiers, digests, and evidence metadata
  remain visible and may still be sensitive in a private deployment.
- The candidate control narrative has no control identifier or authoritative control-text citation;
  obtaining those from practitioners is an explicit outcome of this experiment.
