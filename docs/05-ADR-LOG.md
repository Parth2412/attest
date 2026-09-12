# attest — Architecture Decision Log

| Field | Value |
|---|---|
| Document ID | `ADR-LOG` |
| Version | `1.17.0` |
| Status | **NORMATIVE** for recorded decisions |
| Last updated | 2026-09-12 |

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

## ADR-030 — Separate model diagnostics from boundary errors

**Status:** Accepted · **Date:** 2026-09-11 · **Affects:** `GLOSS-001 §6`, `AGENTS.md §7`,
`BRD-INDEX §6`, `BRD-F01`, `BRD-F05`, `BRD-F08`

**Context.** The F-01 executable API probes showed that its acceptance criteria and the
cross-cutting error obligation could not both be implemented literally. `AC-F01-010` requires
direct Pydantic model validation to raise `ValidationError`, including Pydantic-owned failures
such as unknown fields and incorrect primitive types. `X-05` said every error path must instead
raise a project-coded error. Pydantic's built-in structural failures cannot be replaced with
attest error classes without replacing or wrapping the required direct validation behavior.

The downstream public-operation contracts already define the appropriate boundary codes:
F-05 maps an invalid constructed Statement to `ERR-BUILD-210`, while F-08 maps structural and
semantic verification failures to their `ERR-VERIFY-*` codes.

**Decision.** Direct `BaseModel.model_validate()`, model construction, and assignment validation
are a typed diagnostic layer and may raise Pydantic `ValidationError`. Those diagnostics do not
cross a CLI, collector, builder, signer, store, verifier, policy, or export operation boundary
without translation to the code defined by that boundary's BRD.

When F-01 assigns a specific semantic code—malformed Git OID, subject/predicate digest mismatch,
or unknown closed-enum value—the underlying validator **MUST** retain the corresponding
`BuildError` and its `code`, `message`, and `remediation` in the Pydantic error context. Pure F-01
functions such as `canonicalize()` and `generate_json_schema()` raise `BuildError` directly when
their BRD assigns a code. Pydantic-owned structural diagnostics for which F-01 assigns no project
code remain ordinary `ValidationError` entries until an owning operation maps them.

`X-05` therefore applies to attest-defined domain errors escaping public feature-operation
boundaries, not to direct model diagnostics explicitly exposed and tested by F-01. Every
attest-defined error class still carries a code, human message, and remediation hint.

**Rationale.** Structural model diagnostics and externally actionable operation failures serve
different audiences. Preserving Pydantic's locations and stable error types makes model failures
precise, while mapping at operation boundaries ensures CLI and automation consumers receive the
documented project codes. This keeps one owner for each externally visible failure instead of
inventing dozens of F-01 codes that downstream features would immediately remap.

**Rejected alternatives.** Replacing every Pydantic failure with a custom exception would violate
the F-01 acceptance criteria and lose nested field locations. Assigning one generic F-01 code to
all structural failures would erase useful diagnostics. Treating raw `ValidationError` as an
externally stable API would bypass the coded contracts already assigned to F-05 and F-08.

**Consequences.** Callers using wire models directly handle `ValidationError`. Public operations
must catch it and emit their BRD-owned code. F-01 tests verify both ordinary structural diagnostics
and retention of the three assigned semantic codes. Boundary-mapping tests remain owned by the
features that expose those boundaries.

---

## ADR-031 — Keep F-02 commit identities in ChangeSetInfo

**Status:** Accepted · **Date:** 2026-09-11 · **Affects:** `BRD-F02`, `ADR-019`

**Context.** `AC-F02-100` requires `record.base_commit` to equal a forge-reported merge base, but
ADR-019 and `SPEC-001 §5.3` require a ChangeSet Record to contain exactly `algorithm` and
`entries`. F-01 implements that closed record and deliberately has no `base_commit` field.
`REQ-F02-100` already places the forge merge base in `ChangeSetInfo.merge_base` and says to use it
as `baseCommit`, so the acceptance criterion contradicts both its requirement and the signed wire
contract.

**Decision.** In a pull-request collection, the resolved forge-reported merge base is recorded in
both `ChangeSetInfo.merge_base` and `ChangeSetInfo.base_commit`. `AC-F02-100` tests those two
metadata fields. `ChangeSetRecord` remains context-free and contains no commit identity.

**Rationale.** The signed predicate must retain the exact commit context used to derive entries,
while the digest must remain stable when identical transitions move through rebase or squash
workflows. The two `ChangeSetInfo` fields express that context without reopening CSD-1.

