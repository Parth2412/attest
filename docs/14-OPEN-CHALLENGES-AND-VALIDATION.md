# attest — Open Challenges and Validation Plan

| Field | Value |
|---|---|
| Document ID | `CHALLENGE-001` |
| Version | `1.0.4` |
| Status | **NORMATIVE** for validation gates and empirical unknowns |
| Last updated | 2026-09-10 |

---

## 1. What this document is

Every **documentation** question is closed. `MPD-001 §14` lists all six, each closed by an ADR.
No feature is blocked on an undecided design question.

What remains cannot be closed by writing. These are **empirical unknowns** — things that are true
or false about the world, and can only be settled by running something or asking someone. This
document lists them exhaustively, in the order they must be attacked, with a pre-committed gate
for each.

**Rule for implementers and agents:** a challenge marked `OPEN` with `blocks:` set **MUST** be
closed before the named features are started. Closing a challenge means recording its outcome in
§12 of this document and, where the outcome changes a decision, adding an ADR.

---

## 2. Challenge summary

| ID | Challenge | Kind | Blocks | Cost | When |
|---|---|---|---|---|---|
| `CH-01` | Does `CSD-1` survive real repositories? | Technical | F-01, F-02 | 2 days | **Week 0** |
| `CH-02` | Do the pinned libraries actually do what the BRDs assume? | Technical | F-06, F-08 | 2 days | **Week 0** |
| `CH-03` | Can agent harnesses reliably emit claims? | Product | M2 exit | 3 days | **Week 0–1** |
| `CH-04` | Does the evidence shape satisfy a real auditor? | Market | F-12 | 1 week elapsed | Week 1–2, runs in parallel |
| `CH-05` | Will teams enable a *blocking* gate? | Product | M2 exit | measured | Week 5–8 |
| `CH-06` | Will anyone pay, and who signs? | Market | M3 exit | measured | Week 9–12 |
| `CH-07` | Will anyone else implement the spec? | Strategic | Standards thesis | ongoing | From M1 publish |
| `CH-08` | Does it hold up at monorepo scale? | Technical | F-02 DoD | 1 day | Week 2 |
| `CH-09` | Is container cold start acceptable? | Technical | F-11 DoD | 1 day | Week 8 |

**Week 0 is `CH-01`, `CH-02`, `CH-03` — roughly five working days, before any production code.**
They are cheap, and they attack the three failures that would invalidate the most work.

---

## 3. `CH-01` — Does `CSD-1` survive real repositories?

**Status:** CLOSED · **Blocks:** F-01, F-02 · **Cost:** 2 days

### The unknown
`CSD-1` is designed but has never been executed. It is a **wire format**: once published and
signed against, changing it invalidates every prior attestation. Design surviving contact with
real git history is not guaranteed.

### Why documentation cannot close it
The edge cases in `SPEC-001 §5.4` are the ones I could enumerate. Real repositories contain ones
nobody enumerates: octopus merges, orphaned histories, case-folding collisions on macOS,
`core.autocrlf` interactions, submodules pointing at missing commits, files at path-length limits.

### The experiment
A throwaway script — **not** production code, not in the repository — that:

1. Implements `CSD-1` per `SPEC-001 §5.3` in ~150 lines using `pygit2`.
2. Runs against at least five real repositories, chosen to include: one large monorepo, one with
   submodules, one with non-ASCII paths, one with heavy binary content, one of your own.
3. For each, computes the digest for the last 200 merge commits.
4. Re-runs everything on a second machine and a different OS.
5. Independently implements step 3 with `git diff-tree --no-renames --raw` and compares.

### Gate — all must hold
- [x] Digests are identical across machines and OSes for every commit
- [x] The `pygit2` and `git`-CLI implementations agree on 100% of cases
- [x] Every sampled squash-merged PR whose canonical entry transitions are unchanged produces a
  stable digest across the squash; changing any entry field changes the digest (`ADR-019`)
- [x] No repository produces an unhandled case not covered by `SPEC-001 §5.4`

### Outcomes
| Result | Action |
|---|---|
| All hold | Close `CH-01`; start `BRD-F01` |
| A new edge case found | Add it to `SPEC-001 §5.4` **before** publication, via ADR. Cheap now, impossible later. |
| The two implementations disagree | Stop. Find the cause. Disagreement means `CSD-1` is under-specified, which is fatal for a standard. |

