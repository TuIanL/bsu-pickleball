"""7.4 个人图层与状态卡口径一致性测试。

背景：`_build_roster_map` 的 `confirmed_only` 分支此前读 registry 快照的
`frozen_identity_confirmed`，而状态卡读 `anchor_binding_audit`。两者分歧时会出现
「热力图绘制 P4 个人图层 + 状态卡同时声明 P4 未确认且有效点为 0」的自相矛盾
（真实案例见 job-faf852782a）。

7.4 要求：个人热力图、散点图、位置指标与逐槽位状态卡消费同一份审计权威映射。
"""

from __future__ import annotations

from app.services.multiview_result_composer import _build_roster_map


def _entries() -> list[dict[str, object]]:
    """registry 快照：global_player_3/4 都被标成 confirmed（冲突根源）。"""
    return [
        {
            "global_player_id": "global_player_1",
            "player_id": "Player_2",
            "frozen_player_id": "Player_2",
            "frozen_identity_confirmed": True,
        },
        {
            "global_player_id": "global_player_2",
            "player_id": "Player_3",
            "frozen_player_id": None,
            "frozen_identity_confirmed": False,
        },
        {
            "global_player_id": "global_player_3",
            "player_id": "Player_4",
            "frozen_player_id": None,
            "frozen_identity_confirmed": False,
        },
        {
            "global_player_id": "global_player_4",
            "player_id": "Player_4",
            "frozen_player_id": "Player_4",
            "frozen_identity_confirmed": True,
        },
    ]


def _audit(*, p4_confirmed: bool) -> dict[str, object]:
    entries = [
        {
            "canonical_player_id": "Player_2",
            "canonical_end": "end_a",
            "confirmed": True,
            "formal_canonical_player_id": "Player_2",
            "global_player_id": "global_player_1",
        },
        {
            "canonical_player_id": "Player_3",
            "canonical_end": "end_b",
            "confirmed": False,
            "formal_canonical_player_id": None,
            "global_player_id": None,
            "reason": "bootstrap_binding_tracklet_competes_for_slots",
        },
        {
            "canonical_player_id": "Player_4",
            "canonical_end": "end_b",
            "confirmed": p4_confirmed,
            "formal_canonical_player_id": "Player_4" if p4_confirmed else None,
            "global_player_id": "global_player_4" if p4_confirmed else "global_player_2",
            "reason": None if p4_confirmed else "anchor_global_end_conflict",
        },
    ]
    return {"schema_version": "bootstrap-binding-audit.v1", "entries": entries}


def test_roster_map_defers_to_audit_over_registry_snapshot():
    """7.4：审计判P4 未确认时，个人图层不得再出现 P4。"""
    roster_map = _build_roster_map(
        _entries(),
        confirmed_only=True,
        anchor_binding_audit=_audit(p4_confirmed=False),
    )

    assert roster_map == {"global_player_1": "Player_2"}


def test_roster_map_keeps_p4_when_audit_confirms_it():
    """7.4：审计确认 P4 时才允许进入个人图层。"""
    roster_map = _build_roster_map(
        _entries(),
        confirmed_only=True,
        anchor_binding_audit=_audit(p4_confirmed=True),
    )

    assert roster_map["global_player_4"] == "Player_4"
    assert "global_player_2" not in roster_map


def test_roster_map_never_assigns_one_slot_to_two_globals():
    """7.4：一个 P 槽位不得被两个 global 同时占用（双源冲突的核心症状）。"""
    roster_map = _build_roster_map(
        _entries(),
        confirmed_only=True,
        anchor_binding_audit=_audit(p4_confirmed=True),
    )

    assert sorted(roster_map.values()) == ["Player_2", "Player_4"]
    assert len(set(roster_map.values())) == len(roster_map)


def test_roster_map_falls_back_to_registry_when_audit_absent():
    """7.4：历史 Job 无审计产物时保持旧行为，不因缺审计而丢失已确认身份。"""
    roster_map = _build_roster_map(_entries(), confirmed_only=True, anchor_binding_audit=None)

    assert roster_map == {
        "global_player_1": "Player_2",
        "global_player_4": "Player_4",
    }


def test_roster_map_ignores_audit_entry_with_foreign_formal_slot():
    """7.4：`confirmed=True` 但 formal 槽位回指他人时不得进入个人图层。"""
    audit = _audit(p4_confirmed=True)
    for entry in audit["entries"]:
        if entry["canonical_player_id"] == "Player_4":
            entry["formal_canonical_player_id"] = "Player_3"

    roster_map = _build_roster_map(_entries(), confirmed_only=True, anchor_binding_audit=audit)

    assert "global_player_4" not in roster_map
    assert roster_map == {"global_player_1": "Player_2"}


def test_roster_map_keeps_legacy_slot_fallback_without_confirmed_only():
    """非冻结名册 Job 仍用 slot 顺序 fallback，不受审计口径影响。"""
    roster_map = _build_roster_map(_entries(), confirmed_only=False)

    # global_player_2 与 global_player_3 的 player_id 都是 Player_4，
    # 后者必须拿到新槽位而不是重复占用。
    assert len(set(roster_map.values())) == len(roster_map)
    assert len(roster_map) == 4
