# attest — Architecture Decision Log

| Field | Value |
|---|---|
| Document ID | `ADR-LOG` |
| Version | `1.9.0` |
| Status | **NORMATIVE** for recorded decisions |
| Last updated | 2026-09-11 |

> **Purpose.** Every non-obvious decision is recorded with its rationale and its rejected
> alternatives. This exists so that six months from now — or when an implementation agent
> proposes "a simpler approach" — the reasoning is available and the decision does not get
> silently reversed.
>
> **Rule:** changing a normative document requires a new ADR. ADRs are append-only; they are
> superseded, never edited.

---

## ADR-001 — Digest git object identities, not diff text

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `SPEC-001 §5`

**Context.** The attestation must bind to "what changed". The obvious approach is to hash the
unified diff.

**Decision.** `CSD-1` digests a canonicalised, path-sorted list of `(path, changeType, oldMode,
newMode, oldBlob, newBlob)` entries derived from git tree comparison, with rename and copy
detection disabled.

**Rationale.** Rendered diff text is a function of the diff algorithm, context width, whitespace
flags, rename heuristics, and renderer version. None are stable across tools or across years.
Blob OIDs are content-addressed and reproducible by any git implementation, forever. Audit
evidence that stops reproducing is worthless.

**Rejected alternatives.**
- *Hash the unified diff* — non-reproducible.
- *Hash the head tree* — would attest the whole repository state, not the change; every
  attestation would differ for unrelated reasons.
- *Use the head commit SHA as subject* — breaks under squash-merge and rebase, which is the
  dominant merge workflow.

**Consequences.** Renames appear as delete + add. Line-level statistics cannot be part of the
signed record. Both are acceptable; the second is arguably a feature (see `SPEC-001 §6.2`).

---

## ADR-002 — Subject is the ChangeSet Digest, not the commit SHA

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `SPEC-001 §3.2`

**Context.** in-toto subjects usually name an artifact. What is the artifact for a code change?

**Decision.** `subject[0].name = "changeset"`, digest = ChangeSet Digest. The head commit is
recorded inside the predicate for traceability but is not the binding anchor.

**Rationale.** Squash-merge rewrites commit SHAs. If the SHA were the subject, every attestation
created at PR time would become unverifiable the moment the PR merged — which is precisely when
the evidence becomes valuable.

**Consequences.** Retrieval is keyed on the digest, so the storage layer must map digest →
attestations. Multiple attestations per digest are legitimate and must be supported.

---

## ADR-003 — Attest claims; never detect

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** everything

**Context.** Users will ask for "what percentage of our code is AI-written". Statistical
detection is the obvious feature.

**Decision.** attest records self-reported claims and their provenance. It performs no
statistical inference about authorship, and no document, error message, or marketing sentence may
imply otherwise.

**Rationale.** Three reasons, any one sufficient. (1) AI-code detection is unreliable and its
false-positive behaviour is unacceptable in an audit context. (2) Asserting a defensible-sounding
falsehood in a signed, non-repudiable record creates legal exposure for the customer and for us.
(3) The honest, narrow claim is *more* defensible commercially, because it is the claim an
auditor can actually rely on.

**Consequences.** Unclaimed AI use is invisible to attest. This is a real, stated limitation, not
a bug. Coverage comes from making claim emission easy and from policy requiring claims.

---

## ADR-004 — Identity verification is mandatory and cannot be bypassed

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `SPEC-001 §8.1`, `F-08`

**Context.** Sigstore verification can check a signature without constraining the signer's
identity. Many tools ship this way for convenience.

**Decision.** Verification requires an expected identity pattern and issuer. No default accepts
any identity. No flag skips the check while reporting success. Unconstrained verification is
reported as `unverified-identity`.

**Rationale.** Anyone can obtain a Fulcio certificate. Signature-only verification proves only
that *someone* signed, which is worth nothing. This check is the difference between a security
product and security theatre.

**Consequences.** Slightly worse first-run ergonomics. `attest init` mitigates by generating the
correct identity constraint for the repository's workflow.

---

## ADR-005 — The signer re-verifies its own output before reporting success

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `ARCH-001 §4` step 10

**Context.** Signing bugs, canonicalisation drift, and clock skew produce attestations that
verify at creation but fail later.

**Decision.** `attest run` runs the full verification pipeline against the bundle it just
produced, before exiting successfully.

**Rationale.** The failure mode we must never have is discovering at audit time that a year of
attestations are invalid. Paying a small cost per run to eliminate that class of failure is
obviously correct.

**Consequences.** ~1–2s added per run. Accepted.

---

## ADR-006 — File-drop sidecar protocol for authorship claims

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `ARCH-001 §7`, `F-03`

**Context.** Claims must be collected from many different agent harnesses.

**Decision.** Harnesses write JSON files to `.attest/claims.d/`. attest also reads commit
trailers and Git Notes for compatibility with existing conventions.

**Rationale.** A file-drop requires no vendor cooperation, no API, no auth, no network. It works
with any tool capable of writing a file, including ones that do not exist yet. Vendor-neutrality
is the strategic moat; a protocol requiring vendor partnership would forfeit it.

**Consequences.** Claims are trivially forgeable. Accepted and explicit — see `ADR-003` and
`SEC-001 T-01`.

---

## ADR-007 — Dual git backend from day one

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `F-02`, `TECH-001 §3.1`

**Context.** `pygit2` is the correct library but requires compiled libgit2, which can complicate
installation on some platforms.

**Decision.** Define a `GitBackend` protocol with two implementations — `pygit2` (default) and
`subprocess` (fallback) — both required to pass the same `spec/testvectors/` conformance suite.

