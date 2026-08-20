"""Read-only verification of job-bc053321f8 artifacts for fix-joint-bootstrap-visual-gap.

Confirms:
  (a) bootstrap_display_backfill.json — 5.2 "不造假" evidence
  (b) fused_player_overlay.json — current (pre-fix) has 0 bootstrap entities (integration gap)
"""
import json
import sys

JOB = "/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_122645_317228/analysis/job-bc053321f8"


def load(name):
    with open(f"{JOB}/{name}", "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("=== (a) bootstrap_display_backfill.json (5.2 不造假 evidence) ===")
    back = load("bootstrap_display_backfill.json")
    obs = back.get("observations", back) if isinstance(back, dict) else back
    if isinstance(back, dict):
        # Try common shapes
        for k in ("observations", "backfill", "data"):
            if k in back and isinstance(back[k], list):
                obs = back[k]
                break
        else:
            obs = [back]
    print(f"  type={type(back).__name__}  total observations={len(obs)}")
    players = {}
    frames = []
    bad_flags = []
    bad_canon = []
    for o in obs:
        pid = o.get("player_id") or o.get("playerId")
        players[pid] = players.get(pid, 0) + 1
        fr = o.get("frame_index", o.get("frameIndex"))
        frames.append(fr)
        do = o.get("display_only", o.get("displayOnly"))
        me = o.get("metric_eligible", o.get("metricEligible"))
        if do is not True or me is not False:
            bad_flags.append((pid, fr, do, me))
        canon = o.get("canonical_court_position_ft") or o.get("canonicalCourtPositionFt")
        if not canon or len(canon) != 2 or any(c is None for c in canon):
            bad_canon.append((pid, fr, canon))
    print(f"  player distribution={players}")
    print(f"  frame range=({min(frames)}..{max(frames)})  n={len(frames)}")
    print(f"  bad display_only/metric_eligible flags={len(bad_flags)}  -> {bad_flags[:5]}")
    print(f"  bad canonical coords={len(bad_canon)} -> {bad_canon[:5]}")

    print()
    print("=== (b) fused_player_overlay.json (current artifact, pre state-machine fix) ===")
    ov = load("fused_player_overlay.json")
    frames_ov = ov.get("frames", ov.get("overlay_frames", []))
    print(f"  total overlay frames={len(frames_ov)}")
    bb_entities = 0
    ev_counts = {}
    for fr in frames_ov:
        entities = fr.get("entities", fr.get("players", []))
        for e in entities:
            et = e.get("evidence_type", e.get("evidenceType"))
            ev_counts[et] = ev_counts.get(et, 0) + 1
            if et == "bootstrap_backfill":
                bb_entities += 1
    print(f"  evidence_type distribution={ev_counts}")
    print(f"  bootstrap_backfill entities in current overlay={bb_entities}")
    print(f"  => integration gap confirmed: backend computed {len(obs)} backfill obs but overlay injected {bb_entities}")


if __name__ == "__main__":
    main()
