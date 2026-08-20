## Context

Debug Replay 四联 MP4 由 `joint_debug_renderer.py` 从持久化 evidence（`joint_debug_trace.v1.json` + trajectory + diagnostics + 原视频）离线渲染，前端仅播放 MP4。两个已确认的事实构成本设计的出发点：

1. **cam-2 前段无框有两条不同机制**：
   - **机制 A（display-only tick）**：`multiview_joint_run.py` 的 tick 循环中 `status != "available"` 的视角直接 `continue`（perception 整体跳过），`view_results` 中无该 view，trace 的 `detections` 恒为空。但 renderer 将 `available_extrapolated` / `fallback_valid_start` 视为可渲染状态（显示真实源帧）。即"有画面"与"跑过 tracker"是两回事，且此路径**没有任何 track 数据可供画框**。
   - **机制 B（bootstrap 期 available tick）**：tracker 正常 step，全量存活 `tracks` 在 lock 过滤前已存在于 `ViewTrackingSession.step()` 中；因 `eligibility_policy="lock_only"`（`multiview_joint_executor.py:359`），未锁定 track 被排除在 formal `frame_detections` 之外。数据在手里，只是没有输出通道。
2. **court panel 非等比失真**：`_court_panel()` 把 20 ft 映射到 530 px（26.5 px/ft）、44 ft 映射到 225 px（5.11 px/ft），同一英尺两方向像素长度差 5.18 倍；且只画了一条碰巧位于网位置的横线，NVZ 与发球中线缺失。

约束：MP4 输出契约 `1280×620` 四联布局被测试锁定且前端已适配，不可变；正式链路（PlayerLock / eligibility / association / fusion / sync authority）不可动。

## Goals / Non-Goals

**Goals:**

- 正常 `available` tick 中，把 tracker 已见但未满足 `lock_only` eligibility 的存活 track 以可选 `candidate_detections` 字段写入 trace（debug-only）。
- Renderer 区分候选框（细线弱色、统一标 `candidate`）与正式框（现状高亮、`Player_N`）。
- Display-only 帧在画面上明确标注未执行 tracking，消除"漏检"误读。
- Court panel 单一 px/ft 等比绘制，横置 44 ft 长边，补齐标准球场线。
- 旧 trace（无 `candidate_detections`）加载与渲染完全兼容。

**Non-Goals:**

- 不改 `eligibility_policy`、PlayerLock 阈值、association、fusion、sync authority 或任何正式产物。
- 不为 candidate 框反查 PlayerLock slot 精细状态（`player_states` 是 slot→state，不是 track→state；反查扩大范围且收益低）。
- 不 bump `joint_debug_trace.v1` 到 v2。
- 不改前端页面与 MP4 布局/尺寸。
- 不追求"让前几秒看起来有框"——目标是准确表达算法当时所处的阶段。

## Decisions

### D1：`candidate_detections` 作为 v1 可选字段，而非 bump v2

**决策**：trace schema 保持 `joint_debug_trace.v1`；`candidate_detections` 是 view 级可选字段，validator 仅做 **list 级校验**——字段缺失 → 通过；字段存在但不是 list → 失败。SHALL NOT 顺手加强 formal `detections` 的历史逐元素校验（否则历史 trace 可能开始 load 失败）；candidate 元素形状（bbox/track_id/confidence、不带 player_id）由 producer 单测锁定。renderer 一律 `view.get("candidate_detections", [])`。

**理由**：这是纯诊断增强，formal `detections` 语义一字不变；旧 trace 无字段仍可加载是硬需求（历史 run 的 replay 不能坏）。bump v2 会让 loader/renderer/manifest/测试全链跟着动，对 debug-only 工具收益为负。

**备选**：必填字段（旧 trace 直接 load 失败，需迁移，否决）；v2（成本不成比例，否决）。

### D2：candidate 数据在生产端一次成型，消费端零推导

**决策**：`ViewTrackingSession.step()` 中先显式计算集合差 **`candidate_track_ids = live_track_ids - eligible_track_ids`**，再仅对该集合生成 candidate 列表（复用 `_tracks_to_frame_detections()` 的构造语义），挂在 `ViewFrameResult` 新字段 `candidate_detections` 上。`_build_debug_tick()` 把它写入 view 的 `candidate_detections`（与 formal `detections` 同构的 dict 行，含 bbox/track_id/confidence，不含 player_id——candidate 没有 formal 身份）。

**硬不变量**：`formal_track_ids ∩ candidate_track_ids == ∅`（同一 tick 内集合互斥）。实现不得先取"全部 live tracks"再遗漏排除已 formal 的 track；该不变量须有专门测试锁定。

**理由**：candidate 恰好是 formal 的补集（存活 ∧ ¬lost ∧ ¬eligible），在过滤发生处一次算清，下游无需理解 eligibility 规则；`ViewFrameResult` 是既有的"一次 step 实时输出"通道，加字段不破坏任何消费者。

**备选**：renderer 从 formal 反推（无法得知被过滤了什么，不可行）；trace 里存全量 track（体积膨胀且泄漏内部状态，否决）。