**Rejected alternatives.** Adding `base_commit` to `ChangeSetRecord` would reverse ADR-019 and
break required digest stability. Testing only `merge_base` would fail to prove that the same
commit was used as the diff base. Removing `baseCommit` from signed metadata would discard the
recomputation boundary required by `SPEC-001 §6.2`.

**Consequences.** F-02 resolves the supplied merge-base revision once, diffs from that commit,
and assigns the resolved OID to both signed metadata fields. No F-01 model or CSD-1 change is
required.

---

## ADR-032 — Define the F-02 collector operation boundary

**Status:** Accepted · **Date:** 2026-09-11 · **Affects:** `BRD-F02`, `F-02`

**Context.** The original F-02 interface required an already-created backend even though
`REQ-F02-160` requires automatic selection and an override. It also provided no input for the
forge merge base required by `REQ-F02-100`, no result field for backend diagnostics, and no
definition of `CollectionWarning`. Finally, `GitBackend.repository_url()` may return `None` while
F-01 requires `ChangeSetInfo.repository`. Implementing any of these gaps would require invented
public behavior.

**Decision.** `collect_changeset()` accepts keyword-only `merge_base_rev` and `repository_url`
overrides. Its `backend` argument accepts an injected `GitBackend` or one of `auto`, `pygit2`, and
`subprocess`, defaulting to `auto`. An injected backend supports deterministic tests. In automatic
mode, pygit2 is preferred and subprocess is used only when the pygit2 backend is unavailable;
repository or revision failures are never masked by switching implementations. An explicit
backend that is unavailable raises `ERR-COLLECT-104`.

Every `GitBackend` exposes a stable backend name and working-tree dirtiness in addition to the
existing revision, merge-base, diff, and repository operations. The result contains immutable
tuples of structured warnings and a `CollectionDiagnostics` value naming the selected backend.
`WARN-COLLECT-001` reports an ignored dirty working tree; `WARN-COLLECT-002` reports that the
requested head differs from checked-out `HEAD`. Both conditions may be reported together and
neither changes the tree-to-tree result.

An explicit repository URL takes precedence over backend discovery. The selected value is
normalised per `REQ-F02-110`. If neither source provides a value, the public operation raises
`ERR-COLLECT-105` with remediation directing the caller to supply repository identity. When
`merge_base_rev` is present, F-02 resolves it, uses it as the diff base, and records it as both
`ChangeSetInfo.base_commit` and `ChangeSetInfo.merge_base`; otherwise it resolves and uses
`base_rev` without calling `merge_base()`.

**Rationale.** One explicit boundary makes every context-affecting input visible, retains backend
injection for conformance testing, and produces machine-readable diagnostics without coupling the
collector to the later CLI logging layer. Refusing to guess repository identity prevents signed
records from silently naming the wrong project.

**Rejected alternatives.** Hiding merge-base discovery inside a backend would violate
`REQ-F02-090`. Falling back after data or revision errors could make two backends observe different
repositories. Returning a partial result without repository identity would violate the F-01 wire
model. Logging the backend directly would leave library callers without diagnostics and couple
F-02 to F-10. Mutable warning lists would undermine the frozen result contract.

**Consequences.** F-02 adds `ERR-COLLECT-105`, two stable warning codes, and typed backend
diagnostics. Callers must supply repository identity for repositories without a usable remote.
The CLI later maps its backend flag directly to the three documented selector values.

---

## ADR-033 — Complete the F-02 error boundary

**Status:** Accepted · **Date:** 2026-09-11 · **Affects:** `BRD-F02`, `ADR-030`, `F-02`

**Context.** ADR-032 defines the F-02 operation inputs but leaves three public failure classes
ambiguous. A repository identity may be present but impossible to normalise, a backend selector
may be unknown rather than merely unavailable, and an otherwise valid Git operation may fail
after repository and revision validation. Passing raw `pygit2` or subprocess exceptions through
`collect_changeset()` would violate the coded public-operation boundary established by ADR-030.

The existing shallow-clone criterion also overlaps general revision failure. Without an exact
classification rule, the same absent object could produce `ERR-COLLECT-101` or
`ERR-COLLECT-103` depending on the backend.

**Decision.** `collect_changeset()` maps every failure leaving its public boundary to one of the
BRD-F02 codes and preserves the code, human message, and remediation fields:

- `ERR-COLLECT-101` applies only when the selected diff-base input is a full 40-character
  lowercase OID, that object is unavailable, and the repository reports itself as shallow.
- `ERR-COLLECT-102` applies when `repo_path` is not a Git repository.
- `ERR-COLLECT-103` applies to every other unresolved base, head, or explicit merge-base input,
  including malformed OIDs and unknown symbolic revisions.
