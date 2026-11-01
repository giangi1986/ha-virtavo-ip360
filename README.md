# Virtavo / IPC360 Home for Home Assistant

Beta candidate **0.1.0-beta.2**, licensed under MIT. Public repository for the authorized HACS test; no release or community announcement. Destination metadata is configured for giangi1986/ha-virtavo-ip360. Actual registration, GitHub archive download and installation through unmodified HACS2.0.5 methods now pass in an empty HA configuration, followed by real HA setup/unload. HACS browser UI/OAuth startup is not covered; see evidence/HACS_REMOTE_INSTALL.json.

Email/password authentication, fresh device discovery (owned and shared devices), autonomous manager/relay transport, pure Python DES, H.265 video and optional AAC audio. On-demand streaming and audio OFF are the defaults. Continuous streaming is optional and may increase battery consumption.

All runtime code is inside `custom_components/virtavo`. No development server, historical network capture, proprietary SDK or Unicorn is required. The integration does require the IPC360 Home cloud service, Internet access and the FFmpeg supplied by a supported Home Assistant installation. This is not an offline/local-only camera protocol.

## Installation

See [installation](docs/INSTALLATION.md). The selected baseline is stable Home Assistant2026.10.4; minimum2026.10.0 has separate compatibility checks. No prerelease HA or extra Virtavo pip dependency is required. Linux/POSIX is required for the private process pipes. The browser/player must support HEVC. No external RTSP server is required.

The config flow validates credentials, discovers devices and requires selecting a real device. Home Assistant stores the account credentials in its config entry. Session tokens, device passwords and shared playback identities are kept in owned runtime memory and are not intentionally logged. Protect your Home Assistant configuration and backups.

## Verification

A separate fresh-session live test decoded121 HEVC frames and55 AAC frames in10 seconds from a shared device, without recording. The full Home Assistant loader, camera registration, on-demand HTTP producer and unload were tested in an isolated runtime-only configuration. External account/receiver I/O was substituted in HA tests; the receiver's real operation was checked separately.

See [verification and limits](docs/VERIFICATION.md). The real HA HLS worker also processes synthetic HEVC/AAC output from the production mux; stalled-source unload is regression-tested. Physical browser playback remains unverified; the actual HACS download is verified separately from these offline tests. H.264, Google login, snapshots, motion, talkback and playback archives are outside the first beta. UDP loss recovery/reordering and precise A/V sync are not implemented; CN carrier routing is unsupported. Audio OFF discards audio before processing and does not guarantee the device stops sending it.

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

## Controlled HACS test status

The repository is public solely for the owner-authorized HACS installation test. No release, public tag or community announcement has been created. Wider release/announcement authorization remains separate. Production HA and cameras were not modified.

The final candidate passes190 tests on stable HA2026.10.4 and27 targeted HA/security-scope tests on minimum2026.10.0. All10 official HACS action checks pass. Unmodified HACS2.0.5 methods register the actual GitHub repository, download its real archive and install37 byte-matching files into an empty HA configuration. Real HA then registers the camera, consumes the on-demand endpoint and unloads. HACS browser UI/OAuth startup and physical browser playback are not tested. Account/receiver I/O in the HA acceptance phase uses local fixtures; actual device operation is separate preserved evidence. GitHub uses a short-lived read-only Actions token, not camera credentials. See evidence/FINAL_ACCEPTANCE.json and evidence/HACS_REMOTE_INSTALL.json for exact revisions and run/job links.

The32 runtime Python modules and all35 preexisting integration files are unchanged from checkpoint53. Only the original MIT brand/icon.png and its provenance README were added for HACS branding. No vendor artwork or fonts are reused. No Karbon, historical PCAP, proprietary SDK, Unicorn, separate bridge or RTSP server is required. Vendor cloud/Internet and HA stream/ffmpeg with FFmpeg remain necessary. No extra Virtavo pip requirement or prerelease HA is imposed.

Known host risk remains:39 advisory records affect HA-pinned Pillow12.3.0. They are not fixed, suppressed or forcibly upgraded. Actual Virtavo HLS/unsupported-image-proxy path tests on both stable targets make no calls to12 guarded Pillow image APIs; this bounded scope does not certify the whole HA host or every Pillow path. See docs/DEPENDENCY_SECURITY.md.

Before public exposure,35 remote commits and2473 historical file visits passed selected source/assets and commit metadata checks; no unexpected email was found. GitHub system/user noreply addresses were correctly distinguished from private identities. ZIP53 CRC/file hashes and a fresh bundle53 clone restored all110 source files. A later combined review covered62 local/remote commits without selected sensitive findings. Private operational history, captures, SDK binaries, recordings and credentials are outside this repository. These controls are not universal secret detection or a legal opinion. Archives include per-file hashes; isolated staging rejects unsafe paths, symlinks, duplicates, corruption and unexpected assets. The original PNG is size/format/CRC checked, contains no ancillary metadata chunks and has bounded decompression; other unexpected binaries remain rejected.
