# 真实双摄 60 秒样例验收记录

日期：2026-08-23  
样例：`sync_20260720_122645_317228` / `ct_6949bef776a5`  
初始快速验证任务：`job-7681da443f`  
恢复官方采样密度后的复验任务：`job-4021da09d9`

## 输入与配置

- 输入窗口：`0–60,000 ms`，源视频 `60 FPS`。
- 初始快速验证：`frameStride=12`，共 `303` 个 canonical tick。
- 本次复验：`frameStride=2`，共 `1815` 个 canonical tick；页面发起的 0–60 秒窗口与原先 60 秒验证口径一致。
- 双摄：`cam_1 / camera 174`、`cam_2 / camera 175`。
- 标定：`calib-2cf5715434`、`calib-3c7930ff0d`。
- 同步：人工锚点、revision `0`，覆盖率 `80.38%`，Cam2 offset `36.196 ms`，残差 RMS `4.164 ms`。
- 球模型：`models/ball/tennis-ball.pt`，SHA-256 `4cae1d1239af94f19b9f37502ea9c0f10a82c04d22e7423bd4cf2764c6224f4e`。
- 球检测阈值：`0.18`；canonical 时间门：`16.667 ms`。

## 任务与页面结果

两次任务最终状态均为 `completed`，执行模式均为 `joint_tracking_v2`。恢复采样密度后的复验阶段结果如下：

- 素材与同步检查：`done`。
- 双摄协同跟踪：`done`，未再出现历史 mapping tuple 崩溃。
- 双摄球路分析：`unavailable`，原因是有效双摄证据不足。
- 运动指标、可视化、报告：均 `done`。

比赛库“球路”页已实际打开并核对：仍显示“多视角估算 3D 球路 / UNAVAILABLE / 双摄球路暂不可用”，可见球路数量为 `0`；没有把低质量点伪装成完整轨迹。

## 球侧证据统计

初始 `frameStride=12` 结果（基线）：

- detector calls：`589`。
- 候选数：`575`。
- 接受的视角观测：`210`。
- 双摄配对 / stereo measurement：`4 / 4`。
- 时间门拒绝：`0`。
- 未配对 tick：`299`。
- stereo coverage：`3.7%`。
- reprojection error：`124.459 px`。
- prediction ratio：`96.3%`。

恢复 `frameStride=2` 后的复验结果：

- canonical ticks：`1815`。
- detector calls：`3528`。
- 候选数：`3469`。
- 接受的视角观测：`1572`。
- 双摄配对 / stereo measurement：`26 / 26`。
- 时间门拒绝：`0`。
- 未配对 tick：`1789`。
- stereo coverage：`3.3%`。
- reprojection error：`197.502 px`。
- prediction ratio：`96.7%`。

复验的 `reconstructed_ball_trajectory.v3` 仍为 `UNAVAILABLE`，无可靠落点，符合质量门和页面降级语义。两个 Parent artifact URL 均可通过任务 artifact API 读取，状态与内容一致。

## 结论与已知限制

本次样例证明了“页面发起 → canonical 双摄联合跟踪 → 共享球候选检测 → stereo evidence → Parent artifact → 球路页面降级展示”的链路已经打通；同时验证了同步 offset 不会再被错误的原始 PTS 门控阻断（复验 `rejected_time_gate=0`）。恢复到 `1815` 个 tick 后，候选和双摄测量数量明显增加（`4 → 26`），因此之前的 `303` tick 不是唯一原因。

但该样例仍未通过“可用 3D 球路”验收：1815 tick 复验虽有 `26` 条原始双摄测量，但覆盖率仍只有 `3.3%`，回投误差升至 `197.502 px`，预测比例为 `96.7%`。这说明主要阻塞已不是分析时长或采样密度，而是球候选的跨视角关联稳定性、误检/漏检以及当前双摄几何/标定质量的综合问题。后续需要优先改进球检测与跨视角匹配、复核双摄几何/标定，或选取具有更稳定双视角球可见性的窗口，再复验覆盖率、回投误差和落点。
