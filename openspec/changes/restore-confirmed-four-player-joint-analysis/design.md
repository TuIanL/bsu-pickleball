## Context

`job-9a640b069a` 的 Job 冻结名册为四人、两端各两人；joint executor 创建 `MultiViewJointRun` 时只传入视频、标定、同步与跟踪对象，没有传入该名册。Global Roster 按候选出现顺序分配四个全局槽位，满槽后新观测进入 recovery ledger。本次运行四槽都被占用，但 `roster_state=BOOTSTRAPPING`、`confirmed_player_count=0`、`unresolved_no_slot=58996`。最终融合轨迹只有 global_player_2/3 有较长的有效样本，且都位于 canonical B 端；global_player_1/4 近乎空白。结果组装用顺序 fallback 补出 `Player_N`，热力图与 overlay 因而呈现看似确定的 P 标签。

现有 `bootstrap_binding_audit` 隶属于 canonical Rally/Shot 组合；该组合失败时审计文件也缺失。本次 Rally/Shot 因 `REASON_BINDING_AMBIGUOUS_MATCH` 导入错误失败，进一步说明身份审计不能依赖球事件组合的成功。当前代码中的常量可正常导入；具体运行进程与源码不一致的原因留给独立的运行环境排查。

## 2026-09-28 诊断 Job 的首断点定位（`job-faf852782a`）

`verification-real-take.md` 记录的 120 秒诊断 Job 由用户执行，产物已落盘。2026-10-03 对该产物做只读复核，定位到首个可证断点，并纠正了此前「四人身份链最脆弱一环」的表述。

### 事实基线（读自产物，非页面显示）

- Job `canonicalStatus=succeeded` / `displayStatus=completed` / progress 100，`clipStartMs=0`、`clipEndMs=120000`、`debugTraceEnabled=true`、`jointRunId=mvr_b6e5d8762956`。
- 名册 hash 为 `0abcee71…`，与本 change 早前记录的 `edfb8e4a…` **不同**；名册已变更，锚点时间（55.5s / 57.5s / 62.5s）与旧描述不可直接沿用。
- 同源另有两个未记录 Job：同一秒创建的 `job-d78bf4a20a`（stage=segment，07:02 取消）与 09-29 的 `job-c5acfce089`（另一 take，77% 取消）。
- 逐槽位 metric-eligible：P1=0、P2=2162、P3=0、P4=2982；`verdict=fail`，`confirmed_roster_count=2`。
- `global_player_4`（真 P4）2982 个 eligible 样本 **100% 落在 end_b**，coverage 0.825 已过 0.70 门槛。
- raw funnel 41,805 个检测框，ROI 未进一步过滤。

**结论：检测与跟踪层不是瓶颈。** 三条身份门槛失败（`confirmed_roster`、`canonical_identity_anchors_confirmed`、`two_confirmed_players_per_canonical_end`）全部产生于身份裁决层。P4 具备合格轨迹却被判未确认。

### 断点 A：tracklet 竞争的裁决方向相反

`anchor_binding_audit.entries[Player_4]` 记录 `global_player_2`、`tracklet_lineage_id="Player_3:epoch:0"`、evidence `track_id=388`、IoU 0.8575、court 距离 0.6614ft——是四槽中最干净的锚点匹配。但 track 388 的本地身份标签已被 P3 占用（`roster.json` 中 `global_player_2` 的 cam_1 binding 即 `Player_3:epoch:0` / track 388，`mapping_method=unconfirmed_anchor`）。

`multiview_joint_run.py:1410-1420` 的处理是：把**后到**的 P3 标为 `bootstrap_binding_tracklet_competes_for_slots`，而**先到**的 P4 反而获得该 tracklet 的确认资格。即「先到先得」。这与 design Decision 1 的「一对一约束」和 Decision 2 的「占用者应让位」意图相反：应保留证据更强（IoU 更高、court 距离更近）的一方，另一方落回待裁决池并保留竞争证据。