### D3：display-only 帧只标注、不造框；机制 A 与机制 B 的可视化责任严格分离

**决策**：`status in ("available_extrapolated", "fallback_valid_start")` 时，renderer **主动跳过全部 overlay 绘制**（formal/candidate bbox、footpoint、guidance ROI），只渲染源帧 + 画面固定位置的醒目横幅（如 `DISPLAY ONLY · TRACKING NOT STEPPED`）。不依赖"生产端现在恰好为空"——即使旧 trace、异常 trace 或未来生产端变化导致这些 tick 带有 detections 数据，renderer 也 SHALL NOT 画框。

**理由**：这是本 change 最重要的一条边界。机制 A 没有数据，任何"补框"都是伪造；横幅把"为什么没框"从猜测变成事实陈述。机制 B 由 candidate 层覆盖。两者互补而非冗余。renderer 端的主动禁止让 SHALL NOT 语义不随生产端演化而退化。

### D4：candidate 框统一标 `candidate`，不做 slot 状态反查

**决策**：候选框标签统一为 `track_<id> · tracker candidate` 形式的弱化文本——语义是"tracker 已经有这条轨迹，但它不是正式 Player_N"；细线（thickness 1）、低饱和色（如淡灰/淡黄），与 formal 框（thickness 2、高亮橙、`Player_N`）视觉强区分。

**理由**：`PlayerLockUpdate.player_states` 是 slot→state 映射，track 级精细状态需要反查 slot 的 `current_track_id`，属实现细节且易错；视觉区分已足以传达"已检测、未锁定"。列为可选增强，第一版不做。

### D5：court panel 横置等比重绘，显示层交换轴，canonical 坐标不动

**决策**：在 640×260 面板内：可用绘图区约 600×220（留边距/标题）；`scale = min(600/44, 220/20) = 11.0 px/ft`，球场约 484×220 px（真实 2.2:1）。屏幕映射 `screen_x ← y_ft`（44 ft 横轴）、`screen_y ← x_ft`（20 ft 纵轴），底层 canonical `(x_ft, y_ft)` 数据与 trajectory 完全不动。绘制线集：外边界 44×20、网 `y_ft=22`、两侧 NVZ line `y_ft=15/29`、两段 service centerline `x_ft=10, y_ft∈[0,15]∪[29,44]`。

**理由**：横置是 2.2:1 球场在宽面板里的唯一自然姿态；单一 scale 从数学上杜绝再次失真。几何计算提取为**纯函数**（`_court_layout()` 返回 origin/scale/court_width_px/court_height_px，`_court_to_panel(x_ft, y_ft, layout)` 做坐标映射），测试直接断言 `scale_x == scale_y`、`court_width_px/court_height_px ≈ 44/20`、网/NVZ/中线映射坐标与 clamp 行为，不靠 OpenCV 最终像素猜比例；MP4 级测试只守 `1280×620`。球员点沿用现有 canonical 坐标 `[0,20] × [0,44]` clamp（越界点的既有显示行为不变）与 `global_player_id` 文本标注。

**备选**：纵置 44 ft（面板高 260 放不下 2.2:1，会把 scale 压到 ~5 px/ft 更小，否决）；改 MP4 布局给 court 更大区域（违反 1280×620 契约，否决）。

## Risks / Trade-offs

- [candidate 框可能被用户误读为"正式检测已生效"] → 标签固定含 `tracker candidate` 字样 + 弱视觉样式 + summary 文档说明；spec 中明确 candidate 不得出现在任何正式产物。
- [candidate 数量不可预估] → candidate 是"所有 live 但 non-eligible tracks"的补集，背景人员、邻场干扰或 tracker 分身时完全可能超过 4 个；Debug Replay 诚实呈现全部候选、**不人为 cap**（隐藏证据比画面拥挤更危险），体积压力由可选字段缺失零开销 + debug-only 生命周期兜底。
- [`_tracks_to_frame_detections` 二次调用的性能] → 输入是同一帧已算好的 `tracks` 列表，纯列表过滤 + dataclass 构造，开销可忽略。
- [display-only 横幅遮挡画面] → 放在画面顶部状态行附近固定位置，与既有 status 文本同区域，不覆盖画面主体。
- [旧测试对 court panel 像素位置的断言可能失效] → 现有 renderer 测试若断言了旧坐标需同步更新；1280×620 尺寸断言保留不动。
- [cam-2 "3 秒后仍无框"属于另一问题（bootstrap/track 层缺陷）] → 本 change 验收分界：若 candidate 层上线后 3 秒内仍无任何候选框，说明是 detector/tracker 层问题，转交 `fix-multiview-cam1-bootstrap-4player` 类 change，不在本范围修。

## Migration Plan

纯增量、无迁移：旧 trace 无 `candidate_detections` 照常加载渲染（无候选框，行为等同现状）；新 trace 带字段时旧 renderer 忽略之（`view.get` 容错）。回滚 = revert 三个生产文件改动，无数据迁移。

## Open Questions

（无——两项待决策已在探索阶段拍板：可选字段方案 D1、统一 `candidate` 标签 D4。）