**Rationale.** Retrofitting an abstraction after the codebase assumes one library is expensive.
Building it first costs little and de-risks the primary install-failure mode. The shared vector
suite guarantees the two backends cannot diverge silently.

**Consequences.** Slightly more code in `attest-collect`. Worth it.

---

## ADR-008 — Policy language is declarative and closed

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `F-09`

**Context.** Policy engines often embed a scripting language (Rego, Lua, CEL, Python) for
flexibility.

**Decision.** A fixed, declarative YAML vocabulary. No embedded execution.

**Rationale.** The gate runs in a CI job that holds `id-token: write`. Arbitrary code execution
in that job is a supply-chain vulnerability. A closed vocabulary is also statically analysable,
diffable in review, and comprehensible to the compliance staff who will actually read it.

**Consequences.** Some exotic policies will be unexpressible. That is the intended trade.
Requests for scripting are answered by extending the vocabulary, with a new ADR.

---

## ADR-009 — No blockchain anchoring

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** architecture

**Context.** The founder has deep blockchain expertise; anchoring attestations on-chain is an
obvious-seeming idea.

**Decision.** Attestations are recorded in Rekor. No blockchain component.

**Rationale.** Rekor is already an append-only Merkle transparency log with inclusion proofs and
signed tree heads — the exact property anchoring would provide. Adding a chain would introduce
cost, latency, key management, and operational burden with no additional security property, and
would damage credibility with the security-engineering audience this product must win.

**Consequences.** The blockchain background remains an asset — as fluency in verifiable data
structures and as the basis for the future Solidity provenance plug-in (`OOS-04`) — not as an
architectural component.

---

## ADR-010 — Generated JSON Schema, never hand-authored

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `SPEC-001 §11`, CI

**Context.** The specification needs a machine-readable schema.

**Decision.** Generate it from Pydantic models. CI fails if the committed schema differs from the
regenerated one.

**Rationale.** Hand-authored schemas drift from implementations, guaranteed. Since the
specification is the strategic asset, drift between spec and implementation is the single most
damaging quality failure available to this project.

**Consequences.** Pydantic model structure is constrained by what must appear in the schema. Field
aliases and strict configuration must be maintained carefully.

---

## ADR-011 — Verifier port to a static binary is deferred, with a single bounded trigger

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `TECH-001 §1.3`

**Context.** Python cannot ship a single static binary easily. An earlier draft left this as an
open musing about a possible v2 Go rewrite, which is exactly the kind of unresolved hedge that
causes drift.

**Decision.** No port. The container image plus the GitHub Action is the distribution mechanism
for v1.0 and v1.1. Exactly one trigger may reopen this: **if, at the M2 exit gate, installation
or runtime friction is the top-ranked complaint from a majority of design partners, the
verifier — and only the verifier — is reimplemented as a static Go binary, recorded then as a new
ADR.** No other condition reopens it. Nobody may begin such a port speculatively.

**Rejected alternatives.** PyInstaller/Nuitka bundling now (adds build complexity before any
evidence of need); rewriting the whole tool (throws away the signer and spec work).

**Consequences.** Distribution friction is accepted as a known cost until measured.

---

## ADR-012 — Implementation language is Python; this is final for v1.x

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `TECH-001`, all packages

**Context.** Two defensible options existed. TypeScript favours founder velocity, native
JavaScript GitHub Actions, `npx` reach, and a Sigstore client proven at npm-provenance scale.
Python favours proximity to the in-toto and TUF reference implementations, a first-party Sigstore
client, and Pydantic-generated schemas. Documentation briefly carried both positions, which is a
defect under `MPD-001 §12`.

**Decision.** **Python 3.12+. Final for the v1.x line.** No further comparison, no dual-stack, no
partial port other than the single bounded trigger in `ADR-011`.

**Rationale.** The decision is the project owner's stated requirement, and it is defensible on
the merits: the strategic asset is `SPEC-001`, and being in the same language as the in-toto and
TUF reference implementations is a real advantage for a project whose plan depends on standards
adoption. The velocity cost is mitigated by a small pure core, `mypy --strict`, and mature
libraries.

**Rejected alternative.** TypeScript. Its strongest argument — a native JS Action with faster
cold start — is mitigated by container layer caching and measured against `REQ-F11-100`. Its
second argument, founder familiarity, is mitigated by strict typing and normative test vectors.

**Consequences.** Distribution is container-first (`TECH-001 §8`). Any document, comment, or
agent suggestion proposing a language change is out of scope and must be rejected without
discussion.

---

## ADR-013 — Predicate type URI scheme and stability window (closes OQ-01)

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `SPEC-001 §3.1`

**Context.** The predicate type URI is the public identifier of the format. It must be under a
domain the project provably controls, but a domain may not be owned on day one, and blocking on
a purchase would block `F-01`.

**Decision.**
1. All `v0.x` predicate type URIs are **explicitly unstable** and may change without a MAJOR
   bump. This is stated normatively in `SPEC-001 §3.1`.
2. Until a project-controlled domain is registered, the URI is derived from the GitHub
   organisation, which is provably controlled:
   `https://<org>.github.io/attest/ai-authorship/v0.1`
3. The URI **MUST** be a single constant in `attest_core`, never a literal at a call site
   (`REQ-F05-040`), so the change is a one-line edit.
4. The URI **freezes permanently at v1.0**. From v1.0 onward, any change requires a new MAJOR
   URI and permanent verification support for the old one.

**Rejected alternatives.** Blocking `F-01` on a domain purchase; using a domain not yet owned
(publishing an identifier you do not control is a hijack risk).

**Consequences.** Early adopters must be told v0.x identifiers are unstable. This is stated in the
README and in verification output for v0.x predicates.

