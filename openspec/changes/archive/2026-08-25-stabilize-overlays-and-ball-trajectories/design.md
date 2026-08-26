## Context

当前 joint_tracking_v2 的球员 overlay 由参考视角检测、donor 视角证据、canonical 融合位置和 target-view projection 共同生成。P2/P4 在参考视角出现短时关联缺失或歧义时，builder 会在 `base_observed` 与 `cross_view_projected` 之间快速切换；虽然 canonical identity 没有被判定为交换，但两类证据的 bbox 几何不同，最终表现为框闪烁和相互覆盖。

球路重建则按 flight segment 选择 `primary_view_id`。该选择适合段级重建质量评估，但不适合作为视频叠加的坐标空间。当前播放器在缺少显式 `trajectoryViewId` 时使用每个 segment 的主视角，并对结束片段保留短尾迹，导致相邻片段可能在同一时刻并行绘制，且不同摄像头的 image-space 坐标可能被画到同一个视频上。

本设计需要同时调整关联、融合、展示状态机、segment artifact 和视频 renderer，约束是保留 canonical Player_N 身份、保留现有证据诚实性、兼容旧 artifact，并且不把本次变更扩大到球检测模型或 RTMPose 接入。

## Goals / Non-Goals

**Goals:**

- 让参考视角的 P2/P4 关联在短时漏检、弱观测和候选歧义下保持 incumbent，不因单帧变化反复切换。
- 让跨视角投影只在目标视角、几何、连续性和碰撞门控均通过时进入正式 overlay。
- 在 `base_observed`、`guided_observed`、`cross_view_projected` 等证据切换时保持展示 bbox 的时间连续性，同时不篡改 `evidence_type`。
- 为视频球路定义唯一的 `render_view_id`，优先使用任务 reference view；segment 内部的 `primary_view_id` 只用于重建与质量解释。
- 让相邻 segment 使用半开时间区间和唯一活动 segment 规则，消除边界重复、旧尾迹与新轨迹重叠。
- 为上述行为提供可审计字段和确定性回归测试。

**Non-Goals:**

- 不在本变更中提升球 detector 的召回率、重新训练模型或修复所有漏球。
- 不在本变更中接入 RTMPose、生成骨架或改变 canonical player identity 逻辑。
- 不把跨视角投影伪装成本视角真实检测；证据 provenance 和 `source_confidence` 仍保持诚实。
- 不重新设计球场标定或改变已有 canonical court frame 的单位与坐标定义。

## Decisions

### 1. 关联层保持 incumbent，展示层单独稳定几何

沿用 `PendingReassociation`，将 reference-view association 的 incumbent、challenger、连续强证据计数和最后可信 tick 作为显式状态。缺失关联、歧义 pair、低于 `switch_margin` 的候选只记录 diagnostics，不改变当前 `(view_id, view_player_id) → global_player_id` 绑定；只有连续满足几何可行、优势 margin 和同一 challenger 的证据才允许切换。

球员展示状态仍按 `(job_id, reference_view_id, canonical_player_id)` 隔离。`evidence_type` 始终记录当前 tick 的真实来源；展示状态机另外维护上一份 presentation geometry、最后可信真实框和 projected geometry。这样可以稳定 bbox 的位置/尺寸，但不会把投影框标成真实框。

替代方案：直接把上一帧的 `evidence_type` 延续到当前帧。该方案会掩盖真实漏检，不符合现有 provenance 契约，因此不采用。

### 2. 投影框必须通过连续性与碰撞门控

跨视角投影在写入 `cross_view_projected` 前，除现有 donor recency、canonical position 和 geometry valid 外，增加：

- 相对上一份可信 presentation geometry 的位移、尺度和脚点速度门控，使用真实时间差而不是 tick 数。
- 与参考视角其他球员 strong/accepted bbox 的重叠门控；若投影框会明显覆盖另一名球员，优先降级为 footpoint 或保持上一份稳定几何，而不是发布可疑 bbox。
- 投影残差、目标视角可见范围和不确定性/质量摘要进入 diagnostics；仅“落在图像范围内”不再等同于视觉上可信。

投影通过后，使用上一份合格 bbox 的尺寸或冻结的 view scale profile 进行连续 reanchor；不通过时禁止新 synthetic bbox 污染 bbox memory。`evidence_type` 仍可为 `cross_view_projected`，但 `display_state` 可降级为 `PROJECTED_POINT` 或短时复用稳定几何。

替代方案：仅加 CSS/SVG transition。它只能缓和 opacity，无法解决坐标空间错误、投影碰撞和 bbox 突变，因此不采用。

### 3. 区分重建主视角与视频渲染视角