附带效应：P3 的失败原因「同一检测轨迹竞争多个名册槽」正是本条裁决产生的结果，而非独立的第二个断点。

### 断点 B：`roster_end` 是一次性赋值且不可回退

`global_state.py:403`：`if expected_end and state.roster_end and expected_end != state.roster_end: return False, "anchor_global_end_conflict"`。

`state.roster_end` 在锚点时刻**之前**由 global 关联阶段写入。`global_player_2` 实测 2561 个 eligible 样本横跨两端（end_a 852 / end_b 1709），锚点前取定 end_a，而 P4 冻结端位为 end_b → 永久冲突。此后的 1709 个 end_b 样本无法纠正该判定，锚点匹配即便 IoU 0.8575 也只能得到 `anchor_global_end_conflict`。

这把「某一时刻的端位估计」当作「不可变的身份约束」，与 Decision 2 中「端位不明观测留在待裁决池」不一致。端位在证据充分时应可随观测修订，冲突应触发重新裁决而非直接拒绝。

### 断点 C：同一 Job 产物内存在双源真相

同一 Job 对同一 P 槽位给出互斥结论：

| 来源 | P2 | P4 |
|---|---|---|
| `roster.json`（`mapping_confirmed`） | true | true（`anchor_simultaneous_match`，IoU 0.8575） |
| `frozen_roster.anchor_binding_audit` | confirmed | `anchor_global_end_conflict` |
| `bootstrap_binding_audit.json` | `no_formal_observation` | `no_formal_observation` |

第三份文件整体 `status="unavailable"` / `unavailable_reason="bootstrap_binding_failed"`，四槽全部 `confirmed=false`，与前两者均冲突（其内容由 Rally/Shot 组合补写，来源不干净）。

放大机制：`four_player_quality.py:302` 的 `mapping_confirmed_by_player` 读 `roster.json`，而 `:308-321` 的 `expected_end_by_player` 与 `identity_slots` 读 `anchor_binding_audit`。因此覆盖率门槛按前者判定（通过），页面状态卡按后者渲染（未确认）——**热力图与散点图敢画 P4，状态卡同时显示 P4 未确认且有效点为 0**。

这违反 Decision 1 末段「joint run 是身份审计的权威来源，Rally/Shot 只读消费」：现状是两份产物互不参考，且覆盖率与展示各自选了对自己有利的那份。

### 对验收路径的影响

首断点已定位到裁决语义，无需再跑全片盲试。Decision 4 期望的「`mapping_confirmed=false` 导致的零覆盖 SHALL 与检测为零区分」在本例中**没有生效**——P4 的覆盖率为 0.825 且被计入通过，却又在状态卡显示未确认，说明两个口径未收敛。

### 实施后的复核结论（2026-10-03）

读取 `fused_diagnostics.roster` 后**修正了上文对 P4 的判断**：P4 在 `global_player_4` 上**绑定成功**（`frozen_identity_confirmed=true`、from_ms=55500）。真正的问题有三个，都已修：

1. **P4 名字被两个 global 同时占用**。`global_player_3`（end_b）经 `_roster_canonical_player_id` 回退到 reference view 本地标签，也报 `Player_4`。
2. **个人图层准入读错了来源**。`_build_roster_map` 的 `confirmed_only` 分支读 registry 快照的 `frozen_identity_confirmed`，而状态卡读审计——这是「热力图绘制 P4 + 状态卡声明 P4 未确认」的直接原因。
3. **锚点匹配的竞争裁决在更上游**。`analysis_roster_runtime.match_anchor_observations` 用 `conflicting_slots` 把所有竞争者一起判失败，先到者因此独占 tracklet；`multiview_joint_run.py:1410` 只是它的下游表现。

