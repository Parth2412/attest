# GitHub REST fixtures

These sanitized response-shape fixtures are pinned to GitHub REST API `2026-03-10`. They retain
the complete object supplied to the collector tests so evidence digests can be recomputed from the
fixture itself. Names, IDs, URLs, and bodies are non-secret test values.

Pagination, authentication, rate-limit, malformed-response, and server-failure variants are built
from these objects in tests so the default suite never performs a network request. The dedicated
`e2e-github` workflow is the only live forge test.
