# Verification scope

Preserved live evidence: a fresh email/password NET session, both owned/shared discovery groups, one shared camera's metadata, then a separate10-second independent stream check. The latter reported121 decoded HEVC video frames and55 decoded AAC audio frames,768 video packets,171 audio packets and11 rejected packets, status verified. No recording or credentials are included. The11 rejected packets were not classified; the aggregate count alone does not establish a regression or a loss rate.

Offline coverage includes packet serialization/validation, bounded transport, DES subprocess ownership, audio routing, on-demand endpoint lifecycle, credentials reauth and device selection, isolated component-only configuration and the full HA loader/config-entry/platform setup/unload. HA tests substitute external account/receiver I/O and restricted system IP enumeration with local fixtures. Actual HA http/stream/ffmpeg/camera dependencies are used. They do not decode another camera video.

The preparation workspace previously ran192 tests. Three historical research-only modules are deliberately absent from this repository: their dependencies were not runtime code and were missing from the old source ZIP. This repository's suite is counted from its own files and is tested again after extraction; do not transfer the old count to a different scope. The unchanged synthetic A/V module is present but not repeated by default.

Publication checks: static assets/imports/private-data scan, runtime-only HA copy and tests from an extracted repository archive. Selected-pattern scanning and manual source review found no supplied account credentials or personal environment data; automated scans cannot guarantee detection of every possible secret. The repository has a fresh local history rather than an imported laboratory history.

Still pending: actual HACS download from the real GitHub repository, live playback via the HA decoder/browser, compatibility across additional camera models/networks and precise A/V sync. Public cloud bootstrap addresses are vendor defaults, not user camera endpoints. Tests use reserved fictional identities and local/synthetic transports.

Final extracted-archive result:176 tests passed, zero failures/skips, Python3.14.8/HA2026.10.4. This is167 retained runtime/diagnostic tests plus9 new repository-control tests. The runner used an isolated interpreter with no external component-root override. At checkpoint38, runtime Python ASTs matched the live-verified source except documentation strings. Beta2 changes camera unload order as described below. Known private-context review found no matches; long DES S-box/permutation constants were reviewed as algorithm tables, not account secrets.

Owner metadata is now configured for giangi1986/ha-virtavo-ip360, including manifest URLs and CODEOWNERS. A regression test rejects missing or mismatched CODEOWNERS. The configured archive passed176 tests with isolated interpreter and no external component-root override. No new camera/video test was performed.

## Beta2 HA media regression

A publication-specific synthetic test now exercises the real HA stream worker: production mux HEVC/G711A → owned HTTP endpoint → HA HLS fMP4 → decoded HEVC and optional AAC frames. Video-only and audio-enabled cases pass; this is not another camera test. It does not certify a physical browser or remote HACS download. Synthetic first-part times around1.2s/2s are not real-camera startup guarantees.

A stalled-source test exposed an unload ordering defect: joining HA's reader before closing the owned source could exceed a3-second deadline while blocked in socket I/O. Beta2 closes the endpoint first and guarantees subsequent cleanup. The same stalled fixture then unloaded in0.007s. This timing is fixture-specific; the regression asserts a bounded3-second deadline. Protocol/authentication/DES/mux code was unchanged.

Beta2 final extracted-source suite:178 tests passed, zero failures/skips. This includes the two new HA-media tests (video/audio subcases and stalled-source unload). The protocol/authentication/DES/mux engine remains unchanged.

## Fresh environment and manual archive installation

New Python3.14.8 environment with no system site packages, installed only from requirements-test.txt:106 compatible distributions, no Unicorn installation. Final extracted-source suite:186 tests passed, zero failures/skips. Added6 installer tests and2 private workflow-policy tests beyond178. The installer stages only the validated runtime into a fresh HA config and the actual loader/setup/unload succeeds. It rejects corruption, unsafe paths, symlinks and duplicate members before output. No production HA configuration, household service or real camera was touched.

HACS private-repository support was checked against official documentation and is absent. These manual install checks do not satisfy the remote HACS download gate. Known-vulnerability queries against PyPI and OSV failed with read timeouts; no completed report and no zero-vulnerability result. Private CI is prepared but not executed. Static secrets/assets/import review remains a separate completed control.