- `ERR-COLLECT-104` applies to an unknown selector, an explicitly selected unavailable backend,
  or automatic selection finding neither backend usable.
- `ERR-COLLECT-105` applies when repository identity is absent or cannot be normalised to the
  canonical HTTPS form required by F-01.
- `ERR-COLLECT-106` applies when a backend operation fails after repository, backend, revision,
  and repository-identity validation, including invalid entry data returned by a backend.

Backend-specific exceptions may be retained as exception causes for debugging, but their text is
not part of the stable public error message and is never used to classify a failure. Automatic
selection falls back only during backend availability checks, never after an operational error.

**Rationale.** Mutually exclusive classifications make both implementations observable in the
same way and prevent backend exception wording from becoming an accidental API. Restricting the
shallow code to a missing full object identity avoids falsely telling a caller to deepen a clone
when the actual input is a mistyped branch or malformed revision.

**Rejected alternatives.** Mapping every Git failure to `ERR-COLLECT-103` would hide repository
corruption and permission failures as revision mistakes. Treating any failure in a shallow clone
as `ERR-COLLECT-101` would prescribe `fetch-depth: 0` for unrelated errors. Exposing raw backend
exceptions would make error behavior platform- and implementation-dependent. Silently dropping
an invalid repository URL would permit incomplete signed metadata.

**Consequences.** F-02 adds `ERR-COLLECT-106` and broadens the precise conditions of
`ERR-COLLECT-104` and `ERR-COLLECT-105`. Conformance tests must inject each failure class into
both backend paths and prove identical public codes. Diagnostic causes remain available to Python
callers without becoming stable user-facing text.

---

## ADR-034 — Make pygit2 an optional backend extra

**Status:** Accepted · **Date:** 2026-09-11 · **Affects:** `TECH-001`, `BOOT-001`, `BRD-F02`,
`BRD-F07`, `COMPAT-001`

**Context.** ADR-007 requires a subprocess fallback because a compatible `pygit2`/libgit2 wheel
may be unavailable. The bootstrap manifests nevertheless made `pygit2` a mandatory dependency of
both `attest-collect` and `attest-store`. Because `attest-cli` installs every workspace package,
dependency resolution could fail before the collector ever had an opportunity to select its
fallback. The mandatory dependency therefore defeated the installation-risk mitigation it was
meant to preserve.

**Decision.** `attest-collect` and `attest-store` expose a `pygit2` optional dependency extra
containing `pygit2==1.20.0` and do not include it in their base dependencies. Both packages import
`pygit2` lazily. A base installation remains fully operational through the Git CLI:
`SubprocessBackend` implements F-02, and the F-07 `GitRefStore` uses its subprocess implementation
when the extra is absent.

The workspace root development group pins `pygit2==1.20.0`. The committed lock retains that exact
validated version, and CI installs the development group and runs conformance against both native
and subprocess implementations. Automatic F-02 selection prefers pygit2 when importable and falls
back only when it is unavailable; explicitly requesting an unavailable pygit2 backend raises
`ERR-COLLECT-104`. Distribution builds may select the extra but may not make base package
installation depend on a compatible native wheel.

**Rationale.** A fallback is meaningful only if users can install and start the program without
the primary backend. Keeping the exact native dependency in development and CI preserves the
stronger dual-implementation test obligation without transferring wheel availability risk to
every user. The same rule for storage prevents its transitive dependency from silently undoing
the collector's portability guarantee.

**Rejected alternatives.** Keeping `pygit2` mandatory would make ADR-007 ineffective for wheel
installation failures. Removing it from CI would permit the preferred backend to rot. Making
`attest-store` mandatory-native would still force pygit2 into `attest-cli`. Falling back after an
operational Git error remains forbidden because it can make two backends observe different
repository states.

**Consequences.** Package metadata, compatibility documentation, and the lock must keep base and
extra installation paths explicit. Release validation must prove a minimal installation without
pygit2 and the full development installation with it. F-07 must provide subprocess behavior for
its Git-ref store rather than relying exclusively on libgit2.

---

## ADR-035 — Complete the F-03 collector contracts

**Status:** Accepted · **Date:** 2026-09-12 · **Affects:** `SPEC-001 §6.3`, `ARCH-001 §7`,
`BRD-F03`, `F-03`

**Context.** The F-03 BRD named four claim sources but did not define `CollectContext`, a way for
collectors to return non-fatal diagnostics, source-specific reference and digest boundaries, or
the exact syntax used by manual claims. The displayed `X-Attest-Claim` grammar omitted
`claimId`, although `AC-F03-030` requires the same identifier to appear in a sidecar and a
trailer. `Co-Authored-By` agent-pattern semantics were unspecified. The mode table did not cover
manual-only claims or an empty ChangeSet. It also required canonical-path validation without
assigning a public error code for invalid `changed_paths`.

