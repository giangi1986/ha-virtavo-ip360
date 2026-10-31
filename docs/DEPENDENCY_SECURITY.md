# Stable HA dependency security assessment — checkpoint50

## Selected target

The owner selected stable Home Assistant and autonomous project-scope triage. The default test requirements remain HA2026.10.4, the latest stable checked on2026-10-31. The declared minimum stays2026.10.0 and is separately tested. No prerelease HA, Pillow override, additional pip dependency, SDK, external bridge or server is required by Virtavo. The optional requirements-test-preview.txt and preview evidence are historical compatibility evidence only.

Home Assistant's security policy supports the latest stable official release; minimum-version compatibility does not mean older patch releases have current upstream security support. Prefer the current stable HA patch. Source: https://www.home-assistant.io/security/

## Audit provenance and retained host finding

The supplied dependency-audit.zip matches its private CI SHA256. All106 package names and versions match the clean stable test environment exactly. It reports39 advisory records in Pillow12.3.0; every record lists13.0.0 as fixed. HA2026.10.4 pins Pillow==12.3.0, so overriding it would violate HA's declared requirements. Compact IDs, aliases and fixed versions are retained in evidence/DEPENDENCY_TRIAGE.json. Upstream fixes: https://pillow.readthedocs.io/en/latest/releasenotes/13.0.0.html

The host audit remains a finding/exit1. No ignore list, dependency metadata patch, forced upgrade or zero-vulnerability claim for stable HA is introduced. Pillow is an upstream HA dependency; Virtavo's manifest requirements is empty. This assessment does not repair Pillow or make other HA integrations safe. Maintain normal HA updates and review the upstream finding during publication review. A future compatible stable upstream fix can be tested when available.

## Relevance to the implemented Virtavo paths

All32 runtime sources have no direct PIL/Pillow imports. The component uses the HA stream/ffmpeg components, standard Python and the FFmpeg executable. Still images are unsupported: async_camera_image returnsNone and inherited use_stream_for_stills isFalse.

A new bounded acceptance test, test_dependency_scope.py, ran on HA2026.10.0 and2026.10.4 with the actual registered camera, owned HTTP source, production mux, HA HLS worker and decoded synthetic HEVC/AAC. Twelve Pillow image entry points for opening/creating/saving/converting/filtering/transforming/quantizing/EXIF are replaced with fail-on-call guards. Normal and scaled camera_proxy image requests fail as unsupported without waking the source; an unauthenticated request is rejected. The HLS stream decodes18 video and8 audio frames and unloads its worker. No guarded Pillow API is invoked. No exploit or malicious image is executed.

This provides bounded evidence that the reported image-processing operations are not invoked by those tested Virtavo paths. It is not a blanket not-affected statement for all39 advisories, all Pillow APIs, modified/custom consumers or the entire HA host. No advisories are suppressed. Evidence: STABLE_SECURITY_SCOPE.json. Runtime code is unchanged.

## Compatibility evidence

The minimum2026.10.0 target has106 compatible distributions and passes26 targeted HA checks plus the new scope check. The current stable2026.10.4 baseline previously passed186 distributed tests; the complete extracted package with the new scope test passed187 tests, zero failures/skips, using the isolated interpreter. CI now retains both stable and minimum profiles, with the full suite on current stable and27 HA/scope checks on the minimum. No physical camera is contacted.

The earlier separate official HA2026.11.0b1/Pillow13 environment passed26 targeted checks and its108-package audit had no known findings. That result neither changes the chosen stable requirement nor clears stable findings.

## Publication boundary

Stable compatibility work proceeds without requiring users to select prerelease HA. The upstream finding remains documented for final release review, rather than being relabeled a Virtavo code fix. No public publication is authorized. Actual HACS download and full private source mirroring remain separate pending operations.