---

## ADR-014 — Attestation storage uses a dedicated git ref namespace (closes OQ-02)

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `SPEC-001 §9`, `BRD-F07`

**Context.** Two in-repository options: git notes, or a dedicated ref namespace.

**Decision.** `refs/attestations/<changeset-digest>`, one ref per attestation. Git notes are
**not** used for storage.

**Rationale.** Git notes concentrate all entries under a single ref, which produces merge
conflicts when parallel CI jobs write concurrently — a routine condition in a busy repository and
the exact failure mode `REQ-F07-100` forbids. Independent refs are conflict-free by construction:
concurrent writers touch different refs. Multiple attestations per digest are supported by
suffixing (`refs/attestations/<digest>/<log-index>`).

Note this is storage only. attest still **reads** git notes as a claim source for Git AI
interoperability (`BRD-F03`); that is unaffected.

**Rejected alternatives.** Git notes (concurrency); a committed directory in the working tree
(pollutes the tree, changes the ChangeSet being attested — circular).

**Consequences.** Refs must be pushed explicitly (`REQ-F07-040`) and require `contents: write`.
Fetching attestations requires an explicit refspec, documented in the quickstart.

---

## ADR-015 — Transparency log inclusion proof is embedded and verified offline (closes OQ-03)

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `SPEC-001 §8`, `BRD-F08`

**Context.** Inclusion in the transparency log can be checked by querying the log at verification
time, or by embedding the inclusion proof in the bundle at signing time.

**Decision.** The inclusion proof and signed entry timestamp **MUST** be embedded in the bundle at
signing time. Verification **MUST** verify the proof cryptographically from bundle contents alone.
Querying the log at verification time is **not** an accepted substitute, and no configuration may
make verification depend on log availability.

**Rationale.** `O6`/`REQ-F08-080` require offline verification. An auditor verifying evidence in
three years must not depend on a service being reachable, or on the log operator's continued
existence. Embedding also removes a network dependency from the audit path entirely.

**Rejected alternatives.** Online-only checking (breaks offline verification); optional embedding
(produces two classes of attestation, and the weaker one would silently dominate).

**Consequences.** Signing fails if the log entry cannot be obtained (`REQ-F06-060`) — accepted
deliberately, because a bundle without a proof is not the product.

---

## ADR-016 — Control mappings ship as draft until reviewed; building is unblocked (closes OQ-04)

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** `BRD-F12`

**Context.** Control identifier mappings need a practising auditor's review. Waiting for that
before writing any `F-12` code blocks the milestone; guessing and publishing is dishonest.

**Decision.** Separate **building** from **publishing**.
1. `F-12` is unblocked for implementation immediately. Mapping files carry mandatory metadata:
   `status: draft-unreviewed`, `reviewedBy: null`, `reviewedAt: null`.
2. Any export generated from a `draft-unreviewed` mapping **MUST** carry a prominent banner in
   `summary.md` and `manifest.json` stating the mapping has not been reviewed by a qualified
   practitioner.
3. A mapping **MUST NOT** be marked `status: reviewed` without a named reviewer and date.
4. `F-12` cannot pass its Definition of Done, and no export may be presented to a customer as
   audit evidence, until at least one framework mapping is `reviewed`.

**Rationale.** The engineering work — bundle structure, verification-during-export, `verify.sh`,
exceptions reporting — is independent of which control IDs are cited. Only the mapping content
needs expertise. Separating them removes the block without permitting a false claim.

**Rejected alternatives.** Blocking all `F-12` work (wastes weeks); guessing mappings and shipping
them unlabelled (violates `GLOSS-001 §2.2`).

**Consequences.** The draft banner must be genuinely prominent and must not be suppressible by a
flag.

---

## ADR-017 — Licensing: Apache-2.0 for code, CC-BY-4.0 for the specification (closes OQ-05)

**Status:** Accepted · **Date:** 2026-07-25 · **Affects:** repository root, `spec/`

**Decision.** All code is **Apache-2.0**. `SPEC-001` and the test vectors are **CC-BY-4.0**.

**Rationale.** Apache-2.0 carries an explicit patent grant, which enterprise legal review expects
from security tooling and which MIT lacks — this matters for the compliance-driven buyer. CC-BY-4.0
is the conventional licence for a specification intended for independent implementation, and it
signals that reimplementation is invited, which is the entire adoption strategy. A copyleft or
source-available licence would deter both the enterprise buyer and the second implementer.

**Rejected alternatives.** MIT (no patent grant); AGPL or BSL (kills the standards play and
enterprise adoption); a single licence for both (code and specification have different reuse
needs).

**Consequences.** Anyone may build a competing implementation. That is intended: a specification
with one implementation is not a standard.

---

## ADR-018 — Git paths use canonical percent encoding

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `GLOSS-001 §8`, `SPEC-001 §§4–6`,
`BRD-F01`, `BRD-F02`, `BRD-F03`, `CH-01`

**Context.** Git pathnames are byte strings and may contain sequences that are not valid UTF-8.
`CSD-1` originally required implementations to decode those bytes with `surrogateescape` and
place the resulting string in the ChangeSet Record. RFC 8785 requires I-JSON strings and rejects
lone surrogate code points, so that representation cannot be canonicalised as required. The
conflict was reproduced with `rfc8785==0.1.4`, which raises `CanonicalizationError` for a
surrogate-escaped byte.

**Decision.** Every Git path carried in a signed or digested field **MUST** use one canonical,
reversible ASCII representation derived from the raw Git path bytes:

