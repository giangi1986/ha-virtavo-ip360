# Testing and visibility policy — checkpoint56

The repository is public solely for the owner-authorized HACS installation test. No release, public tag or community announcement has been created. Wider release/announcement authorization remains separate. Production HA and cameras were not modified.

The repository was initially private. The owner separately authorized public visibility after final security/history/license and recoverable-backup checks. Standard HACS does not support private repositories: https://hacs.dev/docs/faq/private_repositories/. Historical manual staging/offline fixtures are distinct from the subsequently successful real remote installation.

The final candidate passes190 tests on stable HA2026.10.4 and27 targeted HA/security-scope tests on minimum2026.10.0. All10 official HACS action checks pass. Unmodified HACS2.0.5 methods register the actual GitHub repository, download its real archive and install37 byte-matching files into an empty HA configuration. Real HA then registers the camera, consumes the on-demand endpoint and unloads. HACS browser UI/OAuth startup and physical browser playback are not tested. Account/receiver I/O in the HA acceptance phase uses local fixtures; actual device operation is separate preserved evidence. GitHub uses a short-lived read-only Actions token, not camera credentials. See evidence/FINAL_ACCEPTANCE.json and evidence/HACS_REMOTE_INSTALL.json for exact revisions and run/job links.

Use tools/stage_install.py ARCHIVE --parent EMPTY_TEST_PARENT only with a disposable test parent. It creates a new configuration, rejects unsafe/corrupted/unexpected assets and never starts or overwrites existing services. Hashes establish consistency, not publisher authenticity. Developer requirements are for isolated environments, not a working household HA installation.

Preserve history and source/Git backups, and retain redacted CI evidence before temporary Actions artifacts expire. Never upload private operational history, captures, SDK files, recordings or credentials. Do not override HA dependencies or require a prerelease for this beta.
