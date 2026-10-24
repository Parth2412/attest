# Product Marketing Context

*Last updated: 2026-10-24*

## Product Overview

**One-liner:** attest is an open-source, CI-native provenance toolchain that binds declared
AI-authorship claims and forge-sourced Review Records to a deterministic ChangeSet, then signs and
verifies that evidence with a CI workload identity.

**What it does:** attest collects Authorship Claims and GitHub Review Records, builds a versioned
in-toto Statement, signs it keylessly with Sigstore, stores the resulting Bundle, verifies both the
signature and expected Signing Identity, and evaluates a declarative merge policy. F-01 through
F-11 are implemented; auditor-facing Evidence Bundle export (F-12) is not yet implemented.

**Product category:** developer security tooling; software provenance; CI policy enforcement;
compliance-enabling engineering evidence.

**Product type:** Apache-2.0 open-source CLI, Python libraries, container image, and GitHub Action.

**Business model:** The current product is free and open source. Pricing is not set. The documented
commercial hypothesis is to keep the verification standard and developer entry point open, validate
the category with design partners, then sell an auditor-facing evidence and operational layer. No
paid demand or pricing claim is validated yet.

## Target Audience

**Target companies:** GitHub-based software organisations adopting AI coding tools and facing
change-management, customer-assurance, or audit-evidence requirements. Initial validation should
focus on security-conscious startups and regulated software teams where a platform engineer can
adopt a CI gate without a long procurement cycle.

**Decision-makers:** Platform/DevSecOps engineering is the initial user and champion. Engineering
leadership is the technical influencer. Compliance, GRC, or security leadership is the hypothesised
economic buyer. A practising auditor is the independent validator.

**Primary use case:** Produce durable, independently verifiable evidence of which Authorship Claims
and Review Records were present for one exact ChangeSet, and enforce the organisation's policy in
CI.

**Jobs to be done:**

- Add signed, identity-bound provenance to a GitHub pull-request workflow.
- Require declared authorship and independent human review through a blocking policy check.
- Re-verify a Bundle later without trusting a mutable dashboard or the original CI runner.
- Eventually hand an auditor a control-mapped Evidence Bundle; this remains gated by CH-04/F-12.

**Use cases:**

- Enforce review policy for ChangeSets carrying AI-authorship claims.
- Preserve a transparent chain of custody for incident review and customer assurance.
- Complement build provenance by covering the authoring and review stages before a build exists.
- Test an organisation's AI-development controls without storing raw prompts.

## Personas

| Persona | Cares about | Challenge | Value we promise |
|---------|-------------|-----------|------------------|
| Platform / DevSecOps engineer | Reliable CI, low adoption friction, deterministic failures | Security asks for evidence that current source-control metadata cannot supply | A pinned GitHub Action, stable exit codes, and policy-as-code |
| Engineering lead | Review quality and throughput | Increasing change volume makes informal review controls hard to defend | A visible, enforceable review requirement tied to the exact ChangeSet |
| Compliance / GRC lead | Evidence quality and independent verification | Screenshots and mutable dashboards are weak long-lived evidence | Signed Bundles that can be re-verified; control-mapped export is planned, not shipped |
| External auditor | Traceability, scope, limitations, reproducibility | Vendor assertions are difficult to validate independently | Public specification, exact identity verification, and explicit limitations |

## Problems & Pain Points

**Core problem:** Git records commits and forges record reviews, but neither creates one durable,
cryptographically bound record connecting a ChangeSet, declared AI contribution, human review, and
the CI identity that observed them.

**Why alternatives fall short:**

- Usage dashboards and trailers are useful signals but are mutable or vendor-scoped when used
  alone.
- AI review tools assess code; they do not preserve the same provenance record.
- Build-provenance systems start after authoring and review; attest is complementary to them.
- Manual audit packs are slow to assemble and difficult to reproduce.

**What it costs them:** Manual evidence collection, inconsistent policy enforcement, longer security
questionnaires, and uncertainty during audits or incident reviews. These costs are hypotheses until
measured with design partners.

**Emotional tension:** The organisation is using AI-assisted development faster than its evidence
and review controls are evolving, while security and compliance teams still need precise answers.

## Competitive Landscape

**Direct:** No direct category winner is established in the project evidence. Refresh competitor
research before publishing comparative claims.

**Secondary:** AI-usage analytics, AI code-review tools, build-provenance platforms, and native forge
metadata each solve adjacent parts of the problem but not the complete authoring-to-review evidence
boundary defined by attest.

**Indirect:** Manual evidence collection, ticket screenshots, commit conventions, and accepting the
risk without a dedicated control.

## Differentiation

**Key differentiators:**

- A public, versioned predicate and normative test vectors.
- Deterministic ChangeSet identity based on Git object identities.
- Verification constrained by both certificate identity and issuer.
- Keyless Sigstore signing with transparency-log evidence.
- A declarative policy decision distinct from cryptographic verification.
- No raw prompt storage and no statistical inference about source authorship.
- Exact, immutable Action releases pinned to reviewed multi-platform image digests.