---

## 4. `CH-02` — Do the pinned libraries do what the BRDs assume?

**Status:** CLOSED · **Blocks:** F-06, F-08 · **Cost:** 2 days

### The unknown
Every BRD is a behaviour contract, deliberately written without library call signatures
(`AGENTS.md §4`). That is correct for avoiding hallucinated APIs, but it means several assumptions
are unverified — and they are load-bearing.

### The assumptions to verify, each individually

| # | Assumption | Governing requirement |
|---|---|---|
| A | `sigstore-python` detects the GitHub Actions ambient OIDC credential without manual token handling | `REQ-F06-030` |
| B | The emitted bundle embeds a Rekor inclusion proof that can be verified **offline** | `REQ-F08-070`, `ADR-015` |
| C | Verification can be constrained to an expected certificate identity **and** issuer | `REQ-F08-040` — if this is not possible, the product has no security property |
| D | A Sigstore **staging** environment is usable for tests | `QA-001 §10` |
| E | Sigstore-native DSSE signing and verification interoperate with the Sigstore bundle format without direct `securesystemslib` handling | `REQ-F06-020`, `ADR-020` |
| F | `pygit2` exposes tree-diff with rename detection genuinely off | `REQ-F02-010` |
| G | `rfc8785` output matches a second independent JCS implementation | `REQ-F01-030` |
| H | Pydantic v2 JSON Schema covers required structural constructs; runtime validators enforce non-representable semantic invariants | `REQ-F01-120`, `ADR-021` |

### The experiment
One throwaway script per assumption. Each must **actually run** — reading documentation is not
verification. Assumption C is verified by signing with identity X and confirming verification
**fails** when constrained to identity Y.

### Gate
- [x] All eight verified by executing code against the corrected E and H contracts
- [x] Assumption C demonstrated by a *failing* verification, not a passing one
- [x] Exact working versions recorded; `BOOT-001 §4.1` mandates those exact pins in the first
  `uv.lock` before production feature implementation

### Outcomes
| Result | Action |
|---|---|
| All corrected contracts hold | Close `CH-02`; the amended BRDs are implementable |
| C fails | **Stop everything.** Without identity-constrained verification the product is security theatre (`ADR-004`). Re-evaluate the whole approach. |
| B fails | Offline verification is impossible with the current library; `ADR-015` needs revisiting via a new ADR before F-08 |
| Any other fails | Record the actual behaviour; amend the affected BRD via ADR before implementing |

---

## 5. `CH-03` — Can agent harnesses reliably emit claims?

**Status:** OPEN · **Blocks:** M2 exit · **Cost:** 3 days · **This is `RISK-07`, the highest-scored technical risk**

### The unknown
If harnesses do not emit claims, most attestations record `mode: unknown`. You then ship a
cryptographically impeccable record of nothing. Every other part of the system can be perfect and
the product is still worthless.

### Why documentation cannot close it
`ARCH-001 §7` specifies the sidecar protocol. It does not establish that a hook can reliably fire
at the right moment, capture a session ID, and know which paths were touched — in each harness,
as they exist today.

### The experiment
For each of Claude Code, Cursor, and one CLI agent (Codex or Gemini CLI):

1. Write the smallest hook that writes a sidecar claim on file modification.
2. Use it for a full working week on real work — your own.
3. Measure: what fraction of AI-touched changes produced a claim; whether session IDs are
   obtainable; whether path scope is accurate; how often the hook silently fails.

### Gate
- [ ] At least two harnesses reliably emit claims
- [ ] Claim rate above 90% of AI-touched changes for those harnesses
- [ ] Path scope accurate enough that `ai-assisted` vs `ai-authored` is meaningful
- [ ] Session ID obtainable for at least one harness

### Outcomes
| Result | Action |
|---|---|
| Gate met | Close `CH-03`; hooks become `examples/hooks/` and a headline onboarding asset |
| Only one harness works | Proceed, but scope the product to that harness in GTM and say so plainly |
| No harness emits reliably | **Reconsider the product.** Fall back to review-record attestation only — still real, but a much smaller claim. Record as an ADR and rewrite `MPD-001 §2`. |

### Ongoing metric
Track `mode == "unknown"` share across design partners. Above 50% after onboarding triggers
kill criterion `K4` (`RISK-001 §5`).

