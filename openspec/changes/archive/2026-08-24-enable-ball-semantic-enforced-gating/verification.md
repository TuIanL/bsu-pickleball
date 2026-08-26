# 第二阶段真实双摄 Enforced 回放记录

核对日期：2026-08-24

## 素材与运行约束

- CaptureTake：`ct_2d7316936aac`
- 双摄目录：`/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_112124_00d84c`
- 视频：`174_merged.mp4`、`175_merged.mp4`
- 视频信息：两路 1920×1080、60 FPS；抽样使用同一 canonical 秒时间点
- 时间线：该 take 自带 `timeline/events.json`；权威阶段来自 manual/corrected 事件
- detector model：`models/ball/tennis-ball.pt`，模型文件未修改
- rollout：`mode=enforced`、`enforced_rollout_enabled=true`、`rollout_id=real-20260720-take-ct_2d7316936aac`
- Shadow-vs-Enforced 使用同一时间点、同一 raw detector candidates；Enforced 对照没有重复运行 detector

89.5 秒和 90.5 秒的 `serve_candidate_confidence`/`serve_armed` 是沿用第一阶段已经核对过的发球候选 evidence，用于验证发球预热分支；两路 raw candidates 仍来自本次真实视频和未修改模型。

## 抽样结果

| 时间（秒） | raw candidates（174+175） | phase | boundary action | Shadow formal | Enforced 结果 | 结论 |
|---:|---:|---|---|---|---|---|
| 70.0 | 1+1=2 | `NON_PLAY_CONFIRMED` | `seal_formal_segment` | allow | suppress，formal=0 | 回合外候选不进入正式球链 |
| 80.0 | 2+1=3 | `POST_RALLY` | none（已完成边沿） | allow | suppress，formal=0 | 回合间误检继续被抑制 |
| 89.5 | 1+1=2 | `PRE_SERVE` | `warm_reacquire` | serve reacquire | warm，formal=0 | 发球预热不发布手持/静止候选 |
| 90.5 | 3+0=3 | `SERVE_ARMED` | `serve_reacquire` | serve reacquire | warm，formal=0 | 单视角候选不直接污染正式段 |
| 91.2 | 2+1=3 | `RALLY_ACTIVE` | `open_formal_segment` | allow | allow，formal=3 | 正式回合恢复捕获 |
| 96.8 | 1+0=1 | `RALLY_ACTIVE` | none（同一 action id） | allow | allow，formal=1 | 一路短时丢失不关闭回合 |
| 97.5 | 1+0=1 | `NON_PLAY_CONFIRMED` | `seal_formal_segment` | allow | suppress，formal=0 | 回合结束后封存并禁止跨段发布 |
| 100.0 | 2+1=3 | `NON_PLAY_CONFIRMED` | none（已完成边沿） | allow | suppress，formal=0 | 后续捡球/准备阶段保持抑制 |

## 结论与限制

- 权威非比赛窗口内，Enforced 正式候选数为 0；raw detector evidence 仍被保留。
- `PRE_SERVE`/`SERVE_ARMED` 阶段只进入 warm/reacquire，不直接写 formal trajectory。
- `RALLY_ACTIVE` 阶段恢复正式候选；96.8 秒单视角 raw 缺失没有触发语义结束。
- `open_formal_segment` 和 `seal_formal_segment` 使用稳定 action id；同一 action 在后续 tick 不重复 reset/封存。
- 本记录是固定边界抽样，不替代整段视频人工标注；算法 authority 仍保持软约束，未作为 Enforced hard gate。