The Git-note source was described only as "Git AI interoperability." The current upstream Git AI
standard is `authorship/3.0.0` under `refs/notes/ai`; it contains line-oriented path attestations
plus `sessions`, legacy `prompts`, and known-human records. Mapping that format without naming a
supported version and transformation would guess wire behavior. The upstream standard and parser
were inspected at git-ai commit `0670e7ef27590af0e8ff5409267f3f4b09b8fcb4` on 2026-09-12.

**Decision.** F-03 uses immutable `CollectContext`, `KnownAgentPattern`,
`ClaimCollectorResult`, `AuthorshipWarning`, and `AuthorshipCollection` contracts defined in
`BRD-F03 §4`. `CollectContext` carries the repository path, already-resolved full base and head
commit OIDs, a notes ref defaulting to `refs/notes/ai`, and ordered known-agent patterns. A public
collection validates repository readability and both commits before running optional collectors.
An inability to read that Git boundary remains fatal under the existing F-02 codes; every claim
source failure is represented as a non-fatal structured warning.

Collectors return claims and warnings rather than mutating shared state. The supplied collector
sequence defines duplicate precedence; the standard sequence is sidecar, trailer, Git note, then
manual. Each built-in collector uses a deterministic source order. Duplicate identifiers retain
the first claim. Final claims are sorted by `claimId`, and final warnings are sorted by code then
reference. A source without a native identifier receives a newly generated standards-valid
UUIDv7. UUID generation is not an ordering or trust input, and a supplied `claimedAt` is never
used to generate or order identifiers.

The accepted sidecar is the closed object defined in `ARCH-001 §7`. Its UTF-8 filename is exactly
`<claimId>.json`, its `schemaVersion` is exactly `0.1.0`, and its filename identifier must equal
the body identifier. A `prompt` property is the only input-only exception: it is removed before
closed-object validation and produces `WARN-COLLECT-003`. Symlinks and non-regular directory
entries are malformed sidecars. A missing claims directory means no sidecar claims; an existing
directory that cannot be enumerated or read produces `ERR-COLLECT-112` as a warning.

`X-Attest-Claim` and manual values use the closed, order-independent grammar in `BRD-F03 §4.2`.
`agent` is required; every other key is optional. `claim-id` permits cross-source de-duplication,
while an omitted identifier is generated as UUIDv7. Unknown or duplicate keys, empty values,
invalid model pairs, invalid timestamps or digests, and non-canonical paths make only that input
malformed. Commit traversal is the full `base..head` set, excluding base, with commit OIDs sorted
ascending. A trailer source digest covers the exact raw commit-message bytes, not normalised
trailer output. Manual source bytes are the exact UTF-8 flag value.

Trailer-token matching is ASCII case-insensitive. References canonicalise the matched token to
`x-attest-claim` or `co-authored-by`, with occurrences counted independently per token in raw
commit-message order. Payload keys remain case-sensitive.

Known-agent patterns use case-sensitive, whole-string shell globs against the complete
`Co-Authored-By` value. Patterns are evaluated in configuration order and the first match supplies
the `AgentRef`; unmatched identities are silent. This bounded grammar avoids treating a human
co-author as an agent by inference and avoids executing user-provided regular expressions.

Git AI support is pinned to `authorship/3.0.0` and the configured `refs/notes/*` ref. F-03 reads
notes attached to the same sorted commit range, verifies the complete upstream structure, ignores
known-human keys, and emits one claim per referenced AI session or legacy prompt. Repeated trace
keys for one session are combined into one scope. `agent_id.tool` becomes `agent.name`, and
`agent_id.id` becomes `sessionId`. `agent_id.model` becomes a `ModelRef` only when it explicitly
has the `provider/name` shape; otherwise it is omitted because the provider may not be guessed.
Scope paths use the upstream parser rule: a path surrounded by double quotes has only those outer
quotes removed, with no unescaping. The claim-source digest covers the exact raw note-blob bytes.
An absent optional notes ref is silent; unreadable, unsupported, or malformed notes produce
`ERR-COLLECT-116` as warnings and do not abort other collectors.

