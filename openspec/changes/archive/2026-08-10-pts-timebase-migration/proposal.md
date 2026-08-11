# PTS Timebase Migration

## Why

The current multiview path uses decoded `timestamp_seconds` and nominal
`frame_index / fps` in different layers. A later reliability change must make
source PTS the single timing authority across decode, tracking, pairing,
metrics, clips, and overlays.

## Scope

- Introduce one `FrameTimingProvider` backed by source PTS/DTS sidecars.
- Carry source PTS through single-view and joint tracking artifacts.
- Replace nominal frame-index timing in pairing, analysis windows, clips, and
  overlays with the provider's canonical take time.
- Preserve frame index as an address/provenance field, not as elapsed time.

## Non-Goals

- This change does not alter camera recording, segment generation, or codec
  settings.
- This change does not change the canonical court coordinate definition.