---

## 6. `CH-04` — Does the evidence shape satisfy a real auditor?

**Status:** OPEN · **Blocks:** F-12 · **Cost:** 1 week elapsed, ~4 hours of work

### The unknown
The entire compliance thesis rests on assumption `A1` (`RISK-001 §6`): auditors will accept
cryptographic attestations as change-management evidence. Nobody has tested this.

### The experiment
Hand-build a **mock** evidence bundle — `manifest.json`, `summary.md`, one control narrative,
five real attestations, `verify.sh`. No code required beyond `CH-01`/`CH-02` output. Show it to
**two practising auditors** (SOC 2, ideally one with ISO 42001 exposure) and ask three questions:

1. Would you accept this as change-management evidence for AI-generated code?
2. What is missing that you would need?
3. Which control identifiers would you actually cite?

Question 3 supplies the input `ADR-016` defers.

### Gate
- [ ] Two auditors reviewed the mock
- [ ] At least one would accept it, with or without stated additions
- [ ] Control identifiers obtained for at least one framework

### Outcomes
| Result | Action |
|---|---|
| Accepted | Close `CH-04`; mark the mapping `status: reviewed` per `ADR-016`; F-12 can reach DoD |
| Accepted with additions | Add the missing fields to `SPEC-001` via ADR **before** M1 publication if they touch the format |
| Both reject | Kill criterion `K2` territory. The compliance thesis is wrong; re-evaluate against `RISK-001 §5` before building F-12. |

---

## 7. `CH-05` — Will teams enable a blocking gate?

**Status:** OPEN · **Blocks:** M2 exit · Measured, not spiked

Assumption `A2`. A gate nobody sets to blocking is a report, and reports do not get budget.

**Measurement:** of three design partners, how many configure `attest / gate` as a *required*
status check within two weeks of onboarding, unprompted.

**Gate:** at least two of three.

**If not met:** find out whether the obstacle is trust in the tool, false positives, or political.
False positives are fixable; political resistance means the buyer is wrong and `A5` needs
revisiting.

---

## 8. `CH-06` — Will anyone pay, and who signs?

**Status:** OPEN · **Blocks:** M3 exit · Measured

Assumptions `A1` and `A5`, and `RISK-01` — the highest-impact business risk. No hard
willingness-to-pay benchmark exists for this category.

**Measurement:** by day 90, one paid pilot agreed. Record the signer's role.

**Gate:** one pilot, and the signer is compliance/security rather than engineering — confirming
`A5`.

**If not met:** kill criterion `K1` applies at 6 months and 20+ qualified conversations. If the
signer is engineering rather than compliance, the positioning is wrong and GTM changes; the
product does not.

---

## 9. `CH-07` — Will anyone else implement the spec?

**Status:** OPEN · **Blocks:** the standards thesis · Ongoing from M1

The moat is specification ownership, and a specification with one implementation is not a
standard.

**Measurement:** by day 120, either one external implementation exists, or one standards-body
conversation is underway (in-toto, OpenSSF, SLSA community).

**Gate:** one of the two.

**If not met:** kill criterion `K5`. The standards thesis is not working; compete on product
depth — verification strength, policy, evidence export — and stop investing in specification
evangelism.

---

## 10. `CH-08` — Does it hold at monorepo scale?

**Status:** OPEN · **Blocks:** F-02 DoD · **Cost:** 1 day · Week 2

`ARCH-001 §11` targets `CSD-1` under 500 ms for 1,000 changed files. That number is an assertion.

**Experiment:** run the `CH-01` implementation against a monorepo PR touching 1,000+ files;
measure both backends; measure a 10,000-file case.

**Gate:** 1,000-file case under 500 ms; 10,000-file case completes without exhausting memory.

**If not met:** optimise before `F-02` DoD, or amend the target in `ARCH-001` via ADR. Do not
silently ship a slower tool than the document claims.

---

## 11. `CH-09` — Is container cold start acceptable?

**Status:** OPEN · **Blocks:** F-11 DoD · **Cost:** 1 day · Week 8

`REQ-F11-100` requires under 15 s p95. This is the one place the Python decision (`ADR-012`)
carries measurable risk.

**Experiment:** 20 runs of the full Action on a standard runner; record p50 and p95.

**Gate:** p95 under 15 s.