Source references and digest boundaries are fixed by `BRD-F03 §4.4`. Manual claims are recorded
but remain ineligible for AI-mode coverage because `SPEC-001 §6.3` explicitly excludes `manual`.
When claims exist but no eligible claim intersects a non-empty ChangeSet, or when the ChangeSet is
empty and claims exist, mode is `unknown`. Scope absence covers the entire non-empty ChangeSet;
scope coverage is evaluated per claim, never by unioning claims. The repository marker is an
existing `.attest/` directory at the repository root and is consulted only when no claims exist.

F-03 adds `ERR-COLLECT-115` through `ERR-COLLECT-118` and `WARN-COLLECT-003` through
`WARN-COLLECT-004` with the exact meanings in its BRD. Invalid public `changed_paths` is fatal
because a mode cannot be derived. Malformed individual source paths remain non-fatal under that
source's code. Scope paths outside the ChangeSet are retained and produce `WARN-COLLECT-004`.

**Rationale.** Authorship inputs are intentionally untrusted, but their collection must still be
deterministic, traceable, and non-lossy. Explicit raw-byte boundaries make `source.digest`
reproducible. Structured result diagnostics satisfy graceful degradation without hidden logging
or mutable collector state. Pinning the external Git AI profile prevents a future incompatible
format from being accepted accidentally. Omitting ambiguous model data preserves the normative
rule that model values are never guessed.

**Rejected alternatives.** Returning only `list[AuthorshipClaim]` cannot report a malformed file
while retaining valid siblings. Treating all collector failures as fatal violates F-03. Regex
agent patterns introduce unnecessary denial-of-service behavior and ambiguous partial matches.
Deriving a model provider from a tool or model name would fabricate signed data. Parsing any Git
note that resembles JSON would make compatibility versionless. Hashing normalised trailers or
re-serialised notes would not bind the bytes actually found in Git. Treating manual-only or empty
changes as AI-authored would overstate the available evidence.

**Consequences.** F-03 requires a small secure Git signal reader in `attest-collect`, exact
upstream Git AI fixtures, and source-specific malformed-input tests. Git AI model strings without
an explicit provider are intentionally not copied into `ModelRef`. A future Git AI schema version,
additional trailer key, or different pattern language requires a new ADR. CH-03 remains open:
shipping hook examples does not establish their real-world claim rate.

---

## ADR-036 — Separate F-05 assembly from environment collection

**Status:** Accepted · **Date:** 2026-09-12 · **Affects:** `SPEC-001 §6.6`, `ARCH-001 §3`,
`BRD-F05`, `F-05`

**Context.** BRD-F05 required `build_statement()` to be pure while also requiring runtime package
metadata and an injectable clock. It did not identify which distribution supplied the collector
version or define the environment-adapter boundary. The phrase "recognised CI environments with
a verifiable workload identity" had no exact platform signals, and therefore could not safely
control `environment.trusted`. Its prescribed sort keys were not total when reviewer timestamps,
identities, or check names tied, and it omitted automated-review ordering. `ERR-BUILD-211` was
unreachable through the non-optional typed builder signature, and the optional-review language
could be read as permission for the builder to invent an unknown review.

GitHub's official documentation was inspected on 2026-09-12. It defines `GITHUB_ACTIONS`,
`GITHUB_SERVER_URL`, `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_WORKFLOW_REF`, and
`GITHUB_EVENT_NAME`; exposes `ACTIONS_ID_TOKEN_REQUEST_URL` and
`ACTIONS_ID_TOKEN_REQUEST_TOKEN` to jobs permitted to request OIDC tokens; and defines the
github.com Actions OIDC issuer as `https://token.actions.githubusercontent.com`.

**Decision.** `attest-core.build_statement()` retains the exact BRD signature and is wholly pure.
It consumes a supplied `Collection` and never reads environment variables, time, installed
metadata, the filesystem, or the network. `attest-collect.collect_environment()` is the bounded
impure adapter. It accepts an optional environment mapping and an injectable clock, reads process
environment only when the mapping is absent, calls the clock once, normalises its aware result to
UTC seconds, and reads the installed `attest-collect` distribution version at call time. Its
collector name is `attest`. Missing or unusable required inputs and metadata raise
`ERR-BUILD-211`.

Environment classification is exact and ordered: `GITHUB_ACTIONS == "true"` selects
`github-actions`; otherwise `GITLAB_CI == "true"` selects `gitlab-ci`; otherwise `CI == "true"`
selects `other`; otherwise the environment is `local`. Only github.com Actions may be trusted in
v0.1. Trust additionally requires a non-empty run ID, workflow reference, and event name; a
base-10 run attempt of at least one; and non-empty OIDC request URL and token signals. A trusted
result records those non-secret fields and the fixed official issuer. OIDC request credentials
are inspected only for availability and are never retained or exposed. Incomplete GitHub
metadata remains `github-actions` and untrusted; independently valid optional fields may still be
recorded. GitLab CI, other CI, and local are always untrusted until their own workload-identity
contracts are accepted.

