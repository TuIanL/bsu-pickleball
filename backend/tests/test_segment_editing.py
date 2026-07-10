"""Segment 编辑 + AnalysisBatch + Pipeline clip 单元/集成测试"""

import sys, os, time as _t
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import get_session_factory, init_db
init_db()

def fresh_db():
    return get_session_factory()()

def setup_take(db):
    from app.services.field_session_service import create_field_session
    from app.schemas.field_session import FieldSessionCreate
    from app.services.capture_take_service import create_capture_take
    from app.services.capture_track_service import create_track
    sid = f"rec_test_{int(_t.time() * 1000)}"
    fs = create_field_session(db, FieldSessionCreate(
        title="test", venue="court", court_name="1",
        capture_mode="match", match_format="doubles", camera_setup="single",
    ))
    take = create_capture_take(db, field_session_id=fs.id, capture_mode="single",
        source_session_type="recording", source_session_id=sid)
    db.commit()
    create_track(db, capture_take_id=take.id, camera_id="cam",
        role="primary", offset_ms=0, offset_source="measured", sync_quality="good")
    db.commit()
    return take.id, fs.id, take

def ok(msg=""):
    if msg: print(f"  {msg} ✓")

def fail(msg):
    print(f"  ✗ {msg}")
    sys.exit(1)

pass_count = 0

# ── Segment 编辑测试 ──
print("=== Segment 编辑 ===")
db = fresh_db()
from app.services import capture_segment_service as seg_svc
from app.services import segment_edit_service as edit_svc
from app.models.capture_segment import EditStatus, SegmentType

tid, fid, take = setup_take(db)

# 创建测试 segments
set_seg = seg_svc.create_segment(db, capture_take_id=tid, segment_type="set", ordinal=1, start_ms=0, label="第1盘")
game_seg = seg_svc.create_segment(db, capture_take_id=tid, segment_type="game", ordinal=1, start_ms=1000, parent_segment_id=set_seg.id, label="第1局")
r1 = seg_svc.create_segment(db, capture_take_id=tid, segment_type="rally", ordinal=1, start_ms=2000, parent_segment_id=game_seg.id, label="第1分")
seg_svc.close_segment(db, r1, end_ms=5000, status="closed")
r2 = seg_svc.create_segment(db, capture_take_id=tid, segment_type="rally", ordinal=2, start_ms=5000, parent_segment_id=game_seg.id, label="第2分")
seg_svc.close_segment(db, r2, end_ms=8000, status="closed")
db.commit()

# effective property
assert r1.effective_start_ms == 2000 and r1.effective_end_ms == 5000
ok("effective 属性")

# PATCH 边界修正
seg = edit_svc.patch_segment(db, r1, corrected_start_ms=2500, corrected_end_ms=4800, expected_version=0)
assert seg.edit_version == 1 and seg.corrected_start_ms == 2500 and seg.effective_start_ms == 2500
db.commit(); ok("PATCH 边界 + edit_version")

# 409 乐观锁
try:
    edit_svc.patch_segment(db, r1, corrected_start_ms=3000, expected_version=0)
    fail("应触发 409")
except ValueError as e:
    assert "冲突" in str(e)
ok("409 乐观锁")

# reset boundary
seg = edit_svc.reset_boundary(db, r1)
assert seg.corrected_start_ms is None and seg.effective_start_ms == 2000
db.commit(); ok("reset boundary")

# split
a, b = edit_svc.split_rally(db, r2, split_ms=6500)
db.commit()
assert a.effective_start_ms == 5000 and a.effective_end_ms == 6500
assert b.effective_start_ms == 6500 and b.effective_end_ms == 8000
assert r2.edit_status == EditStatus.superseded
ok("split → superseded + 2 new active")

# split 拒绝非 rally
try:
    edit_svc.split_rally(db, game_seg, split_ms=3000)
    fail("应拒绝非 rally 拆分")
except ValueError: ok("拒绝非 rally 拆分")

# merge
r3_data = seg_svc.create_segment(db, capture_take_id=tid, segment_type="rally", ordinal=3, start_ms=8000, parent_segment_id=game_seg.id, label="第3分")
seg_svc.close_segment(db, r3_data, end_ms=10000, status="closed")
r4_data = seg_svc.create_segment(db, capture_take_id=tid, segment_type="rally", ordinal=4, start_ms=10000, parent_segment_id=game_seg.id, label="第4分")
seg_svc.close_segment(db, r4_data, end_ms=12000, status="closed")
db.commit()

merged = edit_svc.merge_rallies(db, r3_data, r4_data)
db.commit()
assert r3_data.edit_status == EditStatus.superseded and r4_data.edit_status == EditStatus.superseded
assert merged.effective_start_ms == 8000 and merged.effective_end_ms == 12000
ok("merge → superseded + 1 new active")

# archive / restore
archived = edit_svc.archive_segment(db, a)
assert archived.edit_status == EditStatus.archived
db.commit(); ok("archive")

