# attest — 90-Day Roadmap

| Field | Value |
|---|---|
| Document ID | `ROADMAP-001` |
| Version | `1.3.0` |
| Status | Baselined |
| Last updated | 2026-09-16 |

---

## 1. Shape of the plan

Three milestones, each with a binary exit criterion. The criteria are deliberately external —
something works in a real repository, or a real person confirms something — because internal
"feature complete" judgements are unreliable.

| Milestone | Window | Theme | Exit criterion |
|---|---|---|---|
| **M1** | Days 0–30 | Signed core | A signed attestation is produced in real CI and verifies on a clean machine. Spec published. |
| **M2** | Days 31–60 | Enforcement | A policy violation blocks a real merge. Three external repositories running it. |
| **M3** | Days 61–90 | Evidence | An auditor confirms an exported bundle is usable. One paid pilot agreed. |

---

## 1.1 Week 0 — validation before code (NORMATIVE)

Five days, throwaway code only, before the scaffold exists. Specified in `CHALLENGE-001 §13`.

| Day | Work | Closes |
|---|---|---|
| 1–2 | `CSD-1` spike against five real repositories, two machines, two OSes, cross-checked against `git` CLI | `CH-01` |
| 3–4 | Verify eight Sigstore/library assumptions by executing code, especially identity-constrained verification | `CH-02` |
| 5 | Write three harness hooks, start a week of real use; hand-build a mock evidence bundle and contact two auditors | `CH-03`, `CH-04` start |

**Gate:** `CH-01` and `CH-02` must be closed in `CHALLENGE-001 §12` before bootstrap. `CH-03` and
`CH-04` run in parallel with M1 and gate the M2 and M3 exits respectively.

The 90-day count starts after Week 0.

---

## 2. M1 — Signed core (Days 0–30)

### Week 1 — Foundation
- Repository scaffold per `BOOT-001` — every file, zero logic; verify against `BOOT-001 §16`
- `F-01` models and enums; canonicalisation via `rfc8785`
- Author the first test vectors: `jcs-canonical`, `csd1-empty`, `csd1-single-add`

**Done when:** `just check` green; canonicalisation vectors pass.

### Week 2 — Digest and git
- `F-01` `CSD-1` implementation plus property tests
- `F-02` `GitBackend` protocol, `pygit2` implementation, git fixtures
- Remaining `csd1-*` vectors including unicode, submodule, symlink, ordering

**Done when:** all `csd1-*` vectors pass from real repositories.

### Week 3 — Claims, builder, signing
- `F-03` sidecar, trailer, git-note collectors
- `F-05` builder plus golden-file test
- `F-06` signing against **Sigstore staging**
- `F-02` subprocess backend; both backends pass the full matrix

**Done when:** a Statement is signed in staging and a bundle is produced.

### Week 4 — Verification and public specification
- `F-08` full pipeline plus the adversarial suite
- Publish `SPEC-001` publicly; open an RFC issue inviting review
- Prepare the verified library boundary for F-09 and the CLI composition root

**M1 exit gate:**
- [x] `CH-01` and `CH-02` closed in `CHALLENGE-001 §12` on 2026-09-10
- [ ] A real GitHub Actions fixture produces a signed attestation logged to the transparency log
- [ ] The F-08 API validates it on a clean container with no local state
- [x] Adversarial suite green
- [ ] `SPEC-001` and test vectors public
- [x] Verified signer and transparency-log evidence are ready for policy consumption

---

## 3. M2 — Enforcement (Days 31–60)

### Week 5 — Review collection
- `F-04` GitHub adapter, recorded fixtures, token-leak test
- Wire `review` into the predicate; extend golden files

### Week 6 — Storage
- Close `OQ-02` with an ADR
- `F-07` git-ref, filesystem, and OCI backends; shared conformance suite

