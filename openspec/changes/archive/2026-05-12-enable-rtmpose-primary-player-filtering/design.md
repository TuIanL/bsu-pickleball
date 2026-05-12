## Context

The current real-video pipeline can render many YOLO person boxes, but RTMPose skeleton output is unavailable unless pose inference is explicitly enabled and model assets are configured. The latest real job showed tracking overlay output while reporting `RTMPose 姿态识别未启用`, so the user-facing "no skeleton" state is primarily an activation/configuration gap.

The active overlay playback change also filters browser-facing boxes and pose subjects by calibrated footpoint projection. That was useful for removing spectators, but it is too brittle as the main presentation rule: valid pickleball players often step behind the baseline or outside the sideline, and footpoint estimates can drift near court boundaries. When the filter removes a player box, RTMPose receives no subject for that track, causing both the box and skeleton to disappear.

## Goals / Non-Goals

**Goals:**

- Enable RTMPose in real calibrated analysis jobs when RTMPose dependencies, config, and checkpoint paths are available.
- Keep a clear unavailable state when RTMPose cannot run, including missing dependencies, missing assets, unsupported schema, or no selected subjects.
- Replace strict line-bound overlay filtering with a primary-player selector based mainly on detection confidence and track prominence.
- Preserve valid player boxes and skeletons when players step normally outside court lines.
- Continue rejecting low-confidence or incidental people so spectators and background people do not dominate overlays.
- Keep court projection for movement metrics and diagnostic details without making it the primary overlay visibility gate.

**Non-Goals:**

- Train or fine-tune a custom player detector.
- Add manual player selection, masking, or UI-driven spectator exclusion.
- Replace the current tracker with ByteTrack, BoT-SORT, or ReID-based identity tracking.
- Guarantee perfect identity stability across long rallies.
- Generate burned-in video files.

## Decisions

### Enable RTMPose when configured instead of keeping pose disabled by default

The backend should initialize `RTMPose26Adapter` for real analysis jobs when pose inference is enabled and the RTMPose config/checkpoint can be resolved. Documentation and environment defaults should support the desired local demo path, while still allowing users to disable pose inference for slower machines.

Alternatives considered:

- Always enable RTMPose unconditionally: simpler to understand, but it would fail noisily in environments without MMPose or model assets.
- Keep pose disabled unless users remember every environment flag: preserves current behavior, but it keeps producing tracking-only jobs even when the user expects skeletons.

### Introduce a primary-player selector for overlay and pose subjects

After detection and tracking, each active track should receive a presentation score. The first implementation can combine:

- current detection confidence,
- rolling or historical average confidence for that track,
- track persistence or number of recent appearances,
- per-frame rank by confidence,
- reasonable box area/height sanity checks,
- optional very broad court-distance exclusion for people clearly far away from the match scene.

The selector should keep at most the configured match participant count per frame, defaulting to 4 for doubles-capable videos. The same selected subject set should feed both the detection overlay artifact and RTMPose estimation.

Alternatives considered:

- Filter by single-frame confidence only: easy, but causes flicker when a player briefly dips in confidence.
- Keep only court-projected valid tracks: removes spectators, but also removes legitimate line-out players and makes skeletons disappear.
- Keep all high-confidence detections: helps recall, but clear spectators near the court can still clutter the overlay unless persistence/ranking limits are used.

### Separate metric-valid positions from presentation-valid subjects

Movement metrics should continue using strict or tolerant court-projected positions as appropriate, because those metrics depend on canonical court coordinates. Presentation overlays should use primary-player selection, not metric-valid projection, so a player can remain visible in video even when their projected footpoint is temporarily outside metric bounds.

Alternatives considered:

- Widen projector bounds until players no longer disappear: reduces false removals, but makes the projection rule do two jobs and can still fail on calibration drift.
- Remove court projection from the pipeline: would protect overlays, but would break movement metrics and heatmap workflows.

### Report filtering and pose status explicitly

Artifact detail strings should report raw detections, selected primary-player boxes, dropped low-confidence/incidental boxes, and RTMPose availability. The frontend can continue rendering existing artifact shapes, but status copy should help users distinguish "RTMPose not configured" from "configured but no primary players selected."

Alternatives considered:

- Keep current generic "no detections" or "unavailable" details: less work, but it hides whether the issue is configuration, filtering, or model quality.

## Risks / Trade-offs

- High-confidence spectators may be selected over real players in unusual camera angles -> cap selected subjects per frame, use track persistence, and allow broad scene-distance sanity checks.
- Track ID churn can make rolling scores unstable -> base frame selection on current confidence plus short rolling history rather than lifetime-only averages.
- RTMPose may make analysis much slower on CPU -> keep pose inference configurable, document CPU/GPU expectations, and preserve tracking-only degraded output.
- Lower-confidence real players may be dropped during occlusion or motion blur -> avoid a single high threshold as the only rule and use track persistence to bridge brief confidence dips.
- Existing active overlay specs mention court-relevant filtering -> this change supersedes that presentation rule while preserving court projection for metrics and diagnostics.