修复后用同一 Job 产物重跑质量组装：P4 变为 `unconfirmed` / 0 有效点（与状态卡一致），新增 `identity_audit_single_source=false` 硬门槛，`Player_4.coverage` 从「通过」转为「失败」——后者是修复前被双源掩盖的真实结论。

## Goals / Non-Goals

**Goals:**

- 让 Job 冻结名册在 joint 跟踪、身份审计、展示和指标中使用同一映射，并保存可复核证据。
- 让双打 Global Roster 在 canonical 端位上保有 2+2 的候选空间，避免同端重复目标永久占满四槽。
- 对真实缺人进行逐层定位与恢复；质量不足时结果可见但不声称四人识别完成。
- 用新的全片真实 Job 验证四人覆盖和两端归属，保留旧结果作为基线。

**Non-Goals:**

- 凭赛前框选在全片生成不存在的视频检测框，或把未来锚点位置直接投射到前面的时间。
- 在缺少唯一证据时强行把两个 global track 合并、改名或交换身份。
- 改动球路、Rally/Shot 或厨房线算法；其导入错误另行修复，不作为四人跟踪通过的替代条件。

## Decisions

### 1. 冻结名册是身份约束，观测仍来自视频

Executor 在启动前按 Job ID 读取 `AnalysisRosterSnapshot`，校验 `rosterSnapshotHash`、四个不同的槽位、Team 归属、初始端位、锚点机位/时间和标定坐标系。将只读 `RosterAnchorSet` 传给 joint run。Job 没有可用名册时沿用现有普通分析路径，输出明确的 identity-unavailable 原因。

锚点在其时间窗内与正式检测/tracklet 做唯一匹配，形成 `P slot ↔ global_player_id ↔ source track lineage` 审计；时间窗外仅通过已核验的连续轨迹传播身份。匹配结合时间、同机位 bbox、canonical 球场距离、两机位一致性与可用外观，采用一对一约束。外观处于 shadow 模式时不得作为唯一决定证据。选择此方式，因为用户的 P 编号是事实输入，但一次画面框并不能证明整场每一帧的身份。直接用 `Player_N` 字符串或固定 global 槽序会重现本次错标。

用户执行的 120 秒任务进一步显示：冻结框可与同机位、同时刻的候选 bbox 完全重合，但候选尚无可用球场投影，因此没有进入位置关联。为保留这类人工锚点证据，joint run 另建 bbox/time-only anchor evidence observation；它只负责建立 `(view, raw track id)` 到冻结槽的待确认联系，不进入全局位置更新。之后同一 raw track 一旦成为正式位置观测并获得 global ID，才尝试确认冻结槽。冻结锚点生命周期按 raw track ID 标识，避免同一个 `Player_N:epoch` 被复用时串接不同轨迹。

审计由球员跟踪/结果组装独立产生并原子落盘，Rally/Shot、overlay、热力图和报告只读消费；Rally/Shot 失败不阻断审计。原有 `/artifacts/bootstrap-binding-audit` 路径保留。

Rally/Shot 可用自己构建的绑定审计控制回合和 Team 语义，但不能覆写 joint run 的来源轨迹审计文件；仅当独立审计文件不存在时允许它补写，以保留失败样本的 raw track 与拒绝原因。

### 2. Global Roster 按 canonical 端位维护候选与占位

双打时采用 end_a/end_b 各两人的容量；每个候选以 `local_to_canonical` 后的坐标分端，端位不明确的观测留在待裁决池，不以 fallback 消耗另一端配额。对同端重复候选，优先使用同 tick 不重复、轨迹持续性、锚点匹配和跨机位证据裁决。未确认且长期无观测的 provisional occupant 可以在记录替换原因及历史后释放；已确认身份不得仅因短时漏检被替换。满槽但另一端仍缺真实球员时，recovery ledger 应继续累积并允许符合证据门槛的候选替换错误 provisional，占用/拒绝原因逐人可查。

