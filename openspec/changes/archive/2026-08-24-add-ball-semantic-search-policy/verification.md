# 真实双摄片段核对记录

核对日期：2026-08-24

## 素材

- CaptureTake：`ct_2d7316936aac`
- 双摄 take：`/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_112124_00d84c`
- 视频：`174_merged.mp4`、`175_merged.mp4`
- 画面：真实室内匹克球场；两路视频均为 1920×1080、约 543 秒
- 时间线：使用该 take 自带的 `timeline/events.json`，来源包含 manual/corrected/algorithm，未修改球模型 `models/ball/tennis-ball.pt`

## 人工抽样与策略结果

| 时间（秒） | 画面语义 | 双摄 raw candidates | phase | action | 结论 |
|---:|---|---:|---|---|---|
| 70.0 | 回合外，球员离场/准备 | 1 + 1 | `NON_PLAY_CONFIRMED` | `suppress_formal` | 不让场外候选进入正式球链 |
| 80.0 | 回合间，球员仍在整理 | 2 + 1 | `POST_RALLY` | `suppress_formal` | 不让误检污染下一分 |
| 89.5 | 下一分前的发球准备 | 1 + 1 | `PRE_SERVE` | `serve_reacquire` | 重新打开发球区域搜索 |
| 90.5 | 发球动作已 armed | 3 + 0 | `SERVE_ARMED` | `serve_reacquire` | 保持渐进式重新捕获 |
| 91.2 | 人工标记的正式回合 | 2 + 1 | `RALLY_ACTIVE` | `allow` | 正式球路搜索恢复 |
| 96.8 | 回合内 | 1 + 0 | `RALLY_ACTIVE` | `allow` | 未因单视角丢失而关闭回合 |
| 97.5 | 回合结束后捡球 | 1 + 0 | `NON_PLAY_CONFIRMED` | `suppress_formal` | 结束该回合的正式球搜索 |
| 100.0 | 下一分准备间隔 | 2 + 1 | `NON_PLAY_CONFIRMED` | `suppress_formal` | 保持抑制，等待新的发球证据 |

## 样本结论

- 选取的非比赛/捡球样本中没有 raw candidate 进入 formal publish。
- 选取的发球准备和正式回合样本没有被 semantic hard gate 错误压制。
- 96.8 秒只保留一视角候选时，状态仍为 `RALLY_ACTIVE`，没有因为一次视角丢失提前关闭回合。
- 这是一组固定边界抽样，不替代全视频人工标注；后续若调整阈值，应重新核对同一组时间点。
