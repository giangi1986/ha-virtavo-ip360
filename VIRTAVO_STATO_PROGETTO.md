# Project checkpoint50 —2026-10-31

Reference0.1.0-beta.2; giangi1986/ha-virtavo-ip360; MIT/CODEOWNERS configured. Public visibility and public releases NOT authorized. Checklist5/7=71%, not effort/time.

Owner selected stable HA and autonomous project-scope security assessment. No prerelease requirement, additional Virtavo pip dependency or runtime changes. Latest stable checked2026.10.4, minimum2026.10.0 unchanged and newly verified:106 compatible packages,26 targeted HA tests plus new bounded dependency-scope test pass. Full current-stable extracted package passed187 tests, zero failures/skips, using an isolated interpreter; no external component-root override.

Pillow host findings retained: user artifact matches CI SHA256 and all106 stable versions.39 advisory records affect HA-pinned Pillow12.3.0; all list13.0.0 fixed, incompatible with that exact HA pin. No ignore, metadata patch, forced dependency update or global safety claim. These are upstream HA findings; Virtavo has no direct Pillow imports or additional pip requirements.

New actual-HA acceptance scope passes on both2026.10.0 and2026.10.4: real HEVC/AAC HLS continues with12 Pillow image APIs guarded to fail on call; unsupported normal/scaled image-proxy requests fail without waking camera, unauthenticated access rejected. No guarded API calls; no exploit input. This is bounded evidence for those paths, not every advisory/API/host integration. No user technical confirmation or prerelease switch needed.

Runtime unchanged, historical DES/auth/fresh live121HEVC55AAC proofs preserved. Only synthetic checks justified by the declared minimum and security-path requirement run; no camera/cloud/production access. CI prepared with current stable full suite and minimum27 HA/scope checks. Earlier preview evidence retained as historical only.

Full source/Git backups persist; private remote remains minimal CI harness. Native connection last returned404 despite valid browser login. Full private source mirroring, actual HACS download and final publication review remain pending; standard HACS private repos unsupported, public availability still prohibited. No new remote changes in this checkpoint.

Official HACS2.0.5 repository-engine/schema acceptance also passes on both2026.10.0 and2026.10.4: unmodified pinned modules, local GitHub/archive fixtures,35 runtime files extracted byte-for-byte and then loaded/registered/consumed/unloaded by real HA. No frontend/startup/real remote download tested; gate remains open. Reproduction and exact limits in docs/HACS_OFFLINE_TEST.md.