- ASCII letters, digits, `-`, `.`, `_`, `~`, and path separator `/` are emitted unchanged.
- Every other byte, including `%` and every byte at or above `0x80`, is emitted as `%HH`, using
  uppercase hexadecimal digits.
- Implementations **MUST NOT** apply Unicode decoding, case folding, locale collation, or Unicode
  normalisation before encoding.
- Entry ordering remains unsigned lexicographic ordering of the original raw path bytes, not of
  the encoded strings.
- Decoders **MUST** reject malformed escapes and non-canonical spellings, including lowercase
  hexadecimal escapes and percent-encoding of bytes from the unchanged set.
- Claim-scope paths and ChangeSet paths use this same representation. Path comparison is over
  decoded raw bytes.
- Human-facing renderers **MAY** decode valid UTF-8 for display, but display text is never used
  for digesting or path comparison. Invalid bytes remain visibly escaped.

`CSD-1` retains its identifier because the predicate and digest algorithm have not yet been
published and no attestations have been emitted.

**Rationale.** The representation covers every Git pathname, round-trips byte-identically,
contains only RFC 8785-compatible ASCII, has one spelling per byte sequence, and is implementable
without platform or language-specific Unicode behaviour. Preserving `/` keeps repository-relative
paths legible while encoding `%` prevents ambiguity.

**Rejected alternatives.**

- *Continue using `surrogateescape` in JSON* — lone surrogates are outside I-JSON and RFC 8785.
- *Reject non-UTF-8 paths* — valid Git history would become unattestable.
- *Use WTF-8* — not RFC 8785-compatible and poorly interoperable.
- *Base64-encode paths* — reversible but needlessly destroys path readability and separators.
- *Encode only invalid UTF-8 sequences* — introduces Unicode decoding and normalisation hazards
  and makes canonical-form validation more complex.

**Consequences.** Non-ASCII path bytes are escaped in signed data even when they form valid UTF-8.
Presentation layers must render paths separately when human-readable Unicode is desired. Test
vectors must cover percent signs, valid multibyte UTF-8, invalid bytes, canonical-form rejection,
and cases where encoded-string order differs from raw-byte order. `CH-01` remains open until its
full cross-repository and cross-OS experiment passes.

---

## ADR-019 — ChangeSet digests exclude commit identities

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `SPEC-001 §§3.2, 5, 6.2`,
`BRD-F01`, `CH-01`

**Context.** `CSD-1` promises that an unchanged set of path, mode, and blob transitions remains
stable across rebase and squash merge. The original ChangeSet Record also contained `baseCommit`
and `headCommit`, making that promise mathematically impossible because those identities change
during both operations. The defect was reproduced against a real squash-merged pull request:
all eight entry transitions were identical before and after the squash, while the two digests
differed solely because `headCommit` changed.

**Decision.** The canonical ChangeSet Record contains exactly `algorithm` and the sorted `entries`
array. `baseCommit` and `headCommit` remain required inputs for computing the tree difference but
**MUST NOT** be included in the ChangeSet Record or ChangeSet Digest. `baseCommit`, `headCommit`,
and optional `mergeBase` remain required or conditionally required fields of signed
`Predicate.changeSet` metadata. A verifier supplied with a repository recomputes entries from
those signed commit identities and hashes the commit-independent ChangeSet Record.

Two computations with byte-identical sorted entry transitions therefore produce the same
ChangeSet Digest even when their commit identities differ. This equivalence is intentional: a
ChangeSet identifies what changed, while the signed predicate records where and when that change
was observed.

`CSD-1` retains its identifier because it has not been published and no attestations have been
emitted.

**Rationale.** Path, mode, and old/new object identities completely describe the file-level
transition being attested. Commit identities provide valuable provenance but are contextual
metadata, not part of the change itself. Keeping them inside the signed predicate preserves their
integrity without making the subject unstable under normal forge workflows.

**Rejected alternatives.**

- *Keep commit identities in the digest* — directly fails the required squash/rebase stability.
- *Digest base and head tree identities* — unrelated repository changes alter whole-tree IDs and
  therefore preserve the same defect.
- *Rewrite commit identities after merge* — invalidates the original signature and is
  forge-specific.
- *Introduce `CSD-2`* — unnecessary before the first publication or emitted attestation.

**Consequences.** Identical transitions in different commit contexts intentionally share a
digest, and an empty ChangeSet has one universal `CSD-1` digest. Storage already supports multiple
bundles per digest. Consumers needing commit or repository context must read and verify the signed
predicate rather than infer context from the subject digest alone. Conformance vectors must prove
rebase and squash stability while also proving sensitivity to every entry field.

---

## ADR-020 — Delegate DSSE and bundle verification to Sigstore

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `SPEC-001 §§7–8`, `ARCH-001`,
`TECH-001`, `BRD-F06`, `BRD-F08`, `BOOT-001`, `CH-02`

**Context.** Executed validation against `sigstore` 4.5.0 found that a DSSE envelope produced by
Sigstore does not interoperate with direct `securesystemslib` envelope handling: Sigstore's bundle
signature omits the `keyid` field that the `securesystemslib` envelope model requires. The supported
Sigstore API successfully signed and verified the exact canonical payload through `sign_dsse` and
`verify_dsse`, including mandatory identity and issuer policy, Rekor v2 inclusion proof, and offline
verification. The same validation showed that the current keyless bundle contains the leaf signing
certificate in `verificationMaterial.certificate`; the chain to Fulcio is supplied by the configured
trusted root rather than embedded as a certificate chain.

Sigstore's public verifier establishes certificate path and time validity, identity policy,
transparency evidence, DSSE signature, and log-entry consistency as one operation. It raises a
generic `VerificationError` rather than a stable typed cause for each internal subcheck. Pretending
the reference implementation can reliably report six distinct cryptographic failure codes would
require parsing exception text or duplicating Sigstore internals.

