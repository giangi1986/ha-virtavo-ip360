# Official HACS offline repository-engine check

Publication requirement: verify the prepared tree is selected and copied by the real HACS integration-repository engine, rather than relying only on our staging tool. This check uses separately supplied official HACS2.0.5 source, commitc0dfd8b44297c3673c21973e2539375a53687a9c, checked clean; no HACS source or dependency is bundled into Virtavo. Module hashes are recorded in evidence/HACS_OFFLINE_ENGINE.json.

The official repository modules run unmodified in an isolated temporary HA2026.10.4 and2026.10.0 configurations. The HACS package entrypoint/frontend is not started (the source tag does not include generated frontend assets). GitHub metadata, API responses and archive transport are in-memory local fixtures from the prepared ZIP. HACS's actual manifest schemas, common validation, integration manifest/path selection, branch fallback and repository ZIP selection/extraction execute. No Virtavo remote repository or camera is accessed.

Result: selected custom_components/virtavo,35 runtime files copied byte-for-byte, no README/docs installed. The actual HA loader then loads the HACS-extracted component, registers its camera, starts its owned on-demand producer when consumed, and unloads cleanly using existing external-account/receiver fixtures. No SDK, PCAP, Unicorn or extra Virtavo pip requirement.

Reproduce with the declared stable test environment, FFmpeg, a clean clone of the official HACS2.0.5 tag and a trusted source archive built by tools/build_repository.py:

```bash
python -I tools/check_hacs_offline.py --hacs-source OFFICIAL_HACS_CLONE --archive SOURCE_ZIP --output RESULT_JSON
```

The tool checks the exact HACS commit/clean tracked sources and archive path/hash/size consistency. It writes only temporary test data plus the explicitly requested report. These checks do not authenticate an untrusted archive publisher.

This fixture check is NOT actual HACS GitHub discovery, OAuth startup, registration UI or remote download and does not establish private-repository support. It remains historical offline evidence. After separate scoped authorization, real public GitHub registration/download/installation passed using unmodified HACS methods and real network traffic; see ../evidence/HACS_REMOTE_INSTALL.json. That separate test satisfies the remote-install gate, not these fixtures.