### Week 7 — Policy and gate
- `F-09` policy schema, evaluator, decision reporting
- Decision-table tests across every predicate
- Complete `REQ-F04-150` GitHub ChangeSet context and `REQ-F08-170` parse-only inspection
- `F-10` `init`, `run`, `verify`, `inspect`, `doctor`, and `gate`; exit codes frozen

### Week 8 — Action and design partners
- `F-11` closed-interface container Action, injection-safe job summary, and quickstart
- Two-phase multi-platform image candidate and protected release; publish the six implemented
  `0.1.0` distributions through PyPI Trusted Publishing and Action `v1.0.0`/`v1`
- Dedicated public-repository and `zettacore-labs` fork proof; retain required-check and timing evidence
- Onboard three external design partners
- First public write-up: "We signed every PR for a month — here is what the auditor saw"

**M2 exit gate:**
- [ ] `CH-03` closed: at least two harnesses emit claims reliably
- [ ] `CH-05` measured: at least two of three partners enabled a blocking gate
- [ ] `CH-08`, `CH-09` closed
- [ ] A policy violation blocks a merge via a required status check in a real repository
- [ ] Three external repositories running the Action in CI
- [ ] Quickstart works unmodified on a fresh repository
- [ ] Onboarding friction documented from real partner feedback
- [ ] Product `0.1.0` is published as the six approved PyPI distributions and immutable
  multi-platform GHCR image; Action `v1.0.0`/`v1` is published and the release verifies its own
  attest evidence

---

## 4. M3 — Evidence (Days 61–90)

### Week 9 — Auditor input
- Close `OQ-04`: interview two practising auditors; confirm control identifiers
- Draft control mapping files; do **not** guess mappings

### Week 10 — Export
- `F-12` manifest, per-control narratives, `verify.sh`, exceptions section
- Determinism and no-source-code tests

### Week 11 — Validation
- Generate a real bundle from a design partner's repository (with permission)
- Auditor review; incorporate feedback
- Harden limitations language

### Week 12 — Commercial
- Package the paid tier proposition; price it
- Convert one design partner to a paid pilot
- Publish the auditor-validated evidence walkthrough
- Ship `v0.4.0`

**M3 exit gate:**
- [ ] `CH-04` closed: an auditor accepted the evidence shape
- [ ] `CH-06` measured: one paid pilot, signer's role recorded
- [ ] A practising auditor confirms in writing the bundle is usable as change-management evidence
- [ ] `verify.sh` reproduces verification in a clean container
- [ ] One paid pilot agreed
- [ ] Adoption and conversion data collected against `RISK-001` thresholds

---

## 5. Sequencing rules

| Rule |
|---|
| Build in the `BRD-INDEX §2` order. Later features consume earlier contracts. |
| Do not start a feature whose blocking `CH-` is open (`CHALLENGE-001 §2`). All `OQ-` are closed. |
| Do not start M3 export work before auditor input. Guessed control mappings are worse than none. |
| Publish the specification at M1, not later. Standard ownership is the moat and it decays with time. |
| Dogfood from the first commit. |

---

## 6. What is deliberately not in the 90 days

| Deferred | Why |
|---|---|
| Hosted evidence store | v1.0's decentralisation is an adoption advantage; do not become a service early |
| Web dashboard | Not what the buyer is buying |
| GitLab/Bitbucket | GitHub-first; breadth after depth |
| Solidity plug-in | Beachhead credibility play, not core; after product-market signal |
| Single static binary | Container solves distribution adequately for now (`TECH-001 §1.2`) |
| Fundraising | Better with M3 evidence and a paid pilot in hand |

---

## 7. Weekly review questions

Answer these honestly every Friday. They are designed to surface a dying project early.

1. What did a real external user do with attest this week?
2. Which `OQ-` did I close, and which did I avoid?
3. Did I add anything untraceable to a `SCOPE-` item?
4. Did any kill criterion in `RISK-001` move closer?
5. Did I change a normative document without an ADR?