**Decision.** The Python reference implementation **MUST**:

- construct `sigstore.dsse.Statement` from the exact RFC 8785 canonical Statement bytes;
- create one Sigstore signer context per attestation and call `sign_dsse`, delegating PAE,
  envelope construction, signing, Rekor submission, and bundle construction to Sigstore;
- call `Verifier.verify_dsse` with a mandatory Sigstore `Identity` policy containing the caller's
  expected identity and issuer, then assert the returned payload type and payload bytes before
  parsing application data;
- use the default in-memory ephemeral-key retention within that single signer context. It
  **MUST NOT** use `cache=False` with `sigstore` 4.5.0 and **MUST NOT** persist private key material;
- depend directly on `sigstore`, not `securesystemslib`. A transitive installation does not permit
  direct imports or direct envelope manipulation.

The required bundle verification material is the DSSE envelope, the leaf signing certificate,
the transparency-log entry and inclusion proof, and any timestamp verification material emitted
by Sigstore. The configured and pinned trusted root supplies the certificate chain.

The verifier treats Sigstore's cryptographic verification as one fail-closed check. Because the
public API exposes no stable typed failure cause, any `VerificationError` from that operation maps
to `ERR-VERIFY-013`; it **MUST NOT** be classified by matching exception text. Earlier draft codes
`ERR-VERIFY-002` through `ERR-VERIFY-006` are retired before first publication and were never
emitted. Bundle parsing, payload-type/Statement parsing, schema validation, semantic validation,
and optional local ChangeSet recomputation retain distinct codes.

**Rationale.** One supported cryptographic boundary is safer and more maintainable than adapting
two incompatible envelope models or reimplementing verification internals. A generic, stable error
code is more accurate than brittle diagnostic precision derived from undocumented messages.

**Rejected alternatives.**

- *Inject a `keyid` and continue through `securesystemslib`* — mutates or reconstructs an upstream
  bundle and creates two envelope authorities.
- *Hand-construct PAE or DSSE JSON* — duplicates security-sensitive upstream logic.
- *Use Sigstore private verification methods to retain granular codes* — binds correctness to an
  unsupported API and still cannot provide stable typed causes.
- *Parse `VerificationError` text* — undocumented text is not a machine contract.
- *Require an embedded certificate chain* — contradicts the verified Sigstore bundle shape.

**Consequences.** `attest-sign` has one fewer direct dependency and one upstream authority for
DSSE and bundles. Cryptographic failures share `ERR-VERIFY-013`, while human diagnostics may include
a sanitised upstream message. Any Sigstore upgrade must re-run `CH-02`-equivalent conformance before
the adapter changes. The exact validated version must be pinned during bootstrap before feature
implementation.

---

## ADR-021 — Separate structural schema from semantic invariants

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `SPEC-001 §§2, 8, 11–12`,
`BRD-F01`, `BRD-F08`, `QA-001`, `BOOT-001`, `CH-02`

**Context.** Executed validation with Pydantic 2.13.5 and jsonschema 4.26.0 proved that the generated
JSON Schema accepts a Statement whose `subject[0].digest.sha256` differs from
`predicate.changeSet.digest`, while Pydantic's runtime model validator rejects it. Standard JSON
Schema cannot express this equality between two nested instance values. The previous acceptance
criterion incorrectly required every runtime-invalid Statement to be rejected by the generated
schema.

**Decision.** The generated Pydantic JSON Schema is authoritative for representable structural
constraints only: required fields, types, shapes, enumerations, patterns, cardinality, and unknown
field rejection. Cross-field equality and any other invariant that cannot be expressed faithfully
in the generated schema **MUST** be enforced by Pydantic runtime model validators during building
and by an explicit semantic step during verification. Runtime validation **MUST NOT** be weakened
to match the schema's lower expressive power.

Normative vectors are split into two classes:

- `statement-invalid-schema-*` **MUST** fail both JSON Schema and runtime model validation;
- `statement-invalid-semantic-*` **MAY** pass JSON Schema but **MUST** fail runtime model validation
  and the corresponding verifier semantic step.

The verifier parses untrusted payload bytes without constructing the semantic Pydantic model,
applies the versioned structural schema, and only then performs semantic model validation. This
preserves deterministic failure ordering: structural failures map to `ERR-VERIFY-008`; the
subject/predicate digest mismatch maps to `ERR-VERIFY-009`.

**Rationale.** A generated schema cannot promise constraints its target language cannot represent.
Separating the two layers makes both contracts truthful while retaining strict runtime enforcement
and language-neutral structural interoperability.

**Rejected alternatives.**

- *Hand-edit the schema with a non-standard extension* — violates `ADR-010` and is not portable.
- *Duplicate the digest value into a schema-friendly shape* — changes the wire format solely to
  accommodate a tooling limitation.
- *Remove the runtime validator* — weakens the signed-data invariant.
- *Claim the schema rejects every invalid Statement* — contradicted by executed evidence.

**Consequences.** Consumers using only the JSON Schema achieve structural, not full, conformance;
they must implement the semantic rules in `SPEC-001`. Tests and public documentation must state
which layer rejects each invalid vector. Schema drift checking remains unchanged.

---

## ADR-022 — Make evidence export a bounded application layer

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `ARCH-001 §2`, `TECH-001 §3`,
`QA-001 §6`, `BOOT-001 §§4–5`, `COMPAT-001`

**Context.** The architecture text said that no sibling package may import another and that only
`attest-cli` composes packages. The normative dependency table and import-linter layers instead
placed `attest-export` above `attest-store` and `attest-sign`, which `BRD-F12` requires to retrieve
and verify every exported attestation. Both rules cannot hold simultaneously.