选择端位配额而非仅调整 YOLO 置信度，因为本次已有四个候选晋升、但四人中两条正式轨迹几乎为空，说明槽位竞争与后续恢复至少是独立断点。用户执行的 120 秒 Job 显示 41,805 个 raw detections 且 ROI 未进一步过滤，首个可证断点在锚点候选与局部 P 身份/全局关联之间；修复相应 track identity 入口，不调整检测阈值。

### 3. 明确三种身份状态并控制发布

每个球员结果区分 `observed_unbound`（真实观测、尚未绑定 P）、`confirmed`（锚点审计通过）、`unavailable`（无可靠观测或冲突）。Global Roster 可以继续保存内部 `global_player_id`；对用户展示的 P1–P4 只来自确认后的冻结名册映射。未绑定的真实观测可展示中性“未确认球员”及证据类型，不能使用顺序 fallback 的 P 标签、Team 或个人热力图。区域图和合并热力图可以保留匿名有效样本，但不得将其说成四人正式结果；四个冻结槽位均有独立状态与缺失原因。身份确认后，overlay 与热力图使用同一只读映射。

现行固定 `Player_1/2=near、Player_3/4=far` 仅适用于特定相机朝向。本次参考机位的 A 端是画面远端。正式分侧以 `initial_team_a_end` 和 canonical end_a/end_b 为准，再投影到当前展示机位；历史 Job 没有冻结名册时维持旧展示语义并标记来源。

### 4. 质量产物拆分“看到人”和“确认身份”

`four-player-identification-quality` 保留已有字段，并新增按视角、canonical 端位和 P 槽位的 `raw_detection`、`local_track`、`global_candidate`、`metric_eligible`、`roster_confirmed` 计数/覆盖率及最长缺口。当前所有逐人 `canonical_ticks=0` 的情形是映射未确认造成的门控，不能误报为检测为零。质量 verdict 分别报告感知覆盖失败、身份审计失败、2+2 端位失败、长时间无球员；已完成的处理 Job 仍可返回部分结果，但页面须明显标明“四人识别质量不足”。保留原始诊断以便追溯第一个断点。

### 5. tracklet 竞争按证据强度裁决，胜者唯一

同一 raw track / tracklet 同时被两个及以上冻结槽位的锚点命中时，SHALL 保留**证据最强**的一方作为该 tracklet 的槽位归属，落败槽位进入待裁决池并记录竞争证据（IoU、court 距离、时间差、落败原因），MUST NOT 因到达顺序先到先得。

证据强度按「court 距离 → bbox IoU → 时间差」依次比较，均由锚点匹配已有字段提供，不引入新打分模型。胜者确认后，落败槽位可继续用其余候选 tracklet 重新匹配；若无剩余候选，保持 `bootstrap_binding_tracklet_competes_for_slots` 失败而非降级为顺序补位。

选择此方式，因为 `job-faf852782a` 的 P4 在 IoU 0.8575 / 0.6614ft 上均优于任何替代匹配，却因 P3 先到而失去槽位；这属于裁决规则缺陷，不是证据不足。

### 6. 端位是可修订的观测结论，不是不可变约束

`roster_end` SHALL 允许在观测证据充分时被修订，而不是锚点时刻前一次性锁定。当前 `global_state.py:403` 的「端位不符即永久拒绝」SHALL 改为：端位冲突触发**重新裁决**——结合锚点证据强度与后续连续观测的端位一致性决定最终归属。

修订必须满足与身份唯一性同等的门槛：修订后同一 tick 仍 SHALL NOT 出现同端重复绑定，且修订过程逐人留痕（`roster_end` 变更原因、依据样本数、前后取值）。仅为通过锚点匹配而改写端位属于禁止行为。

选择此方式，因为 `global_player_2` 的 2561 个样本中 1709 个（66.6%）指向 end_b，而当前实现让锚点前的 852 个样本永久否决了后验的多数证据。

### 7. 身份审计单一权威源，冲突即失败

