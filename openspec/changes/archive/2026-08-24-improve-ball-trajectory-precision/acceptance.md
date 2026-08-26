# 球检测与球路精度门验收记录

日期：2026-08-24
变更：`improve-ball-trajectory-precision`
质量门版本：`ball_quality_gates.v1`

## 1. Hard-negative 回放

固定 fixture：`backend/fixtures/ball_trajectory/ball_quality_gate_hard_negatives.v1.json`。

覆盖以下误检/边界类型：

- 场边设备：投影到球场环境边界外时拒绝；
- 广告区域：候选框面积超过上限时拒绝；
- 网柱：极端长宽比拒绝；
- 网后物体：投影越过环境边界时拒绝；
- 检测 ROI 外物体：拒绝；
- 遮挡：短缺口允许插值，长缺口标记 `long_gap`；
- 高速物体：超速度跳变拒绝；合法高速球仍通过运动门。

回放测试：`backend/tests/test_ball_quality_gate_fixture.py`，共 3 个测试。

## 2. 真实双摄样例对比

样例：`sync_20260720_122645_317228` / `ct_6949bef776a5`，0–60 秒，60 FPS，stride 2。

旧链路：`job-4021da09d9`。新链路：`job-71166f62f7`。原始双摄 pair 没有人工 GT，因此“precision”不能冒充模型真值 precision；本记录同时给出可审计的质量门通过率代理。

| 指标 | 旧链路 | 新链路/回放 | 结论 |
| --- | ---: | ---: | --- |
| 双摄 pair 数 | 26 | 26 | 候选证据保留，低质量 pair 不再默认成为 anchor |
| pair 质量门通过代理 | 未区分，26/26 进入 evidence | 8/26 trusted anchor（30.8%），18/26 audit-only | 18 个 pair 只保留诊断 |
| stereo coverage | 3.3% | 30.8% segment evidence coverage | 证据不再直接等同于可发布轨迹 |
| reprojection error | 197.502 px | 0.021 px（接受 pair 的产物统计） | 新链路显著收紧异常几何 |
| 默认展示合格率 | v3 `UNAVAILABLE`，0 条可展示曲线 | v4 90 段中 88 段为 `medium`，2 段 `none`；按本变更发布规则为 88/90（97.8%） | 低质量段不进入默认展示 |
| 错误球路秒数 | 无 GT，无法给真值 | 无 GT，无法给真值 | 用下方“长缺口跨越代理”监控 |

### 单视角长缺口回放

使用同源真实样例历史原始产物 `job-96a28d6ff0/ball_trajectory.json`，对比历史 frame-count 插值和本变更的秒级插值上限：

- 旧清洗产物：923 个有坐标点，其中 337 个为插值点；
- 新规则离线重放：695 个有坐标点，其中 109 个为插值点；
- 历史插值点中有 228 个来自超过 0.20 秒的缺口，约 7.60 秒的“合成轨迹点”被新规则降级为不可发布；
- 新规则标记 1,112 个缺失点为 `gap_boundary_reason=long_gap`，不跨长缺口连线；
- 因缺少逐帧人工真值，7.60 秒是“被质量门移除的旧合成路径时间”代理，不宣称全部都是错误球路秒数。

## 3. 阈值校准结果

当前配置快照写入 raw、cleaned、stereo evidence 和 reconstructed artifact：

| 规则 | 值 |
| --- | ---: |
| 最低置信度 | 0.22 |
| 最大框面积占比 | 0.004 |
| 最大长宽比 | 4.0 |
| 最小框边长 | 2 px |
| 球场环境边界 margin | 2 ft |
| 最大插值缺口 | 0.20 s |
| 最大图像速度 | 12,000 px/s |
| 最大图像加速度 | 350,000 px/s² |
| 最大方向突变 | 170° |
| 最大双摄回投误差 | 24 px |
| 最小双摄几何质量 | 0.40 |
| 最小 pair 分数余量 | 0.08 |

已知召回损失：没有标注 Gold Set，当前只能确认规则会主动牺牲低置信度、超大框、场外投影、超长缺口和低质量双摄 anchor 的召回；不能从现有产物估计真实球漏检率。后续应在标注工作台形成 Gold Set 后再校准召回与 precision。

## 4. 发布与回退方案

1. 每个新任务在 diagnostics 中记录 `quality_gate_version=ball_quality_gates.v1` 和阈值快照；历史 artifact 保持不可变。
2. 若真实 Gold Set 显示召回损失超出接受范围，优先将任务配置回退到上一版 `quality_gate_version`，重新生成新任务 artifact，不覆盖旧 artifact。
3. 发布回退的最低验证集为本 fixture、现有 tracker/stereo/hybrid 回归集和上述真实双摄样例；回退后仍保留拒绝原因以便定位差异。
4. 当前版本没有把低质量 pair 或长缺口结果静默删除：它们进入 audit/diagnostics，前端默认只消费 `display_eligible` 段。

## 5. 自动化验证

- 质量门、tracker、时序清洗与球分析回归：28 passed；
- hybrid/artifact 回归：16 passed；
- 双摄主链、canonical、artifact、feature flag、segment view：26 passed；
- 前端全量：78 files / 586 tests passed；
- 前端生产构建：通过；
- `git diff --check`：通过。