The producer's `trusted` flag is context rather than cryptographic proof. F-08 must verify the
signed bundle against the caller's expected identity and issuer before trusting it. This prevents
spoofed local environment variables from becoming a trust anchor.

The builder validates the assembled wire object structurally against generated JSON Schema before
final Pydantic semantic validation and maps either failure to `ERR-BUILD-210`. Public errors do
not contain raw validation dumps; private diagnostics remain available through exception
chaining. Required arguments that are missing at runtime raise `ERR-BUILD-211`, despite their
non-optional static types. A caller without F-04 data supplies an explicit unknown `Review`; the
builder never constructs or infers one.

Claims order by their specification-unique `claimId`. Reviewers order by `submittedAt`, identity,
then canonical object bytes; automated reviews by `submittedAt`, tool, then canonical object
bytes; and checks by name then canonical object bytes. The final canonical-byte key makes each
non-unique primary ordering total. Empty optional checks and automated reviews are omitted. Empty
path arrays are preserved because absence and an explicitly empty scope have different meanings.

**Rationale.** Moving time and metadata reads to the collector adapter preserves the pure-core
dependency rule and makes both operations deterministic under injected inputs. An exact,
conservative trust predicate is auditable and fails closed without pretending that environment
variables prove identity. Total sort keys make canonical output independent of input order even
for ties. Explicit ownership of unknown review state preserves the rule that signed values are
never fabricated.

**Rejected alternatives.** Reading package metadata or time inside `build_statement()` violates
the pure-core contract. Using the future CLI package version misidentifies the component that
produces `Collection`. Treating any `CI` variable, GitLab CI, or GitHub Actions without OIDC
availability as trusted claims more than v0.1 can verify. Passing a caller-supplied trust boolean
merely moves the ambiguity. Stable sorting by incomplete keys retains input-order dependence.
Synthesising an unknown review hides missing collector ownership. Publishing raw schema or model
diagnostics risks leaking signed input data.

**Consequences.** F-05 implementation spans pure assembly in `attest-core` and environment
collection in `attest-collect`, without adding a package dependency. GitLab CI remains visibly
untrusted in v0.1. Adding a trusted platform, changing collector identity, or changing the trust
signals requires a new ADR. Tests must cover every trust signal independently, tied ordering,
secret non-disclosure, both validation layers, and injected-clock failures.

---

## ADR-037 — Make the F-06 signing boundary fail-bounded and acyclic

**Status:** Accepted · **Date:** 2026-09-12 · **Affects:** `ADR-005`, `ARCH-001`, `TECH-001`,
`BRD-F06`, `F-06`, `F-08`, `F-10`

**Context.** The F-06 pre-implementation audit found four contract defects. First,
`REQ-F06-100` required the full F-08 verification pipeline before F-06 could report success even
though F-08 depends on F-06. This created a circular completion dependency and contradicted the
explicit signer, store, and verifier steps in `ARCH-001 §4`. Second, optional long-lived-key
support in `REQ-F06-090` had a mandatory acceptance criterion and no verification-output data
contract. Third, the result did not carry the explicitly configured signing environment, and
"certificate issuer" did not distinguish the workload's OIDC issuer from the X.509 CA issuer.
Fourth, no code covered trust-configuration failures before Fulcio.

Source inspection and executable probes against the locked `sigstore==4.5.0` established an
additional implementation constraint. Ambient GitHub OIDC retrieval and the timestamp-authority
client set explicit request timeouts, but the Fulcio and Rekor clients do not. The library exposes
no supported timeout injection point, and `SigningContext.from_trust_config()` is itself marked
API-private despite being the documented construction path. The current Rekor v2 entry can also
omit `integratedTime`; its RFC 3161 material supplies signed time instead. Requiring an integrated
time would reject the already validated staging bundle.

**Decision.** F-06 owns the keyless signing adapter and its output postconditions. It does not
own the full independent F-08 verification pipeline. `attest run`, at the CLI composition root,
continues to run that pipeline before the overall operation reports success as required by
`ADR-005`. This clarification changes ownership, not the self-verification security property.

The v0.1 signer supports keyless ambient OIDC only. It has no long-lived key, key-path, or manual
token input. Supporting long-lived keys later requires a new ADR, a key-management contract, and
an explicit verification-result representation.