`bootstrap_binding_audit`（由 joint run 独立产出）为**唯一**权威来源。`roster.json` 的 `mapping_confirmed` 与 `frozen_roster.anchor_binding_audit` SHALL NOT 各自独立给出确认结论。

- `roster.json` 的 `mapping_confirmed` SHALL 改为引用审计结论，不得独立求值。
- `four_player_quality.py` 的 `mapping_confirmed_by_player` 与 `identity_slots` SHALL 读同一来源；两者不一致时以审计为准并使质量 verdict 为 fail。
- Rally/Shot 补写的 `bootstrap_binding_audit.json` 若与已存在的审计文件冲突，SHALL 使 Job 显式标记审计不可用，MUST NOT 静默覆盖或补全。
- 页面状态卡、覆盖率门槛、overlay 与热力图 SHALL 消费同一映射；任一处显示「未确认」时，其他各处 MUST NOT 呈现该 P 的个人图层或 Team 指标。

选择此方式，因为本 Job 已经出现热力图绘制 P4、状态卡同时声明 P4 未确认的自相矛盾，而根因是两个口径各自选择了对自己有利的事实。

### 8. 验收以新 Job 与证据对照完成

固定 `ct_9997fa5aedf7`、当前两路视频和冻结名册为真实回归输入。保存 `job-9a640b069a` 的 baseline 摘要，创建新的完整 `joint_tracking_v2` Job；比较检测/跟踪/绑定/展示漏斗，确认四个不同身份、Team A/B 各两人、P1/P2 在确认的 A 端、P3/P4 在 B 端、无重复/跨侧/未裁决换绑。沿用现有质量门槛：四人确认、每人 coverage ≥0.70、最长连续缺失 ≤2s、未裁决身份互换为 0。任一门槛未过，变更不得以“修复完成”验收。

## Risks / Trade-offs

- [前视锚点位于 289 秒，无法证明开场身份] → 只经连续 tracklet 与跨机位证据向前/后传播；无法连通的时段保留未确认状态。
- [端位配额可能误排越过中线或标定异常的球员] → 端位按初始队伍与可解释的跨侧事件判定，暂时不确定时隔离，并用逐帧诊断检查标定和 `rotate_180`。
- [更严格身份发布使现有页面显示更少 P 标签] → 同时展示匿名观测与逐人缺失状态，避免把未确认当作未检测；历史 Job 不重写。
- [真实全片回归耗时较长] → 先运行覆盖锚点、前段和长缺口的定向诊断，再跑一次完整新 Job，避免反复无依据重跑。

## Migration Plan

1. 增加兼容字段与只读审计消费；旧 Job 缺新字段时显示旧来源和 `unavailable`，不回填伪确认。
2. 在隔离的新 Job 上启用名册约束、端位容量和诊断，核对质量产物及 UI。
3. 真实全片验收达标后作为新任务默认行为；回滚仅切回旧算法配置，不改写用户冻结名册或历史产物。

## Open Questions

- 用户执行的 120 秒片段中，原始检测和 ROI 不是首断点。2026-10-03 复核已把首断点收敛到身份裁决层的三处语义缺陷（tracklet 竞争裁决方向、端位不可回退、审计双源真相），见上文「2026-09-28 诊断 Job 的首断点定位」。修复这三处后，开场 / 2:32 / 名册锚点 / 7:24 / 末段各窗口是否还会暴露新的独立断点，仍需一次修复后的真实 trace 确认。
- 在确认锚点之前存在多段 tracklet 时，可可靠向前传播身份的最远时刻是多少？该值由连续性证据决定，不能预设为全片。
- `global_player_2` 横跨两端（end_a 852 / end_b 1709）说明该 global 身份本身可能是两个真实球员被合并的产物。修复端位可回退后，需重新检查它是否应当被拆分为两个独立身份；若需要拆分，跨机位与短时漏检的区分判据尚待确定。