The dependency documents also disagreed about three direct dependencies:
`in-toto-attestation` appeared in `TECH-001` but not `BOOT-001`; `structlog` was assigned to every
package in `TECH-001` but only to the CLI in `BOOT-001`; and PyYAML was required for CLI YAML
configuration but was not a direct CLI dependency.

**Decision.** `attest-export` is a bounded application-service layer above the independent adapter
packages. It **MAY** import exactly `attest-core`, `attest-store`, and `attest-sign`, plus PyYAML.
The peer adapter packages `attest-collect`, `attest-sign`, `attest-store`, and `attest-policy`
**MUST NOT** import each other. `attest-cli` remains the top-level composition and presentation
root and may import every internal package.

Direct dependency ownership is:

- project-owned Pydantic models implement the in-toto Statement wire contract;
  `in-toto-attestation` is not a direct dependency;
- `structlog` is a direct dependency of `attest-cli` only;
- PyYAML is a direct dependency of `attest-policy`, `attest-export`, and `attest-cli`;
- every other assignment remains as listed in `BOOT-001 §4.1`.

**Rationale.** F-12 cannot satisfy mandatory retrieval and verification while remaining isolated
from the packages that own those operations. A narrow, enforced upper layer preserves acyclic
dependencies without pushing export orchestration or domain logic into the CLI. Direct dependency
declarations must reflect actual imports rather than relying on transitive availability.

**Rejected alternatives.**

- *Keep export isolated and perform export verification in the CLI* — moves F-12 business rules
  into a package explicitly forbidden from owning business logic.
- *Move storage and verification protocols into core solely for export* — expands the pure core
  with adapter-facing abstractions it does not otherwise need.
- *Let all packages import each other* — destroys the enforceable dependency boundary.
- *Retain unused or transitive-only direct dependencies* — increases supply-chain surface and
  makes package metadata inaccurate.

**Consequences.** The import-linter stack has four levels: CLI, export, peer adapters, core.
Documentation must use “peer adapters” rather than “all siblings” when describing isolation.
`attest-export` remains the only non-CLI package allowed to import multiple internal packages.

---

## ADR-023 — Make the zero-logic bootstrap executable

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `BOOT-001 §§2–6, 14–17`,
`QA-001`, repository scaffold

**Context.** Three bootstrap requirements were mutually impossible as written. Generated schema
files had to exist even though schema generation belongs to F-01 and hand-authoring is forbidden.
The docstring-only `schema.py` stub made `just schema` exit successfully, although the acceptance
gate required a clean “not yet implemented” failure. Finally, `just check` invoked pytest while
the prescribed tree contained no tests, causing pytest's no-tests-collected failure.

**Decision.** At bootstrap:

- `spec/schemas/` contains only `.gitkeep`; generated JSON Schema files do not exist until F-01
  creates them through the generator;
- each intentionally empty test-vector directory contains only `.gitkeep`, which is not a vector;
- `schema.py` remains a docstring-only stub, while the bootstrap `just schema` target emits a
  concise F-01 ownership message and exits non-zero without a traceback; F-01 replaces that target
  when generation is implemented;
- `packages/attest-core/tests/test_bootstrap.py` imports every workspace package as a packaging
  smoke test. It contains no feature behavior and gives pytest one meaningful bootstrap test;
- per-package metadata may change `name`, `description`, `dependencies`, and wheel path from the
  documented pattern.

**Rationale.** The scaffold's required gates must describe behavior that can actually execute.
Placeholders must not masquerade as generated normative artifacts, and a packaging smoke test is
the smallest meaningful proof that all workspace distributions install and import.

**Rejected alternatives.**

- *Commit empty `.json` schema files* — creates invalid artifacts at authoritative paths.
- *Generate schemas during bootstrap* — implements F-01 behavior before its tests and review.
- *Put executable failure logic in `schema.py`* — violates the docstring-only stub invariant and
  makes importing the module fail.
- *Accept pytest exit code 5* — contradicts the green `just check` gate.
- *Add an always-true placeholder test* — creates no useful evidence.

**Consequences.** A pre-F-01 release gate intentionally stops at `just schema`, while the normal
bootstrap `just check` passes. Generated schema paths first appear in the F-01 commit. Empty vector
directories remain trackable without claiming that normative fixtures exist.

---

## ADR-024 — Bound the banned-language allowlist

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `GLOSS-001 §2.2`, `AGENTS.md §3.7`,
`BRD-F12`, `BOOT-001 §9`

**Context.** The bootstrap checker had to scan every Markdown file under `docs/`, but its own
normative documents repeated prohibited literals outside the only permitted glossary region.
The glossary region also lacked the boundary marker required by the checker contract. A faithful
implementation therefore had to fail on the repository immediately after bootstrap.

**Decision.** The canonical banned-language table in `GLOSS-001 §2.2` and the constant table in
`scripts/check_banned_language.py` are the only exemptions. Each uses explicit paired
`# banned-language-allowlist:start` and `:end` markers. All other documents refer to the glossary
without reproducing prohibited literals. The checker fails closed on missing, nested, duplicate,
or unterminated markers and verifies that its constant table exactly matches the glossary table.

**Rationale.** A narrowly bounded, machine-checkable exception preserves both an auditable source
of truth and a repository-wide over-claiming gate. Removing duplicates prevents future drift.

**Rejected alternatives.** Exempting all normative documentation would create a broad bypass.
Silently ignoring every Markdown table would miss user-facing violations. Keeping duplicate
lists would make equality unenforceable.