The signing environment is a required `production` or `staging` enum with no default and is
included in the returned result. `certificate_identity` is the detected ambient identity and
`certificate_issuer` is its effective OIDC issuer, not the Fulcio CA distinguished name. Before
returning, the signer applies Sigstore's public `Identity` policy to the actual leaf certificate
using those exact values. The Rekor log index is required. Integrated time remains optional
because Rekor v2 may establish time through RFC 3161 timestamp material; the complete raw bundle
retains whichever signed-time material Sigstore emitted.

Each concrete signing attempt runs in an isolated child process. The parent enforces a hard
120-second deadline by default and terminates a worker that exceeds it, so an upstream request
without its own timeout cannot outlive the public operation. The timeout is injectable for tests
and must be positive. A timeout before the Rekor stage permits at most one fresh attempt. Once the
worker announces the Rekor stage, the operation is non-idempotent and must not be retried. A
deadline failure maps to `ERR-SIGN-304`; no upstream exception text crosses the process boundary.
Trust-root or signing-configuration initialization failures map to the new `ERR-SIGN-306`.

After Sigstore returns, the adapter serialises through `Bundle.to_json()`, reparses through
`Bundle.from_json()`, and inspects the standard bundle JSON only to assert the DSSE and required
material postconditions and extract public log metadata. It does not construct or mutate PAE,
the DSSE envelope, or verification material. A failed postcondition maps to `ERR-SIGN-305`.

**Rationale.** Keeping self-verification at composition preserves independent signer and verifier
code paths and makes the dependency graph executable. Keyless-only scope removes an unaudited
key-management surface. Process isolation is the only fail-bounded mechanism available without
depending on Sigstore private HTTP clients: a thread timeout cannot stop an abandoned Rekor
submission, while overriding private sessions would bind security behavior to undocumented
internals. Stage-aware retry rules avoid duplicate transparency-log submissions.

**Rejected alternatives.** Implementing F-08 inside F-06 violates feature ownership and verifier
isolation. Marking F-06 complete against a fake injected verifier does not execute the full
pipeline. Shipping optional long-lived keys leaves key storage and verification output undefined.
Accepting Sigstore's unbounded Fulcio/Rekor calls violates the repository-wide network rule.
Mutating private requests sessions or reimplementing the Sigstore clients couples correctness to
private APIs. Timing out a worker thread allows the network operation to continue after failure.
Retrying the complete signing transaction can create duplicate log entries. Requiring Rekor v2
`integratedTime` contradicts the executed staging evidence.

**Consequences.** Signing incurs child-process startup cost and has a documented 120-second
per-attempt ceiling. A pre-Rekor timeout can consume up to two attempts; a Rekor-stage timeout
fails after the first attempt. F-10 must compose F-08 self-verification before reporting overall
success. The returned result contains enough environment and identity metadata for safe user
guidance without exposing the ambient token. Tests must prove worker termination, stage-aware
retry limits, keyless-only input, certificate-policy validation, required bundle material, and
secret-safe inter-process failures.

---

## ADR-038 — Make the F-08 verification boundary explicit

**Status:** Accepted · **Date:** 2026-09-12 · **Affects:** `ADR-004`, `SPEC-001 §8`,
`ARCH-001`, `TECH-001`, `BRD-F08`, `F-08`, `F-10`

**Context.** The F-08 pre-implementation audit found four incomplete or contradictory security
contracts. First, `verify(bundle, constraint, repo=None)` named neither a trust root nor a Sigstore
environment, so an implementation would have to default production, infer from untrusted bundle
contents, read hidden configuration, or try multiple roots. Second, `CheckOutcome` had no defined
names, result states, code semantics, or early-abort representation. Third, the BRD promised bounded
identity globs while Sigstore 4.5.0's public `Identity` policy accepts exact identities only. Fourth,
`AC-F08-110` expected a file modified after signing to change a digest recomputed from immutable
signed commits, contradicting `ADR-019` and F-02's rule that working-tree state is ignored. A
repository path alone also cannot tell the verifier which current ChangeSet the caller means.

Installed-source inspection and executable probes confirmed the public verification boundary.
`Bundle.from_json` parses serialized bundles; `Verifier.production` and `Verifier.staging` accept an
`offline` boolean; `ClientTrustConfig.from_json` parses a complete supplied trust configuration;
and `Verifier.verify_dsse` accepts one `VerificationPolicy` and returns payload type plus exact
payload bytes. An expired staging certificate verified offline from its embedded RFC 3161 time and
inclusion proof. Exact wrong identity and near-miss issuer policies failed. Removing the inclusion
proof caused `Bundle.from_json` itself to reject the bundle, before `verify_dsse` could supply the
BRD-mandated `ERR-VERIFY-013` classification. The locked TUF fetcher applies a 30-second socket
timeout to every request.

