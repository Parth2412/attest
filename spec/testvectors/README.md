# Normative test vectors

This directory contains the plain-file conformance vectors required by `SPEC-001 §12`.

- `jcs-canonical/cases.json` contains JSON values and their exact RFC 8785 UTF-8 output.
- Each `csd1-*` directory contains `input.json` entries and an independently calculated
  `expected.sha256`. Stability-vector `contexts` are metadata and are deliberately excluded from
  the ChangeSet Record.
- `statement-valid/input.json` is the fully populated v0.1 Statement.
- `statement-invalid-schema-cases/cases.json` applies structural mutations that both JSON Schema
  and runtime validation must reject.
- `statement-invalid-semantic-cases/cases.json` applies invariants intentionally enforced only by
  runtime validation.

The CSD-1 expected values were calculated independently from the Python implementation using the
normative record shape and RFC 8785 procedure. They are fixed interoperability fixtures and must
never be regenerated merely to satisfy a failing test. BRD-F02 adds real-repository extraction
coverage without changing these vectors.