**Consequences.** Prohibited literals may appear only in two marked regions. Requirements,
agent instructions, ADRs, and implementation documentation must cite `GLOSS-001 §2.2` rather
than quote the list.

---

## ADR-025 — Define lifecycle-aware pre-feature gates

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `BRD-INDEX §7`, `QA-001 §8`,
`BOOT-001 §§2, 6, 10, 12, 16`

**Context.** At bootstrap, no vector or adversarial tests exist by design. Pytest returns status
`5` when a marker selects no tests, so the prescribed local and CI gates failed even though their
owning features had not started. Separately, traceability referred to features listed as Done in
`BRD-INDEX §7`, but that section had no machine-readable feature-status registry.

**Decision.** `BRD-INDEX §7.1` is the single feature completion registry with values `Planned`,
`In progress`, and `Done`. A marker gate may translate pytest status `5` to success only when none
of its declared owning features is `Done`, and must report that it is not applicable. It propagates
all other failures. Vector tests are owned by F-01 and F-02; adversarial tests are owned by F-08.
The schema-drift CI job is not applicable until F-01 is `Done`, after which generation and drift
comparison are mandatory. The local pre-F-01 release gate still fails at `schema-check`.

**Rationale.** Applicability must follow recorded delivery state, not file-count heuristics or
false placeholder tests. The same registry now drives traceability and empty-suite behavior.

**Rejected alternatives.** Marking the import smoke test as a vector or adversarial test would
mislabel evidence. Treating every pytest status `5` as success would hide missing suites after a
feature is complete. Adding placeholder feature tests would claim behavior that does not exist.

**Consequences.** Bootstrap and intermediate-feature CI can be green without invented tests.
Changing a feature to `Done` activates its completeness gates in the same commit.

---

## ADR-026 — Align quality tooling with the monorepo layout

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `TECH-001 §5`, `QA-001 §2`,
`DEV-001 §§1–3`, `BOOT-001 §§2–7, 10, 12, 16`

**Context.** Executing the bootstrap gates exposed three tool/layout conflicts. Ruff 0.16.6
formats Python fences in Markdown and attempted to rewrite approved normative examples. Seven
required `tests/__init__.py` files made pytest and mypy treat independent test roots as duplicate
top-level `tests` packages. Bandit reported normal test assertions even though the test policy
explicitly permits them.

**Decision.** Ruff excludes `*.md` while continuing to lint and format Python implementation and
tooling files. Workspace test directories are non-package roots without `__init__.py`, and pytest
uses importlib mode. `scripts/run_mypy.py` runs strict mypy separately for every workspace package
and is the sole local, pre-commit, and CI type-check entry point. Bandit excludes
`packages/*/tests/` and scans all production modules under `packages/*/src/`.

**Rationale.** Normative Markdown must not change as a formatter side effect. Per-package type
checking preserves strict coverage without ambiguous module names. Security scanning should
evaluate shipped code; Ruff's test-specific security rules and normal test execution continue to
cover test quality.

**Rejected alternatives.** Reformatting normative examples would create specification changes
unrelated to implementation. Giving test packages invented unique names would diverge from the
documented layout. Excluding all tests from mypy would weaken type coverage. Disabling Bandit
assertion findings globally would also weaken production scanning.

**Consequences.** Quality commands have explicit ownership boundaries. Adding a workspace package
requires no central mypy list update because the runner discovers it from `packages/*/pyproject.toml`.

---

## ADR-027 — Make bootstrap CI deterministic and supply-chain pinned

**Status:** Accepted · **Date:** 2026-09-10 · **Affects:** `TECH-001 §7`, `QA-001 §12`,
`DEV-001 §3`, `SEC-001 T-09`, `BOOT-001 §§12, 16`

**Context.** The bootstrap workflow installed a requested matrix interpreter without binding uv
to it, so both matrix entries could select the same compatible Python. It also tested Linux only
despite the required Linux/macOS matrix, used mutable action tags and an unpinned uv version, let
CI resolve an unlocked environment, and did not validate integration-branch pushes.

**Decision.** CI references `actions/checkout` v7.0.1 at full commit
`3d3c42e5aac5ba805825da76410c181273ba90b1` and `astral-sh/setup-uv` v10.0.1 at full commit
`20cfd1bf945f4377ade1205e4dbc17946fc9a30d`, retaining tag comments for maintainability. setup-uv
installs uv 0.11.2 exactly. The check job covers the Cartesian product of `ubuntu-latest` and
`macos-latest` with Python 3.12 and 3.13, binds `python-version`, and asserts the selected minor
version before running gates. Non-matrix jobs bind Python 3.12. Every CI install uses
`uv sync --locked --all-packages`. CI runs for pull requests and pushes to `dev` and `main`.
Updating an action or uv pin requires a deliberate PR that verifies the upstream release and full
commit SHA.

**Rationale.** A green matrix is evidence only when each cell proves the runtime it names. Locked
dependencies and immutable action references make the executed toolchain reproducible and reduce
workflow supply-chain exposure. Testing `dev` after merge validates the actual integration commit,
not only its pull-request head.

**Rejected alternatives.** Installing a version without selecting it leaves interpreter choice
ambiguous. Mutable major-version tags and an implicit latest uv permit unaudited code changes.
Linux-only execution contradicts the stated support matrix. Testing pull requests and `main` only
leaves integration-branch merge commits without post-merge evidence.

**Consequences.** The check job expands from two Linux cells to four cross-platform cells, so CI
uses more runner time. Automation upgrades are manual and auditable rather than automatic. A stale
pin can miss upstream fixes and therefore must be reviewed routinely.

---

## ADR-028 — Omit inactive workflow placeholders

