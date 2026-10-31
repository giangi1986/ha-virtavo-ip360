# Virtavo / IPC360 Home for Home Assistant

Local beta candidate **0.1.0-beta.2**, licensed under MIT. Prepared for HACS custom-repository installation; not yet published. Destination metadata is configured for giangi1986/ha-virtavo-ip360. An actual HACS repository download still requires a remotely available repository and has not been performed.

Email/password authentication, fresh device discovery (owned and shared devices), autonomous manager/relay transport, pure Python DES, H.265 video and optional AAC audio. On-demand streaming and audio OFF are the defaults. Continuous streaming is optional and may increase battery consumption.

All runtime code is inside `custom_components/virtavo`. No development server, historical network capture, proprietary SDK or Unicorn is required. The integration does require the IPC360 Home cloud service, Internet access and the FFmpeg supplied by a supported Home Assistant installation. This is not an offline/local-only camera protocol.

## Installation

See [installation](docs/INSTALLATION.md). The selected baseline is stable Home Assistant2026.10.4; minimum2026.10.0 has separate compatibility checks. No prerelease HA or extra Virtavo pip dependency is required. Linux/POSIX is required for the private process pipes. The browser/player must support HEVC. No external RTSP server is required.

The config flow validates credentials, discovers devices and requires selecting a real device. Home Assistant stores the account credentials in its config entry. Session tokens, device passwords and shared playback identities are kept in owned runtime memory and are not intentionally logged. Protect your Home Assistant configuration and backups.

## Verification

A separate fresh-session live test decoded121 HEVC frames and55 AAC frames in10 seconds from a shared device, without recording. The full Home Assistant loader, camera registration, on-demand HTTP producer and unload were tested in an isolated runtime-only configuration. External account/receiver I/O was substituted in HA tests; the receiver's real operation was checked separately.

See [verification and limits](docs/VERIFICATION.md). The real HA HLS worker also processes synthetic HEVC/AAC output from the production mux; stalled-source unload is regression-tested. Physical browser playback and actual HACS download are not certified by these offline tests. H.264, Google login, snapshots, motion, talkback and playback archives are outside the first beta. UDP loss recovery/reordering and precise A/V sync are not implemented; CN carrier routing is unsupported. Audio OFF discards audio before processing and does not guarantee the device stops sending it.

## Development

```bash
python -m pip install -r requirements-test.txt
python tools/run_tests.py
python tools/validate_repository.py
```

The default test command does not repeat the unchanged synthetic A/V codec tests. For a new environment or a relevant media regression, run `python tools/run_tests.py --include-av` with FFmpeg/FFprobe and libx265 available. No test requires actual camera credentials, PCAP or SDK files.

`tools/check_account.py` and `tools/check_stream.py` are explicitly invoked diagnostics. They accept a visible email and a hidden password, confirm accepted login, and produce redacted JSON. The stream diagnostic briefly opens the selected camera and stores no recording. Do not repeat a successful live test without a concrete regression or publication requirement.

## Repository preparation

The destination is `giangi1986/ha-virtavo-ip360`, with manifest URLs and CODEOWNERS bound to `@giangi1986`. `python tools/validate_repository.py --publication` checks this metadata locally. The configuration tool never connects to GitHub or publishes.

The CI workflows validate and test only. No workflow creates a repository, pushes changes or publishes releases. Publication remains subject to the owner's explicit authorization. [MIT license](LICENSE), [provenance](docs/PROVENANCE.md), [security](SECURITY.md), [checkpoint](VIRTAVO_STATO_PROGETTO.md).

## Private-only test status

Public publication is not authorized. Standard HACS does not support private repositories; see [private testing](docs/PRIVATE_TESTING.md) and the linked official FAQ. The local ZIP installer and full HA tests can run without publishing. The complete extracted candidate passes187 tests on stable HA2026.10.4, zero failures/skips. The minimum2026.10.0 environment has27 targeted HA/security-scope checks passing. Both use only declared dependencies. No existing configuration was overwritten.

The private dependency audit completed and its106-package inventory matches the stable environment. It reports39 records in Pillow12.3.0, pinned by HA2026.10.4; the host finding remains open and is not suppressed or forcibly upgraded. A new bounded test of actual Virtavo HLS and image-proxy paths passes on HA2026.10.0 and2026.10.4 with no calls to12 guarded Pillow image APIs. This does not certify the whole HA host or every Pillow path. See [dependency security assessment](docs/DEPENDENCY_SECURITY.md).

The official HACS2.0.5 repository engine also validates and extracts the35 runtime files from a local archive fixture, after which the real HA loader succeeds. This is an offline engine check, not an actual remote HACS download; see [scope and reproduction](docs/HACS_OFFLINE_TEST.md).

Stable HA remains the default. Earlier preview compatibility evidence is retained separately and does not impose a prerelease requirement.

The private source mirror is being completed from the verified source archive. Clean GitHub runner checks and whole-tree byte verification remain pending; local source ZIP and Git bundle are the authoritative backups. No public repository visibility or release is authorized.
