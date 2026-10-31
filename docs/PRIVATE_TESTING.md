# Private testing policy — checkpoint52

Only PRIVATE use of giangi1986/ha-virtavo-ip360 is authorized. The repository was created privately; browser account/Private visibility verified. The source mirror now includes the runtime, documentation, evidence, tests, tools and CODEOWNERS. Final workflow and metadata reconciliation, clean runner checks and whole-tree byte verification are pending. The complete prepared integration and scrubbed Git history are delivered as ZIP and bundle. No public visibility, release, force-push or production change is authorized.

Standard HACS cannot use private GitHub repositories: https://hacs.dev/docs/faq/private_repositories/ and https://hacs.dev/docs/publish/start/. Manual ZIP staging and HA loader/stream tests are separate evidence, not a successful HACS download. No HACS fork, hidden token, permission workaround or public exposure is used.

Use tools/stage_install.py ARCHIVE --parent EMPTY_TEST_PARENT for an isolated configuration; it never overwrites an existing config or starts services. It rejects unsafe paths, symlinks, duplicates, oversized/unexpected assets and inconsistent runtime hashes. Hashes establish consistency, not publisher authenticity. Keep production HA and cameras outside these tests.

The private audit ran and the user supplied its matching artifact.39 records affect upstream HA-pinned Pillow12.3.0. They remain recorded. Stable current/minimum compatibility and bounded image-API guards are documented in DEPENDENCY_SECURITY.md; no additional pip dependency or prerelease HA is required. The old preview audit is separate historical evidence.

Before later remote writes verify the exact account and private visibility, preserve history/content and upload only depurated source. The native GitHub connection returned404 at the last private-repo check; do not assume the valid browser login grants that connection access. Do not broaden permissions or change visibility implicitly. Private audit artifacts expire after7days; relevant report data and results are preserved in the source/checkpoint backups.

The manual Private source integrity workflow compares every tracked file (except its own hash inventory) with SOURCE_TREE_SHA256.json, checks all35 runtime files and validates publication metadata. It has read-only permissions, requires this exact private repository and cannot publish. Documentation-only updates do not rerun the media suite; code, test, tool, requirement and relevant configuration changes do.
