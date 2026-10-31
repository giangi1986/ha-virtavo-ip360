"""Runtime availability, distinct from authorization/readiness to publish.

Fresh shared-account H.265/AAC stream verified live; HA factory/endpoint verified
in an isolated component-only copy. RELEASE_GATES.json tracks publication.
"""
RELEASE_READY = True
AUDIO_SUPPORTED = True
BLOCK_REASON = (
    "Virtavo runtime is available. Repository metadata, provenance and a real "
    "clean HACS download remain publication checks; see RELEASE_GATES.json."
)
