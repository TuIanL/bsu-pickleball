## 1. 基线与验收夹具

- [x] 1.1 固化 `job-43e7475fd8` 对应素材的 7–13 秒回归窗口、reference view、canonical P2/P4 映射和现有 artifact 基线。
- [x] 1.2 定义并持久化 local-slot reassociation、bbox/footpoint residual、projection collision 和 display topology transition 的配置阈值。
- [x] 1.3 为 7–13 秒窗口增加结构化验收断言，覆盖 P2/P4 不换位、无未确认 local-slot 换绑、无正式轨迹污染和 overlay 安全降级。

## 2. 跨视角身份关联稳定性

- [x] 2.1 审计 `association_global.py`、`global_state.py` 和 `PlayerLockManager` 的 track、local slot、identity epoch 与 binding lineage，明确 track fragment 后可复用的连续性信息。
- [x] 2.2 实现 local slot reassociation 的连续证据门：组合 tracklet lineage、运动/side/quadrant、唯一槽位、margin 和 challenger 稳定性；证据不足时保持 incumbent 或输出 `ambiguous`/`unresolved`。
- [x] 2.3 确保受控 reassociation 的释放旧槽位、建立新绑定和同 tick 双射校验是原子且可追溯的，禁止 P2/P4 未确认互换。
- [x] 2.4 将带有 slot conflict、ambiguous 或冲突 fusion 证据的样本隔离，禁止其重置 roster、reanchor 其他球员或进入正式 canonical trajectory。
- [x] 2.5 为 local slot 标签抖动、track fragment、P2/P4 交叉和 reassociation pending/confirmed 补充 backend 单元测试。

## 3. Fused overlay 几何安全与防抖

- [x] 3.1 在 `fused_overlay_builder.py` 增加 bbox 底边中心与 projected footpoint 的一致性校验，并复核与其他可信球员框的 IoU/距离冲突。
- [x] 3.2 调整 projection collision、geometry jump 和 bbox-footpoint inconsistency 的 fallback：不满足复核时只允许一致的 `PROJECTED_POINT`、合格 hold 或 `HIDDEN`，不得显示脱离脚点的旧框。
- [x] 3.3 在 `overlay_display_state.py` 增加短窗 topology debounce/hold，限制连续无效投影导致的 box/point/hidden 往返，同时保留真实 bbox 立即恢复语义。
- [x] 3.4 确认 synthetic bbox 不刷新真实 bbox memory/scale profile，且 `evidence_type`、canonical `player_id` 和 bbox memory owner 始终保持诚实。
- [x] 3.5 为碰撞、脚点不一致、快速移动、真实观测恢复和短窗状态振荡补充 overlay/state-machine 单元测试。

## 4. 诊断与前端兼容

- [x] 4.1 扩展 `player-display-diagnostics.v1`，记录 local slot rebind 的 view、slot、epoch、old/new global、连续证据计数和原因。
- [x] 4.2 扩展 overlay/fusion quality diagnostics，记录 projection rejection、bbox-footpoint residual、fallback state、state sequence 和窗口 transition count。
- [x] 4.3 更新 artifact schema 校验、API 查询和前端类型/渲染兼容逻辑；旧 artifact 缺少新增字段时返回结构化 unavailable/default，不重新推断身份。
- [x] 4.4 增加诊断产物的序列化、反序列化、缺字段兼容和查询窗口测试。

## 5. 真实 Job 集成验收

- [x] 5.1 运行 backend/frontend 相关单元测试及 OpenSpec 验收脚本，确认既有单视角和旧 overlay 行为不回归。
- [x] 5.2 使用同一录制素材创建新的 analysis Job，禁止通过刷新旧 artifact 代替回归，并保存 baseline/new 结构化对照。
- [x] 5.3 检查新 Job 的 7–13 秒 `fused-trajectory`、`player-display-diagnostics`、`fused-player-overlay` 和质量产物，确认 P2/P4 identity、几何和污染门全部通过。
- [x] 5.4 在浏览器中回放约 7–13 秒，确认标签颜色、框/点形态和降级提示与 artifact 一致，无可见频闪或 P2/P4 互换。
- [x] 5.5 汇总回归指标、失败样本和配置快照；只有达到硬不变量与窗口验收门后才启用为默认 joint overlay 行为。
