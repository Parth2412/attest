# attest — Risk Register and Kill Criteria

| Field | Value |
|---|---|
| Document ID | `RISK-001` |
| Version | `1.0.0` |
| Status | Baselined |
| Last updated | 2026-07-25 |

---

## 1. How to use this

Review monthly. A risk is only useful if it has a **threshold** and a **pre-committed response**.
Deciding what would make you stop, before you are emotionally invested, is the entire point.

Severity = Impact × Likelihood, scored 1–5 each.

---

## 2. Strategic risks

### RISK-01 — The market does not pay for provenance
**Impact 5 · Likelihood 3 · Score 15**

Provenance may remain a "should have" that never gets a budget line. No hard willingness-to-pay
benchmark exists for this exact category — the adjacent evidence is investor conviction in
supply-chain security, not customer invoices.

*Signals:* free CLI adopted, zero conversion; buyers say "interesting" and never return; requests
to bundle it free into something else.

*Mitigation:* lead with the auditor, not the developer. Sell the evidence bundle, not the CLI.
Get an auditor to say "yes, I would accept this" early — that sentence is the product.

**Kill criterion:** free adoption but zero paid conversion after 6 months and 20+ qualified
enterprise conversations → pivot to the eval-gate runner-up idea.

---

### RISK-02 — Regulatory urgency softens
**Impact 4 · Likelihood 3 · Score 12**

If EU AI Act high-risk obligations are deferred, the forcing function weakens.

*Mitigation:* the pitch must stand on SOC 2 CC8.1 and ISO 42001 alone. Test this explicitly: if a
prospect will not engage without the EU deadline, the value proposition is too thin.

**Kill criterion:** deferral confirmed **and** no design partner treats SOC 2 AI-code evidence as
budgeted within 90 days.

---

### RISK-03 — GitHub ships it natively
**Impact 5 · Likelihood 2 · Score 10**

GitHub already has co-author trailers and attestation infrastructure. Adding signed authorship
provenance is plausible.

*Mitigation:* cross-vendor neutrality and specification ownership. Vendor-native attribution
becomes an *input* to attest, not a replacement — unless it is cross-vendor **and** signed **and**
audit-exportable.

**Kill criterion:** GitHub ships cross-vendor, signed, audit-exportable provenance before ~50
paying organisations → reposition as the policy and evidence layer on top of it, or wind down.

---

### RISK-04 — An incumbent adds signing
**Impact 4 · Likelihood 3 · Score 12**

Git AI already owns the unsigned-analytics frame and could add Sigstore.

*Mitigation:* speed on the specification, and depth on the parts they are not built for —
verification strength, policy gating, auditor-facing export.

**Kill criterion:** a well-funded incumbent ships an equivalent signed predicate with adoption
before your spec has an external implementation → compete on the compliance layer only.

---

### RISK-05 — The claim model is too honest to sell
**Impact 3 · Likelihood 3 · Score 9**

Competitors will say "we detect AI code" — a stronger-sounding claim. attest says "we record
claims".

*Mitigation:* make the honesty the pitch. Auditors and security engineers reward precision and
punish over-claiming. Never soften `ADR-003` to win a deal; a customer won on an over-claim is a
lawsuit waiting to happen.

**Response if it bites:** improve claim *coverage* (make emission effortless everywhere) rather
than weakening the claim.

---

## 3. Technical risks

### RISK-06 — Digest algorithm proves wrong after publication
**Impact 5 · Likelihood 2 · Score 10**

A flaw discovered post-adoption is expensive; old attestations must still verify.

*Mitigation:* extensive vectors before publication; versioned algorithm (`CSD-N`); permanent
verification support for old versions.

---

### RISK-07 — Claim coverage is too low to be useful
**Impact 4 · Likelihood 4 · Score 16 — highest technical risk**

If harnesses do not emit claims, most attestations say `unknown`, and the product records
nothing interesting.