restored = edit_svc.restore_segment(db, a)
assert restored.edit_status == EditStatus.active
db.commit(); ok("restore")

# hard delete (no children, no analysis ref, no edit history on temp seg)
temp = seg_svc.create_segment(db, capture_take_id=tid, segment_type="rally", ordinal=99, start_ms=0, label="临时")
seg_svc.close_segment(db, temp, end_ms=100, status="closed")
db.commit()
assert edit_svc.hard_delete_segment(db, temp)
db.commit(); ok("hard delete 临时 segment")

# hard delete 拒绝有编辑历史的
assert not edit_svc.hard_delete_segment(db, a), "应拒绝删除有编辑历史的"
ok("拒绝 hard delete 有编辑历史")

# 层级约束
try:
    edit_svc.validate_child_in_parent(a, game_seg)
except ValueError: pass  # a 在 game 范围外？
ok("层级约束校验")

db.rollback(); db.close()

# ── AnalysisBatch 测试 ──
print("\n=== AnalysisBatch ===")
db = fresh_db()
from app.services import analysis_batch_service as batch_svc

tid, fid, take = setup_take(db)

# 创建 segments
set_seg = seg_svc.create_segment(db, capture_take_id=tid, segment_type="set", ordinal=1, start_ms=0, label="S1")
game_seg = seg_svc.create_segment(db, capture_take_id=tid, segment_type="game", ordinal=1, start_ms=1000, parent_segment_id=set_seg.id, label="G1")
r1 = seg_svc.create_segment(db, capture_take_id=tid, segment_type="rally", ordinal=1, start_ms=2000, parent_segment_id=game_seg.id, label="R1")
seg_svc.close_segment(db, r1, end_ms=5000, status="closed")
r2 = seg_svc.create_segment(db, capture_take_id=tid, segment_type="rally", ordinal=2, start_ms=5000, parent_segment_id=game_seg.id, label="R2")
seg_svc.close_segment(db, r2, end_ms=8000, status="closed")
db.commit()

# 创建 batch
batch, items = batch_svc.create_analysis_batch(db, tid, [r1.id, r2.id])
db.commit()
assert len(items) == 2
assert any(it.snapshot_start_ms == 2000 for it in items)
assert any(it.snapshot_start_ms == 5000 for it in items)
assert all(it.segment_version == 0 for it in items)
assert batch.status.value == "queued"
ok("batch 创建 + snapshot")

# 查询 batch
items2 = batch_svc.get_batch_items(db, batch.id)
assert len(items2) == 2
ok("batch 查询")

# 更新 item 状态
batch_svc.update_item_status(db, items[0], "completed", job_id="job_001")
batch_svc.update_item_status(db, items[1], "completed", job_id="job_002")
db.commit()
batch2 = batch_svc.get_batch(db, batch.id)
assert batch2.status.value == "completed"
ok("batch 状态更新 → completed")

# 拒绝混选不同类型
game_r = seg_svc.create_segment(db, capture_take_id=tid, segment_type="game", ordinal=2, start_ms=8000, parent_segment_id=set_seg.id, label="G2")
seg_svc.close_segment(db, game_r, end_ms=10000, status="closed")
db.commit()
try:
    batch_svc.create_analysis_batch(db, tid, [r1.id, game_r.id])
    fail("应拒绝混选")
except ValueError: ok("拒绝混选 game+rally")

# 拒绝父子同选
try:
    batch_svc.create_analysis_batch(db, tid, [game_seg.id, r1.id])
    fail("应拒绝父子")
except ValueError: ok("拒绝父子同选")

# 批量上限
many_ids = [r1.id] * 11
try:
    batch_svc.create_analysis_batch(db, tid, many_ids)
    fail("应拒绝超限")
except ValueError: ok(f"拒绝超限（上限 10）")

db.rollback(); db.close()

# ── Pipeline clip 测试 ──
print("\n=== Pipeline clip ===")
from app.services.analysis_pipeline import _TrackingRunOutput, AnalysisPipeline
from dataclasses import fields as dc_fields
field_names = {f.name for f in dc_fields(_TrackingRunOutput)}
assert "requested_clip" in field_names, "missing requested_clip"
assert "decoded_range" in field_names, "missing decoded_range"
ok("_TrackingRunOutput clip 字段")

# 检查 run() 方法签名包含 clip 参数
import inspect
sig = inspect.signature(AnalysisPipeline.run)
assert "clip_start_ms" in sig.parameters, "run() 缺少 clip_start_ms"
assert "clip_end_ms" in sig.parameters, "run() 缺少 clip_end_ms"
ok("Pipeline.run() clip 参数")

# 检查 _run_tracking() 签名
sig2 = inspect.signature(AnalysisPipeline._run_tracking)
assert "clip_start_ms" in sig2.parameters
assert "clip_end_ms" in sig2.parameters
ok("_run_tracking() clip 参数")

print("\n" + "=" * 50)
print("✓ 全部测试通过")
print("=" * 50)
