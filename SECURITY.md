# Security and privacy

Never include account passwords, session tokens, device passwords, sharing identities, camera endpoints or private video in an issue or diagnostic attachment. Review any output before sharing it. Public tests use fictional reserved identities.

The component stores account credentials using Home Assistant config entries; session and device secrets are runtime data. Protect configuration backups. The diagnostics show the email entered locally and hide the password; the JSON summary contains counts and fixed statuses rather than those values.

Use GitHub private vulnerability reporting if enabled by the repository owner. Do not publish exploit details or secrets in a public issue. No personal contact email is embedded; the repository owner is identified in CODEOWNERS.

The preparation includes static selected-pattern scans and manual source review, but no scanner guarantees the absence of every possible secret. Runtime IPC360 Home cloud access is still required; this integration does not provide offline-only camera access.

## Transport and worker review

The NET client uses the vendor TCP protocol and does not wrap its socket in TLS. Media DES follows the device protocol for interoperability. This integration does not retrofit a different cloud protocol or claim end-to-end confidentiality. Account credentials are not embedded in source, command arguments or environment variables. The DES input uses a private inherited descriptor. Runtime account/session/device secret fields are excluded from diagnostic summaries and sensitive object representations.

Installation is staged into a new directory only; the ZIP tool rejects unsafe member paths, symlinks, duplicates, oversized/unexpected assets and inconsistent runtime hashes before writing output. This does not authenticate an untrusted archive publisher.

## Known upstream dependency findings

The stable HA2026.10.4 test environment has39 advisory records in Pillow12.3.0, which HA pins. They remain recorded, not ignored, forcibly upgraded or declared fixed. No extra Virtavo pip dependency or prerelease HA requirement is introduced.

A bounded acceptance check on HA2026.10.0 and2026.10.4 exercises actual Virtavo HEVC/AAC HLS and unsupported image-proxy requests while12 Pillow image APIs fail on any call. It passes with no guarded API calls; unauthorized image access is rejected. This bounds the evidence to those paths and does not certify the host, other integrations or every Pillow API/advisory. See docs/DEPENDENCY_SECURITY.md and evidence/STABLE_SECURITY_SCOPE.json. Prefer HA's latest stable official release and retain upstream findings in release review.