**If not met:** slim the image, defer imports, cache layers. If it remains unacceptable **and**
design partners rank it their top complaint, `ADR-011`'s single trigger fires — verifier only,
recorded as a new ADR. No other route reopens the language question.

---

## 12. Outcome log

Every challenge closes here. An agent reading this document must be able to see, at a glance, what
is settled and what is not.

| ID | Status | Closed on | Outcome | Follow-up ADR |
|---|---|---|---|---|
| `CH-01` | CLOSED | 2026-09-10 | The `pygit2` and Git CLI backends agree across 818 merges and 83,764 entries from five pinned repositories. Identical local reruns match byte-for-byte; GitHub-hosted Ubuntu and macOS result arrays are identical, and the GitHub Linux arrays match the original local run. Canonical raw-byte paths, explicit libgit2 type changes, and every enumerated edge case pass. All 23 sampled squash cases with unchanged entry transitions preserve the `CSD-1` digest; eight additional samples changed an old/new blob transition because the target file changed underneath the PR and correctly produced a different digest. Every entry field is digest-sensitive. Evidence: `Parth2412/attest-csd-conformance` PR #1 and Actions run `34486973511`. | `ADR-018`; `ADR-019` |
| `CH-02` | CLOSED | 2026-09-10 | A/B/C/D/F/G passed by execution. Sigstore 4.5.0 detected ambient GitHub Actions OIDC, signed exact canonical DSSE payload bytes on staging Rekor v2, embedded a complete inclusion proof, verified with the expected identity and issuer, rejected the wrong identity, and verified with network clients blocked. Direct `securesystemslib` 1.5.1 interoperability failed because Sigstore signatures omit its required `keyid`; Sigstore-native `sign_dsse`/`verify_dsse` passed and is now the sole boundary. Pydantic 2.13.5 runtime validation rejected the cross-field digest mismatch that generated JSON Schema consumed by jsonschema 4.26.0 accepted, establishing the structural/semantic split. The bundle carried a leaf `certificate`; the trusted root supplied the chain. Exact validated baselines: pygit2 1.20.0, rfc8785 0.1.4, sigstore 4.5.0, Pydantic 2.13.5, jsonschema 4.26.0. Evidence: `Parth2412/attest-csd-conformance` PR #2/run `34490185022` (staging flow) and PR #3/run `34495967107` (durable boundary proofs), merged as `99d768f` and `334b4d0`. | `ADR-020`; `ADR-021` |
| `CH-03` | OPEN | — | — | — |
| `CH-04` | OPEN | — | — | — |
| `CH-05` | OPEN | — | — | — |
| `CH-06` | OPEN | — | — | — |
| `CH-07` | OPEN | — | — | — |
| `CH-08` | OPEN | — | — | — |
| `CH-09` | OPEN | — | — | — |

---

## 13. Week 0 plan — the five days before production code

| Day | Work | Closes |
|---|---|---|
| 1 | `CSD-1` throwaway implementation; run on 3 repositories | `CH-01` (part) |
| 2 | Cross-machine and cross-OS reproduction; `git`-CLI cross-check; edge cases → ADR if found | `CH-01` |
| 3 | Sigstore assumptions A–E; **A/B/C are the critical ones** | `CH-02` (part) |
| 4 | Assumptions F–H; pin working versions | `CH-02` |
| 5 | Write the three harness hooks; begin the week of real use; hand-build the mock evidence bundle and email two auditors | `CH-03` starts, `CH-04` starts |

At the end of day 5 you know whether the digest is sound, whether the libraries support the
security property, and whether claims can be captured. Only then does `BOOT-001` bootstrap and
`BRD-F01` begin.

**None of this week's output is production code. All of it is throwaway.** That is intentional —
throwaway code that kills a bad assumption is the highest-return work available right now.

---

## 14. What is deliberately not a challenge

So nobody spends time here:

| Not a challenge | Why |
|---|---|
| Whether authorship claims are true | Unknowable by design (`ADR-003`) |
| Whether reviewers understood the code | Unknowable |
| Python vs TypeScript | Closed (`ADR-012`); one bounded trigger in `ADR-011` |
| Storage backend choice | Closed (`ADR-014`) |
| Licence | Closed (`ADR-017`) |
| Whether to add a blockchain | Closed (`ADR-009`) |
| Whether to detect AI code statistically | Permanently out of scope (`OOS-05`) |
