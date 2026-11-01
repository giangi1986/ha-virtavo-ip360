# Installation

## Controlled public test candidate

The source tree has the HACS integration layout and contains one integration, `custom_components/virtavo`. The destination is configured as `giangi1986/ha-virtavo-ip360`. Run `python tools/validate_repository.py --publication` to check local metadata. Configuration does not create or publish the GitHub repository.

For isolated developer testing, copy only `custom_components/virtavo` into an empty Home Assistant configuration's `custom_components` directory. Restart that isolated instance, add Virtavo Camera from Settings → Devices & services, authenticate with IPC360 Home email/password and select a discovered camera. This manual copy does not certify HACS downloading.

## Private test installation

See [private testing](PRIVATE_TESTING.md). HACS standard does not support private repositories. The private ZIP installer creates a fresh isolated configuration without changing a working HA installation; it is not a HACS download test.

## HACS installation in a test instance

1. In HACS, add `https://github.com/giangi1986/ha-virtavo-ip360` as a custom repository, category Integration. The repository is public solely for the authorized installation test.
2. Download the main branch (no GitHub release has been created), then restart the test Home Assistant instance.
3. Add Virtavo Camera, choose the correct account region/country, log in and select a camera. For Italy, countryIT and server regionfr correspond to the audited app policy.
4. Open the camera stream. On-demand starts the producer only when consumed. Enable audio in options if desired; continuous streaming is opt-in.
5. Verify close/reopen, reload, reauthentication and removal. Preserve any existing production instance while evaluating the beta.

Stable Home Assistant2026.10.4 is the selected baseline. Declared minimum2026.10.0 was also tested separately. Prefer the latest stable HA patch; no prerelease or Pillow override is required. The runtime uses standard Python plus HA dependencies stream/ffmpeg, with FFmpeg available as an external executable; no proprietary Python requirement is installed. Linux/POSIX process pipes are required. HEVC-capable playback clients are required; browser compatibility varies.

Cloud access to the IPC360 Home account/manager and UDP relay is required. Server bootstrap defaults are based on app8.10.1.0 and may need updates if the service changes. Region is not the same as country; CN carrier policy is not supported.

References checked2026-10-31: https://hacs.dev/docs/publish/integration/ and https://hacs.dev/docs/publish/start/.


## Host dependencies and advisory scope

Virtavo has no additional pip requirements and needs no SDK, Unicorn, PCAP, Karbon, separate bridge or RTSP server. HA's built-in stream/ffmpeg components and the FFmpeg executable supplied by the HA installation remain necessary; IPC360 Home cloud/Internet access is necessary. Developer requirements-test files are for disposable test environments, not instructions to reinstall dependencies inside a working HA instance.

The selected stable host pins a Pillow version with known upstream findings. See DEPENDENCY_SECURITY.md for the retained findings and bounded Virtavo-path test; do not override HA dependencies manually. A real HACS network registration/download/install test now passes on the public test repository; no release or community announcement has been created. HACS UI/OAuth startup and physical client playback remain separate unverified paths.
