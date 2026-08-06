# Design — 移除球员方向指示 + 前端轨迹位移断线

## Context

小地图（`CourtMinimap` + `videoOverlayHud.buildVideoOverlayHud`）从 `result.tracks`（`PipelineTrackPoint[]`，来自后端 `ProjectedTrackPoint`）构建球员尾迹。

现状两个问题（已在 job-6c0cc96f86 数据中验证）：

1. **方向指示不可靠**：`resolveMotion` 用最新 segment 的最后两个点计算单帧方向（`videoOverlayHud.ts:126-148`）。60fps 下单帧位移只有零点几英尺，方向噪声大；身份跳变时还会指向错误球员。方向不参与任何下游决策，纯展示。
2. **轨迹 V 形抽搐**：后端在 ~21.6s 把真 P1（track 6）丢失，身份锁把 P1 缝到 track 50（近右，P2 分身）与 track 46（远左另一人）并来回弹。身份层的滑动窗口平滑（window=5）把两个簇的接缝"糊"出 6-14 英尺的过渡点。前端 `splitAtGaps` 只按时间缺口（0.7s）断线，两个簇只差 0.03s，所以把过渡点连成一条线 → 小地图上画出一道跨越半场的 V 形扫线。

关键约束：**这是一个纯前端展示层修复**。不触碰后端身份锁定逻辑（根因，留作后续独立 change）。目标是让任何任务、任何身份跳变场景下，小地图都不会画出虚假的跨越式连线。

## Goals / Non-Goals

**Goals:**
- 彻底移除小地图球员方向指示（数据字段、箭头 marker、渲染），保留速度摘要。
- 球员尾迹在相邻两点位移超过阈值时断开为独立 segment，不画跨越跳变的直线。
- 低风险：只改前端两个文件 + 测试，不引入依赖，不改变数据来源。

**Non-Goals:**
- 不修后端身份锁（`PlayerLockManager` / `PlayerIdentityManager`）——错误身份拼接仍会发生，只是不再以连线形式暴露。
- 不把小地图数据源切换为 `player-render-trajectories` artifact（那是更大的改动，且该 artifact 用 raw 坐标更抖）。
- 不改变球轨迹的断线逻辑（球可合法高速移动，不应位移断线）。
- 不改变速度摘要的行为与单位逻辑。

## Decisions

### Decision 1: 移除方向指示（数据 + 渲染双端）

`videoOverlayHud.ts`:
- `HudPlayer.direction` 字段删除；`resolveMotion` 改为只返回 `speedMetersPerSecond`（函数更名 `resolveSpeed`，语义更清晰）。
- 其余 HUD 数据流不变（`speedMetersPerSecond` 仍用于底部摘要区）。

`CourtMinimap.tsx`:
- 删除 `<line markerEnd="url(#court-hud-arrow)" ...>` 方向箭头渲染。
- 删除 `<marker id="court-hud-arrow">` 定义。
- 停滞状态样式（`opacity`、虚线圆点、摘要"丢失"标记）保持不变。

**备选**：保留 `direction` 字段但隐藏渲染。否决——死代码与测试负担，且"方向不准"在未来不会再被开启，彻底删除最干净。

### Decision 2: 球员尾迹按位移断线

在 `videoOverlayHud.ts` 的轨迹分段逻辑中增加位移断线：

- 新增 option `maxTrailJumpFt?: number`，默认 `6.0`（与后端 `CourtTrackPostProcessor.max_spike_displacement_ft=6.0` 对齐；后端 segment 拆分阈值 9.84ft 更宽，但身份滑动窗口的过渡点可达 6-9ft，取 6ft 才能一并切断）。
- `splitAtGaps` 拆分条件扩展为：时间缺口 `> maxGapSeconds` **或** 相邻两点位移 `> maxTrailJumpFt` 时开新 segment。
- 仅作用于球员轨迹（`splitAtGaps` 目前被球员与球共用——球路径调用处传 `maxTrailJumpFt: Infinity` 或单独入口，保持球轨迹只按时间断线）。

**为什么不放在后端**：后端 `player-render-trajectories` 的 post-processor 已按 9.84ft 拆段，但小地图实际消费的是 `result.tracks`（身份平滑后），不经过该拆段。修后端意味着改动平滑/身份链路或切换数据源，风险与回归面远大于前端一处断线。

**为什么 6ft 不会误伤合法移动**：`result.tracks` 在 stride=2（1/30s）下，相邻样本位移超过 6ft 意味着 ≥180 ft/s 的瞬时速度，远超人类极限（冲刺 ~26 ft/s）。6ft 阈值只会在"身份拼接/投影跳变"这类异常时触发。

### Decision 3: 规格层面把"方向"从需求中移除

- 原需求"显示球员方向和可解释的移动摘要"中方向部分整体移除，速度摘要拆成独立需求"显示可解释的球员速度摘要"。
- "同步显示球员移动轨迹"补充位移断线语义。
- "滞后球员点位显示停滞状态"去掉对方向箭头的引用。

## Risks / Trade-offs

- [身份跳变时 P1 圆点仍会短暂出现在错误球员位置（0.5-0.6s）] → 这是数据层问题，本 change 只消除"虚假连线"，不消除错误定位；根治需后续身份锁 change。建议在任务说明中明确此边界。
- [6ft 断线在极端合法场景（如球员摔倒/鱼跃扑救）可能误断] → 概率极低且后果轻微（尾迹多断一段，不画假线），接受。
- [修改 `splitAtGaps` 影响球轨迹调用] → 通过传参隔离，球轨迹行为不变，由既有球轨迹测试守护。