**Decision.** The public F-08 operation requires three positional inputs: bundle bytes,
`IdentityConstraint`, and `TrustRootSource`. A service trust source explicitly selects production
or staging and requires an `offline` boolean. Offline service verification uses only packaged or
cached TUF material; online refresh occurs only when the caller explicitly sets `offline=False`.
A supplied trust source contains complete Sigstore client-trust-configuration JSON, is parsed only
through `ClientTrustConfig.from_json`, and performs no network operation. The verifier never infers
an environment from bundle content and never tries more than the selected root. Trust initialization
failure is check 2 with `ERR-VERIFY-012`.

`IdentityConstraint` is validated at construction. An identity with no wildcard is exact. A glob
is accepted only for a GitHub Actions workflow URI with an entirely literal prefix through
`@refs/`; within the ref, each `*` matches one or more non-slash characters. Matching is
case-sensitive and anchored to the whole URI. `**`, `?`, bracket expressions, empty values, and
wildcards outside the ref are `ERR-VERIFY-011`. For a glob, the verifier resolves exactly one
matching URI SAN from the public leaf-certificate surface and supplies that exact SAN and the exact
issuer to Sigstore's public `Identity` policy. Zero or multiple matches fail `ERR-VERIFY-013`.

The stable check names are `bundle-structure`, `sigstore-dsse`, `statement-payload`,
`structural-schema`, `semantic-model`, and `changeset-recomputation`. Attempted checks record
`passed` or `failed`; the optional sixth check records `skipped` on complete verification when no
repository constraint was supplied. Only a failed check carries a code. On failure, that outcome is
the final list entry and later checks are absent.

Local recomputation accepts a `RepositoryConstraint` containing path, caller-selected base
revision, and caller-selected head revision. A verifier-specific, read-only Git CLI path resolves
those revisions and computes the tree transition independently of `attest-collect`. It disables
replacement objects, hooks, external diff and text conversion, and rename/copy detection; ignores
the working tree; and bounds every subprocess. Unavailable repositories, unresolved revisions,
failed recomputation, and digest mismatch are `ERR-VERIFY-010`. `AC-F08-110` commits the changed file
and points the constraint at the new head; it also proves that an uncommitted edit is ignored.

The public function cannot be called without an identity constraint. Such an omission is rejected
as usage or configuration error before verification, matching F-10's exit-code contract. The
`unverified-identity` term from `ADR-004` is retained only for inspect-only output that has not
claimed verification success; it is not a `VerificationResult` status. A standard-JSON preflight
classifies the specific absence of an inclusion proof as failed check 2 / `ERR-VERIFY-013` even
though the locked Sigstore parser rejects it; every other malformed bundle remains
`ERR-VERIFY-001`. No private Sigstore method or exception-text classification is permitted.

**Rationale.** Explicit trust prevents a staging root, hidden refresh, or attacker-selected root
from silently entering production verification. Resolving a bounded pattern to an exact SAN retains
Sigstore's audited identity and issuer enforcement instead of recreating it. Caller-selected Git
revisions make replay checks meaningful and preserve `CSD-1`'s intentional rebase/squash stability.
Stable result fields make early abort auditable without inventing cryptographic sub-failures that
the upstream public API cannot distinguish.

**Rejected alternatives.** Defaulting to production makes staging tests and private deployments
depend on hidden overrides. Trying production and staging until one accepts weakens the trust
boundary. Inferring an environment from an unsigned outer wrapper trusts attacker-controlled data.
Implementing identity verification instead of calling `Identity` duplicates security-sensitive
upstream behavior. Treating every glob as a regular expression permits unbounded and potentially
pathological policies. Recomputing from the signed commits cannot detect a bundle replayed against a
different caller-intended ChangeSet. Importing `attest-collect` violates the peer-adapter boundary;
guessing `HEAD` makes historical verification nondeterministic. Mapping a missing proof to bundle
malformation contradicts the explicit `ERR-VERIFY-013` requirement.

**Consequences.** F-08 gains explicit trust and repository types and an independent bounded Git
reader. Callers must choose trust behavior and current ChangeSet context rather than relying on
defaults. Exact non-GitHub identities remain supported, but bounded glob convenience is limited to
the trusted v0.1 GitHub Actions shape. Tests must store staging-signed v0.1 bundles with provenance,
including a bundle whose certificate has expired, and must exercise both packaged/cached and
supplied trust configurations offline. F-10 must compose these required inputs. F-08 cannot be
marked Done until an independent human has reviewed the six-check order.

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