**How we do it differently:** attest records declared claims and forge-sourced Review Records,
binds them to one ChangeSet, and makes the resulting Bundle independently verifiable.

**Why that's better:** The evidence survives beyond a dashboard session, preserves explicit trust
boundaries, and can be evaluated consistently by CI and later reviewers.

**Why customers choose us:** This remains an external-validation question. The working hypothesis
is precision, cross-vendor neutrality, open verification, and an evidence-first security model.

## Objections

| Objection | Response |
|-----------|----------|
| A contributor can make a false Authorship Claim. | Correct. Claims are self-reported; attest records when and where a claim was observed and signed. It does not infer forensic truth. |
| We already have SLSA/build provenance. | Keep it. attest covers authoring and review; build provenance covers the build. The records are complementary. |
| This creates another blocking CI dependency. | Start in observation mode, measure failure causes, then require the check only when the policy and operational ownership are ready. |
| We need an audit report today. | F-12 export is intentionally unpublished until practising-auditor validation closes CH-04. Do not sell that capability yet. |

**Anti-persona:** Teams seeking statistical source-code classification, automatic code-quality
review, raw prompt surveillance, or a vendor assertion that substitutes for their own policy and
auditor judgement.

## Switching Dynamics

**Push:** Manual evidence work, inconsistent review enforcement, customer questionnaires, or an
audit finding.

**Pull:** Open verification, identity-bound signatures, policy-as-code, immutable releases, and a
GitHub-native adoption path.

**Habit:** Existing commit conventions, screenshots, dashboards, and informal review processes are
familiar and appear free.

**Anxiety:** CI friction, Sigstore availability, what the evidence actually establishes, exposure of
repository metadata, and whether an auditor will accept the future export shape.

## Customer Language

**How they describe the problem:** No verbatim customer language is recorded yet. Collect exact
phrasing during CH-04 auditor reviews and the first three design-partner onboardings.

**How they describe us:** No customer quote or independently supplied category description is
recorded yet.

**Words to use:** signed provenance, declared Authorship Claim, Review Record, deterministic
ChangeSet, identity-bound verification, tamper-evident, audit evidence, policy gate, independently
verifiable.

**Words to avoid:** Follow the over-claiming restrictions in `GLOSS-001 §2.2` without exception.
Do not imply statistical source classification, forensic certainty, or an automatic compliance
determination.

**Glossary:**

| Term | Meaning |
|------|---------|
| Authorship Claim | A self-reported assertion that a human or agent contributed to a ChangeSet |
| ChangeSet | File-level changes represented by Git object identities |
| Review Record | Forge-sourced evidence of a reviewer's conclusion and timestamp |
| Bundle | A Sigstore Bundle containing the signed envelope and verification material |
| Signing Identity | The expected workflow identity and OIDC issuer bound to verification |
| Decision | The policy output: allow, warn, or deny |

## Brand Voice

**Tone:** Precise, transparent, calm, security-literate, and evidence-led.

**Style:** Lead with what is verifiable. Separate shipped capability from planned work. Explain the
trust boundary in plain language. Prefer exact versions, identities, and links over adjectives.

**Personality:** Rigorous, honest, pragmatic, independent, and technically credible.

## Proof Points

**Metrics:**

- F-01 through F-11 are implemented and evidence-backed.
- Six Python distributions, a multi-platform image, and immutable Action `v1.0.6` are public.
- The `v0.1.6` release includes SBOM, provenance, scan, verification, public-package, performance,
  and dogfood evidence.
- Three 20-sample hosted cold-start runs measured p95 values of 16, 14, and 13 seconds; the combined
  p95 was 16 seconds, below the strict 18-second release SLO.
- Public proof PR #11 passed after independent review; fork proof PR #12 failed before receiving
  signing or write authority.
- The full local release-closure suite passed with 1,313 tests, two skips, and 23 deselections.

**Customers:** No customer or design-partner logo is validated for public use.

**Testimonials:** No testimonial is validated for public use.

**Value themes:**

| Theme | Proof |
|-------|-------|
| Verifiable chain of custody | Versioned specification, deterministic ChangeSet digest, Sigstore Bundle, identity-constrained verification |
| Fail-closed enforcement | Stable semantic exits, declarative policy, protected public proof |
| Supply-chain discipline | SHA-pinned Actions, digest-pinned multi-platform image, SBOM, provenance, scans, immutable tags |
| Honest scope | Explicit limitations, banned over-claiming, F-12 withheld until auditor validation |

## Goals

**Business goal:** Validate that signed authoring/review provenance is accepted as useful evidence,
earn adoption in three external repositories, and convert one validated design partner into a paid
pilot before investing in a hosted product.

**Conversion action:** Install the pinned Action in a real repository, make the `attest` job a
required check after validation, and provide onboarding feedback. Auditors should review the CH-04
mock Evidence Bundle and answer the three recorded validation questions.

**Current metrics:** Internal engineering and public release gates are complete through F-11.
CH-03, CH-04, external M2 adoption, and M3 paid-pilot evidence remain open. No adoption, customer,
or revenue number should be stated until recorded in the project evidence.