**Status:** Accepted · **Date:** 2026-09-11 · **Affects:** `BOOT-001 §§2, 12, 16, 17`

**Context.** The bootstrap created comment-only `.github/workflows/e2e-sign.yml` and
`.github/workflows/release.yml` files to reserve their future locations. GitHub registered both as
workflows, rejected them because they contained no workflow structure, and emitted failed push
runs `34517253705` and `34517254746` on the bootstrap merge even though the active CI workflow
succeeded.

**Decision.** A file with a recognized workflow extension exists under `.github/workflows/` only
when its owning feature delivers a valid executable workflow. At bootstrap, `ci.yml` is the only
workflow file. F-06 creates `e2e-sign.yml`; F-11 creates `release.yml`. Their reserved names remain
normative in documentation, but no empty, comment-only, disabled-extension, skipped, or no-op file
is committed for either workflow beforehand.

**Rationale.** GitHub treats recognized workflow paths as executable configuration, not inert
placeholders. Absence states the lifecycle honestly and cannot generate false failure or success
evidence. The owning BRDs already define the exact future paths.

**Rejected alternatives.** Comment-only files are empirically invalid. A skipped or no-op job
would create misleading green workflow history. An always-failing manual workflow would add an
intentional failure surface. Renaming placeholders with a disabled extension would preserve files
that serve no runtime purpose and could still be mistaken for implementation.

**Consequences.** The bootstrap tree contains only `ci.yml` under `.github/workflows/`. F-06 and
F-11 add their workflow files rather than filling existing placeholders. Repository tree checks
must use feature lifecycle state when evaluating those future paths.

---

## ADR-029 — Complete the v0.1 wire contract before implementation

**Status:** Accepted · **Date:** 2026-09-11 · **Affects:** `GLOSS-001 §§4, 8`, `SPEC-001 §§3, 6,
11`, `ARCH-001 §7`, `BRD-INDEX §5`, `BRD-F01`

**Context.** The F-01 pre-implementation audit found that the predicate examples showed nested
objects whose required fields, optional fields, and null handling were not fully specified. The
generated schema is authoritative for structural constraints, so leaving those decisions to
Pydantic defaults would make the Python implementation, rather than `SPEC-001`, define the public
wire format. The audit also found three conflicts: `mode` was wire-required while an acceptance
criterion omitted it, the camel-case rule did not exempt in-toto's `_type` and digest-map
`sha256` keys, and illustrative digest values used an algorithm prefix even though `GLOSS-001`
requires the algorithm to be named by the field or map key.

The `generate_json_schema(predicate_version)` signature also lacked a contract for its argument,
and the review collector needs an explicit unknown value when it cannot determine whether review
was required.

**Decision.** The v0.1 wire model is completed in `SPEC-001 §6` with a field table for every
nested object. Fields marked required must be present. Fields marked optional may be omitted or
set to JSON `null`; the reference implementation canonicalises its own output by omitting optional
null values. Arrays explicitly documented as possibly empty remain valid.

`Authorship.mode` remains required on the wire and has no model default. A collector with no
authorship evidence must explicitly set it to `unknown`; absence of evidence does not mean absence
of the field. `Review.required` is the closed tri-state `true`, `false`, or the string `unknown`.

Every SHA-256 value field contains exactly 64 lowercase hexadecimal characters with no prefix.
The algorithm is identified by the `sha256` map key or by the field's specified SHA-256 semantics.
The illustrative predicate examples are corrected accordingly.

All Python attributes remain snake case and all ordinary JSON properties remain camel case.
Protocol-defined `_type` and `sha256` are the only v0.1 exceptions. The additional structural
models `DigestSet`, `ChangeSetStats`, and `ReviewEvidence` are part of F-01 because they are needed
to generate strict nested schemas rather than permissive dictionaries.

`generate_json_schema()` produces the complete v0.1 `Statement` schema. Its
`predicate_version` argument accepts only the exact string `0.1`; any other value raises the new
`ERR-BUILD-205`. Schema file writing belongs to a repository-level script invoked by `just schema`,
not to `attest_core`, preserving the package's no-I/O boundary.

**Rationale.** A signed format must define omission, nullability, nested requiredness, and exact
encodings before its first implementation. Explicit protocol exceptions preserve in-toto
interoperability without weakening the project's naming rule. Keeping `mode` present prevents an
omitted field from being mistaken for a negative authorship assertion. A closed review tri-state
records uncertainty without overloading JSON null or accepting arbitrary strings.

**Rejected alternatives.** Inferring requiredness from illustrative examples would violate the
document convention that examples are non-normative. Letting Pydantic defaults determine the
schema would make other implementations reverse-engineer the Python package. Defaulting a missing
mode to `unknown` would make a required wire field optional. Prefixing digest strings would
contradict the normative digest convention. Writing the schema from `attest_core.schema` would put
filesystem I/O inside the pure core package.

**Consequences.** F-01 has a complete structural contract and can generate a reproducible schema.
Consumers must emit `mode` explicitly and must handle the `Review.required` tri-state. Optional
null input is accepted for interoperability, but attest-generated canonical Statements omit it.
Adding or changing a field after publication follows the predicate versioning rules.

---

## Template for new ADRs

```markdown
## ADR-0NN — <short imperative title>

**Status:** Proposed | Accepted | Superseded by ADR-0MM · **Date:** YYYY-MM-DD · **Affects:** <docs/features>

**Context.** What forced a decision.

**Decision.** What was decided, stated as a rule.

**Rationale.** Why, including the constraint that dominated.

**Rejected alternatives.** What else was considered and why it lost.

**Consequences.** What this costs, and what now becomes harder or impossible.
```
