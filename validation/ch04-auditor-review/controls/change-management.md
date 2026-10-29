# Candidate Change-Management Evidence Narrative

> **DRAFT — PRACTITIONER REVIEW REQUIRED**
>
> This narrative is unreviewed. Its framework, control identifier, and authoritative control text
> are deliberately unassigned. It must not be represented as a reviewed control mapping.

| Mapping field | Value |
|---|---|
| Framework | Practitioner to identify |
| Control identifier | Unassigned |
| Status | `draft-unreviewed` |
| Reviewed by | `null` |
| Reviewed at | `null` |
| Authoritative control text | Not yet supplied |

## Candidate evidence objective

For a selected code ChangeSet, provide independently verifiable evidence that:

1. the named paths and Git object identities are bound to a deterministic ChangeSet Digest;
2. any declared AI contribution is recorded as a self-reported Authorship Claim with a bounded
   path scope;
3. forge-reported human review is preserved as a Review Record with reviewer identity, time, and
   whether the reviewer was the change author; and
4. the signed Statement is bound to a CI workload identity and embedded transparency-log evidence;
   and
5. a future emergency Policy exception can preserve the Decision Owner, reason, deadline, and
   later retrospective-review disposition without rewriting the original denied Decision.

This is a product evidence objective, not quoted or paraphrased framework text. A practitioner must
decide whether it supports a real control and provide the authoritative citation.

## Evidence references

### Review transition for ChangeSet `7356fbb…`

- `../attestations/e39d6cb916ca81bb5beaf07048e3f28c74b9142b5e34d9bc91d4aafc6d988533.sigstore.json`
  records `review.state: none` and zero effective human approvals.
- `../attestations/e60df59e1a27fbe7c42b4d7ad484acadbbd8a0ff96937faeb9a371d7d7bde843.sigstore.json`
  binds the same ChangeSet Digest to an effective non-author Review Record.

### Later approved ChangeSet `ed8d845…`

- `../attestations/1e43cd876d32233989e7561fb01a182b3d55ac847edc7c7433c07c4e72628654.sigstore.json`
  supplies a second real approved ChangeSet from the public proof repository.

### Claim-bearing review transition for ChangeSet `9b36957…`

- `../attestations/ef80b71e6031013075e669a593cdf8f5939a18213d2e4d76024b46f2099ae70d.sigstore.json`
  records one scoped `codex-cli` Authorship Claim and no Review Record approval.
- `../attestations/7a6a5ec34871032dee948b244180a214223a9fcb6a99feb33fed5355c0b90f96.sigstore.json`
  binds the same ChangeSet Digest and claim to an effective non-author Review Record.

### Synthetic policy-exception lifecycle

> These files are unsigned validation examples. They are not real exception decisions and are not
> presented as cryptographically verified evidence.

- `../policy-exceptions/validation-exception-001-authorized.json` proposes an emergency
  authorization bound to the claim-bearing ChangeSet, a denied Policy Decision, stable requester
  and Decision Owner identities, reason, deployment, forge-source digest, and review deadline.
- `../policy-exceptions/validation-exception-001-reviewed.json` preserves a later append-only
  retrospective-review event. It links the exact authorization-file digest and the real approved
  Bundle for the same ChangeSet.
- `../policy-exceptions/validation-exception-002-authorized.json` has no closure and is overdue at
  the fixed mock generation timestamp.
- `../policy-exceptions/validation-exception-003-authorized.json` has no closure but remains open
  because its deadline has not elapsed.

The examples deliberately separate Policy exceptions from unattested or unverifiable changes.
They ask whether these records, once signed by a trusted workflow, would be usable in testing an
emergency change-management path.

## Practitioner decisions requested

- Is this evidence objective usable for change-management testing?
- Which framework and exact control identifier, if any, should cite these records?
- What authoritative control text or source should the mapping cite?
- Which additional fields, exceptions, population evidence, or sampling context are required?
- Does the proposed Policy Exception Record lifecycle contain the decision and closure evidence
  required for an emergency release?
- Should overdue retrospective review block subsequent releases, trigger escalation, or remain an
  organisation-defined Policy choice?