在 reconstructed trajectory 的消费边界确定 `render_view_id`：默认等于任务的 `reference_view_id`，并在视频分析页明确传入。每个 segment 的 `primary_view_id` 仍保留，用于描述该段最佳证据和重建质量，但不得决定视频叠加坐标空间。

视频 renderer 只读取 `image_paths_by_view[render_view_id]`。若该 segment 没有目标视角的有效 image path，则按以下顺序处理：使用后端提供的 target-view reprojected path；否则将该 segment 标为 video-overlay unavailable 并保持球场/报告侧数据，不把另一摄像头坐标直接绘制到当前视频上。

替代方案：继续按每段 `primary_view_id` 直接绘制。该方案在跨 segment 切换时不可避免地混合像素坐标，因此不采用。统一把所有轨迹先转成 canonical court 坐标再由前端投影也可行，但会把标定和投影责任重新放回前端，暂不采用。

### 4. 使用半开区间和单活动 segment 合成尾迹

将 segment 的视频显示窗口定义为 `[start_ms, end_ms)`，相邻 segment 共享边界时只归后一个 segment。已结束 segment 的 retention 只允许在“没有后继 segment 已开始”的情况下生效；一旦后继 segment 进入显示窗口，前一 segment 的尾迹立即停止，或只保留一个去重后的公共端点，不得同时绘制两条完整路径。

renderer 在每个播放时刻先按 `render_view_id`、时间窗口和 `segment_id` 去重，再选择唯一 active segment；segment 切换时不跨边界拼接 geometry。该规则保留片段结束端点的可读性，但消除 33 秒左右的双轨迹。

替代方案：继续保留固定 0.8 秒的所有已结束 segment。它能产生尾迹效果，但会与后继片段重叠，无法保证一球一条当前轨迹，因此不采用。

### 5. 以诊断和回放 fixture 作为验收入口

后端 artifact 记录 reference-view association、投影拒绝原因、geometry hold/降级原因、`render_view_id`、segment boundary policy 和 target-view path availability。测试使用固定回放 fixture 覆盖：P2/P4 在 8–13 秒的快速证据变化、投影框与其他球员框碰撞、33.166 秒相邻 segment 边界、primary view 在 cam_1/cam_2 间切换、缺少目标视角 image path。

## Risks / Trade-offs

- [Risk] 更严格的投影/碰撞门控可能减少画面中可见的人物框。→ 以稳定 footpoint 或 `PROJECTED_POINT` 降级，并输出明确 reason code，优先避免错误框覆盖真实球员。
- [Risk] 固定 reference view 后，某些片段在当前视频上没有可用图像坐标。→ 保留 court-space/报告侧 segment，视频层显示不可用状态，不跨视角错画；后续可单独补充后端 reprojected path。
- [Risk] 几何连续性约束会使真实快速移动的框短暂滞后。→ 使用真实时间差、速度/尺度上限和 hard stop；新 strong real bbox 仍允许立即恢复，避免长期追踪滞后。
- [Risk] 半开区间会改变旧任务尾迹的视觉时长。→ 保留旧 artifact 的兼容读取；新 renderer 仅对声明新 boundary policy 的产物启用严格规则，旧产物使用兼容模式并记录 warning。
- [Risk] 前后端同时变更期间字段不一致。→ 所有新增字段可选，旧字段继续作为 fallback；增加 schema contract test，未提供目标视角路径时不得静默使用其他视角坐标。

## Migration Plan

1. 先实现后端 association/projection diagnostics 与 target-view trajectory 字段，并为新产物写入 `render_view_id` 和 boundary policy。
2. 再更新前端消费逻辑：优先读取 target-view path，启用单活动 segment 与边界去重；旧 artifact 保持兼容并记录降级原因。
3. 使用固定任务回放和现有 API 对比 8–13 秒球员框、33 秒球路边界及全屏/非全屏播放器结果。
4. 若新规则导致异常，可通过关闭新 `boundary_policy`/target-view compositor feature flag 回滚到旧渲染路径；不删除或重写历史 artifact。

## Open Questions

- target-view reprojected path 是在 artifact 生成阶段落盘，还是在前端仅消费已有 `image_paths_by_view`；本变更默认优先后端落盘，缺失时安全不渲染。
- 投影框与其他强框的重叠门限应按 IoU、脚点距离还是 court-space 距离定义；实现前需要结合现有 calibrated view diagnostics 确认默认值。
- 新产物的 `boundary_policy` 是否直接升级 reconstructed trajectory schema，还是作为可选 metadata 字段加入现有 v4 artifact；默认采用可选字段以降低历史任务迁移成本。
