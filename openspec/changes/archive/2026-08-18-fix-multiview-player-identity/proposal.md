## Why

joint_tracking_v2 双摄分析（job-222b3ca877）暴露四类可复现问题：① 联合分析页球员诊断接口 404（"This task has no player display diagnostics artifact."）；② 球场 minimap / 报告里 `playerMarkers.team` 按迭代序错位，出现"P1+P4 同侧、P2+P3 同侧"而非按近远端（P1P2 近 / P3P4 远）分组；③ 近端非常明显的球员未被识别出人体框（bootstrap 阶段被过滤）；④ 同一球员身份绑定不稳定（P1 ↔ P2 时互换）。这些问题叠加使"多视角球员身份"这一核心产品能力在展示层和稳定性上不可信，且当前无任何回归防护，后续改动可能再次引入。

## What Changes

- **后端：display diagnostics 产物兜底**：`multiview_joint_run` 构建失败/为空时仍产出 `status=unavailable` 的占位 payload；`multiview_result_composer` 对缺失产物 SHALL 写盘占位 artifact，保证查询 API 返回结构化 `unavailable` 而非 404。
- **查询 API 行为修正**：`GET /jobs/{id}/multiview/players/{player_id}/display-diagnostics` 在产物缺失时返回结构化 `unavailable`（HTTP 200 + status 字段或既有错误契约），前端按不适用状态展示。
- **前端 + 后端：`playerMarkers.team` 按 canonical 槽位语义赋值**：双打 `Player_1/Player_2 → near`、`Player_3/Player_4 → far`；单打 `Player_1 → near`、`Player_2 → far`。同时按 `Player_N` 数字排序 markers，保证 A-D 标签稳定对应 P1-P4。涉及 `src/services/pipelineReportAdapter.ts` 与 `backend/app/services/mock_analysis.py`。
- **后端：bootstrap 候选接受度修复**：放宽近端大尺寸球员（画面近端、bbox 大、清晰）在 bootstrap 阶段的过滤（`is_inside_tracking_area` / 中心距离 / 置信度门控），使近端右路球员能进入槽位锁定。
- **后端：身份绑定稳定性加固**：joint 关联器与 lock manager 的 reconnect 阶段加入"同侧优先 + 横向错配惩罚 + 悬挂期阈值"，阻止 P1↔P2 跨侧互换；必要时输出身份互换诊断事件供观测。
- **回归防护**：为上述四类问题增加自动化测试（产物兜底单测、team 语义单测、bootstrap 近端接纳单测、身份稳定性压力测试），并在相关 capability spec 中固化 MUST/SHALL 约束。

## Capabilities

### New Capabilities

- `multiview-player-identity-stability`: 覆盖多视角球员身份在展示层（team/label 语义）与时间维度（bootstrap 接纳、reconnect 同侧约束、互换防护）上的稳定性约束与回归防护。

### Modified Capabilities

- `player-display-diagnostics`: 产物缺失/构建失败时 MUST 产出占位 artifact（status=unavailable/failed），查询 API 不得因产物缺失返回 404（应返回结构化 unavailable）；诊断失败隔离语义扩展为"占位产物仍可见"。
- `player-identity-display`: `playerMarkers`/minimap 的 `team` 字段 MUST 按 canonical `Player_N` 槽位语义（双打 P1P2=near、P3P4=far；单打 P1=near、P2=far）赋值，MUST NOT 按遍历顺序；A-D 标签 MUST 稳定对应 P1-P4（按数字排序）。
- `player-lock-state-machine`: bootstrap 阶段 MUST 接纳画面近端的大尺寸高清晰候选（放宽 tracking area / 中心距离门控）；reconnect 阶段 MUST 施加同侧优先与横向错配惩罚，防止跨侧身份互换。

## Impact

- **后端文件**：`backend/app/vision/multiview/multiview_joint_run.py`（产物兜底）、`backend/app/services/multiview_result_composer.py`（占位写盘）、`backend/app/api/routes_analysis.py`（API 行为）、`backend/app/vision/multiview/player_display_diagnostics.py`（空产物构建）、`backend/app/services/mock_analysis.py`（team 语义）、`backend/app/vision/player_tracking_engine/player_lock_manager.py` 与 `backend/app/vision/multiview/association_global.py`（bootstrap/reconnect）。
- **前端文件**：`src/services/pipelineReportAdapter.ts`（team 语义 + 排序）、可能的 observability 页（unavailable 展示）。
- **测试**：新增/修改 `backend/tests/`（display diagnostics 兜底、team 语义、bootstrap、身份稳定性）与 `src/services/pipelineReportAdapter.test.ts`。
- **规格**：新增 `multiview-player-identity-stability` spec；修改 `player-display-diagnostics`、`player-identity-display`、`player-lock-state-machine` 三个 spec 的 delta。
- **风险**：bootstrap 放宽可能导致把非球员（裁判/观众）误锁进槽位——需以"脚点门控 + 象限归属"为硬约束兜底；reconnect 同侧约束可能略微降低极端横向跑动下的恢复率，需保留悬挂期阈值可配置。