*Mitigation:* make emission trivially easy — one-line hooks per harness, shipped as examples;
read every existing convention (trailers, notes, vendor metadata); make `claimsRequired` a policy
so organisations can enforce emission internally.

**Watch metric:** share of attestations with `mode == "unknown"` across design partners. Above
~50% after onboarding, the integration story is failing.

---

### RISK-08 — Python distribution friction blocks adoption
**Impact 3 · Likelihood 3 · Score 9**

*Mitigation:* container-first, Action-wrapped, so users never touch Python.

**Trigger:** if installation is the top complaint from design partners, rewrite the **verifier**
only in Go (`TECH-001 §1.3`) and record it as an ADR.

---

### RISK-09 — Sigstore dependency risk
**Impact 4 · Likelihood 2 · Score 8**

Outage, breaking change, or policy change upstream.

*Mitigation:* wrap behind the internal `Signer` protocol; support offline trust roots; keep
long-lived-key signing as a documented fallback.

---

### RISK-10 — Forgeable claims exploited to discredit the product
**Impact 3 · Likelihood 2 · Score 6**

Someone demonstrates a forged claim and calls the product worthless.

*Mitigation:* say it first, loudly, in the specification and the README. A limitation you
documented is a design decision; a limitation someone else discovers is a scandal.

---

## 4. Execution risks

### RISK-11 — Solo founder bandwidth
**Impact 4 · Likelihood 4 · Score 16**

Cryptography, git internals, compliance mapping, GTM, and standards engagement is a lot for one
person.

*Mitigation:* the MVP is small because the primitives are mature libraries. Ruthless scope
discipline via `SCOPE-xx` traceability. Defer everything in `MPD-001 §3.2`.

**Watch:** if M1 slips past day 45, cut `F-07` OCI backend and `F-11` polish rather than extending
the timeline.

---

### RISK-12 — Specification and implementation drift
**Impact 4 · Likelihood 3 · Score 12**

The strategic asset is the spec; drift makes it worthless.

*Mitigation:* generated schema with a CI drift check; normative test vectors that may never be
regenerated to pass; ADR requirement for normative changes.

---

### RISK-13 — Over-claiming creeps into marketing
**Impact 4 · Likelihood 3 · Score 12**

Marketing pressure pushes toward "detects AI code" and "ensures compliance".

*Mitigation:* the banned-language CI check covers docs and generated output, not just code.

---

## 5. Kill criteria summary

Pre-committed. Review monthly against these; do not renegotiate them in the moment.

| # | Condition | Response |
|---|---|---|
| K1 | No paid conversion after 6 months and 20+ qualified enterprise conversations | Pivot to the CI-native eval-gate idea |
| K2 | EU deferral confirmed **and** no budgeted SOC 2 interest in 90 days | Reassess the entire compliance thesis |
| K3 | GitHub ships cross-vendor signed provenance before ~50 paying orgs | Reposition as the layer above, or wind down |
| K4 | `mode == "unknown"` above 50% at design partners after onboarding | Integration story failing; fix coverage before anything else |
| K5 | No external spec implementation or standards engagement by day 120 | Standard-ownership thesis is not working; compete on product only |
| K6 | M1 not complete by day 45 | Cut scope, do not extend timeline |

---

## 6. Assumption log

The plan rests on these. Each should be actively tested, not assumed.

| # | Assumption | How to test |
|---|---|---|
| A1 | Auditors will accept cryptographic attestations as evidence | Show a mock bundle to two auditors before building `F-12` |
| A2 | Teams will run a blocking gate rather than a report | Ask design partners to enable blocking in M2, and see who actually does |
| A3 | Harness vendors will not lock down claim emission | Monitor; the file-drop protocol needs no cooperation, which is the hedge |
| A4 | Cross-vendor neutrality is valued over native integration | Ask directly during design-partner interviews |
| A5 | The buyer is compliance, not engineering | Track who actually signs the pilot |
