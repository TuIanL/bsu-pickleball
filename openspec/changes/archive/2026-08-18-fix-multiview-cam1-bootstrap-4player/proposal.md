## Why

joint_tracking_v2 双摄分析（job-f83ec9c3f9 验收）证实：cam_1（reference view）整场只有 3 个 track 被 PlayerLockManager 锁定（Player_1/3/4），**Player_2 槽位全程 searching 从未锁定**——画面第 4 名球员（远端右、conf 0.5）因脚点投影 x=31.3ft 超出 tracking bounds（x∈[-4,24]）被 `_is_identity_candidate` 直接拒绝，bootstrap 阶段不收集该候选。其后果链：cam_1 侧只有 3 个 view_player_id binding → 4 个 global player 抢 3 个槽位 → gid_3 被几何错配绑定到 Player_1（duplicate）、gid_4 无 cam_1 binding → roster 出现"两个 global 同绑 Player_1"身份冲突 → display diagnostics 产物 validator 抛 duplicate、前端 minimap/overlay 标签错乱（用户截图所见）。上一 change（fix-multiview-player-identity）只做了产物兜底与展示层语义修复，**未触及 bootstrap 漏锁第 4 人的根因**。

## What Changes

- **后端：身份候选接纳放宽（核心）**：`PlayerLockManager._is_identity_candidate` / `_classify_candidate` 对"court 横向（x）超出 tracking bounds、但纵向（y）在球场纵深内（near/far 可判）"的候选 SHALL 接纳为 bootstrap/reconnect 候选；bootstrap 资格判定 SHALL 以图像证据（bbox 存在 + 清晰度达标）为必要条件、court 投影仅作象限分配依据（软约束），MUST NOT 因投影 x 出界而完全丢弃脚点可判的球员。
- **后端：bootstrap 四槽位完整锁定**：`_assign_bootstrap_candidates` 在 bootstrap 窗口内 SHALL 尝试锁定全部 4 个槽位（near_left/near_right/far_left/far_right），近端/远端缺失候选时 SHALL 用"图像位置 → 象限归属"的松弛映射补齐，避免某一象限永久空槽。
- **后端：joint association 槽位唯一性**：`GlobalPlayerAssociator` 对 reference view binding 的 `(view_id, view_player_id)` SHALL 保持唯一——同一 `Player_N` 槽位在同一 view 内 SHALL 最多绑定一个 global；新 global 尝试占用已占用槽位时 SHALL 走 reassociation（PendingReassociation，5 帧强证据）而非直接覆盖。
- **后端：诊断产物兜底强化（既有，微调）**：display diagnostics builder 的 duplicate 去重逻辑保留，但身份冲突本身 SHALL 通过新增观测字段（如 roster 冲突计数）显式呈现，而非仅靠"保留首行"掩盖。
- **回归防护**：新增 bootstrap 四槽位锁定单测（构造 x 超界但纵向可判的第 4 人候选 → Player_2 被锁定）、association 槽位唯一性单测（两个 global 抢同一 Player_N → 第二个走 reassoc 不覆盖）、端到端 view 会话测试（4 人画面 → 4 个 track 全锁定）。

## Capabilities

### New Capabilities

- `bootstrap-slot-completeness`: 覆盖 PlayerLockManager bootstrap 阶段"4 槽位完整锁定"的约束——候选接纳规则（图像证据优先、投影仅作象限分配）、x 超界候选接纳、缺失象限的松弛映射补齐、四槽位完整性回归。

### Modified Capabilities

- `player-lock-state-machine`: bootstrap 候选过滤规则 SHALL 增加"court 纵向可判即可接纳（x 出界不拒绝）"，象限分配 SHALL 支持图像位置松弛映射；reconnect 候选同侧约束保持不变。
- `multiview-player-association`: reference view binding SHALL 保持 `(view_id, view_player_id)` 唯一；槽位占用冲突 SHALL 走 PendingReassociation 而非直接覆盖。
- `player-display-diagnostics`: 身份冲突 SHALL 通过显式观测字段呈现（如 `roster_conflict` 标记），duplicate 去重保留但不得掩盖冲突。

## Impact

- **后端文件**：
  - `backend/app/vision/player_tracking_engine/player_lock_manager.py`（`_is_identity_candidate`、`_classify_candidate`、`_assign_bootstrap_candidates`、`_infer_quadrant`）
  - `backend/app/vision/player_tracking_engine/player_lock_types.py`（配置：`tracking_x_margin_override` 或等价）
  - `backend/app/vision/multiview/association_global.py`（`GlobalPlayerAssociator` 槽位唯一性 + PendingReassociation）
  - `backend/app/vision/multiview/player_display_diagnostics.py`（冲突观测字段）
- **测试**：`backend/tests/test_player_lock_manager.py`（bootstrap 四槽位 + x 超界接纳）、`backend/tests/test_multiview_association_uniqueness.py`（新）、`backend/tests/test_player_display_diagnostics.py`（冲突观测）。
- **规格**：新增 `bootstrap-slot-completeness` spec；修改 `player-lock-state-machine`、`multiview-player-association`、`player-display-diagnostics` 三个 spec 的 delta。
- **风险**：接纳 x 超界候选可能引入场外人员（观众/裁判）误锁——需以"纵向可判 + bbox 清晰度达标 + 象限归属唯一"三重约束兜底；bootstrap 四槽位强制补齐可能把非球员填入空槽——需保持"锁定槽位不可替换"语义，宁可空槽不误锁。
