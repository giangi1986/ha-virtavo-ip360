# 0.1.0-beta.2 — local candidate

A source stall could leave Home Assistant's stream-reader thread blocked while removing the camera: the component joined that reader before closing its own HTTP source. The component now closes the owned endpoint first, then stops the HA stream and runs base cleanup, including error paths.

Verified with the actual HA loader and stream worker using synthetic media: production HEVC/G711A mux output becomes HLS/fMP4 and decodes as HEVC plus optional AAC. Normal video-only, audio-enabled and stalled-source unload cases pass. This is a new integration check, not another live camera test.

178 tests passed from an extracted archive. Independent fresh-session shared-camera HEVC/AAC proof from the earlier version remains valid for the unchanged protocol/DES/mux engine. Only camera lifecycle and manifest version changed at runtime.

Release checklist remains5/7=71%: actual GitHub/HACS download and final publication review/authorization remain pending. No push or release performed. Browser playback with a physical client remains unverified. Source is MIT, targetgiangi1986/ha-virtavo-ip360.
