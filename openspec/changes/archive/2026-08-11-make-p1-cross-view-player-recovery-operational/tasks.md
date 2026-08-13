## 1. Contracts and Configuration

- [x] 1.1 定义集中 `P1OnlineRecoveryConfig`，覆盖 binding aging、donor、ROI、pre-gate、association/reassociation 参数，并接入 joint input signature/manifest。
- [x] 1.2 将 `JointViewObservation` 收敛为 runtime 唯一 observation contract，加入 `(view_id, player_id, identity_epoch)`、track、quality、guided provenance 和 P1-0 timing fields。
- [x] 1.3 扩展 `ViewBinding` 为最后 view evidence（含 local identity epoch），实现可单测的 `registry.age_bindings(now_take_ms, ...)`，并在 epoch 变化时失效历史 continuity。

## 2. Per-View Runtime Foundation

- [x] 2.1 将 executor/runtime 的 FPS、frame size、homography/inverse homography、orientation 和 timing provider 改为 per-view context，移除 joint-wide reference geometry 依赖；P1 recovery target geometry 缺失时只允许 structured skip，禁止 reference-geometry fallback。
- [x] 2.2 为异分辨率/异标定双摄 fixture 增加 runtime 与 ROI 投影回归测试。
- [x] 2.3 保持 P1-0 authority、frame status 和 timing provenance 贯穿新的 per-view runtime context。

## 3. Session and Tracker Evidence

- [x] 3.1 为 `MultiObjectTracker` 实现 assignment-aware update，并确认既有 `update()` 调用的返回值和行为不变。
- [x] 3.2 为 `ViewTrackingSession` 实现 `legacy_union | lock_only` eligibility policy；joint runtime 选择 `lock_only`，单摄/late fusion 保持 legacy 行为。
- [x] 3.3 让 session 从 formal local player detection + matching projected position 输出 joint evidence，排除无 stable `player_id` 的 track。
- [x] 3.4 将 guided candidate evidence 通过 evidence-aware merge、tracker assignment、duplicate-track surviving filter、lock 和 local identity 贯穿到 joint observation；实现 base-over-guided precedence、overlapping guidance 的确定性决议，并修正 pre-gate 为 target local-space residual。
- [x] 3.5 覆盖 reject candidate 不触碰 tracker、每 source frame 一次 update、guided track 未获 lock 不进入 joint、base/guided same-target duplicate、overlapping guidance 及 rotate/mirror orientation 的测试。

## 4. Global State and Donor-Aware Guidance

- [x] 4.1 在 joint tick 的 prediction 前接入 per-tick binding aging，并在 diagnostics 中区分 target frame unavailable 与可用帧无 observation。
- [x] 4.2 扩展 `CrossViewGuidance` 为带 `guidance_id`、donor、expected global、expiry 的证据对象。
- [x] 4.3 实现双向 donor selection：仅允许 recent、高 intrinsic-quality、different-view 的 base evidence，且仅在 target frame available 时生成 guidance。
- [x] 4.4 使用 target 的 per-view geometry 生成 ROI，并实现 cooldown、max regions、donor stale/quality/uncertainty/availability 的结构化 skip diagnostics。
- [x] 4.5 实现 base-only cross-view anchor；保留 guided observation 的真实 measurement/fusion 资格但禁止其充当 donor 或建立 anchor。

## 5. Joint Tick and Association Hardening

- [x] 5.1 重构 `MultiViewJointRun` 为 `age -> predict -> all-view guidance snapshot -> all-view perception -> barrier -> associate/fuse`，确保 runtime 顺序不影响同 tick 输入。
- [x] 5.2 在 `GlobalPlayerAssociator` 中消费统一 observation contract，并在 canonical geometry hard gate 后应用 `(view_id, player_id, identity_epoch)` 与 expected-global ranking prior。
- [x] 5.3 使已有 mapping fallback 同样服从 hard geometry gate，并记录不可行 continuity rejection。
- [x] 5.4 限制 tentative bootstrap 每 global 每 tick 每 view 一份 observation，禁止同 view 近距离 formal players 合并。
- [x] 5.5 覆盖 identity continuity、hard-gate rejection、same-view bootstrap guard、base+guided 不增 anchor 与 single-view缺失不阻塞的测试。

## 6. Artifacts and Diagnostics

- [x] 6.1 additive 扩展 `fused_player_trajectory.v2` 的 view observation，写入 local identity、track、origin、guidance/donor、residual、quality 与 timing provenance，保持历史 reader 兼容。
- [x] 6.2 实现带 `recovery_episode_id` 的 recovery funnel diagnostics，冻结 `recovery_opportunity` / `guided_recovery_success` / `base_recovered` 语义、cooldown 消费时点、skip/reject reason counters、config snapshot 与 expected-global preservation 统计。
- [x] 6.3 更新 baseline `view-tracking-session` 契约测试，确认 non-empty guidance 在 joint mode 真实运行而默认/legacy 路径不变。

## 7. End-to-End Validation

- [x] 7.1 新增 Cam1 dropout、Cam2 base donor 的 controlled online recovery integration test，断言 target real-pixel recovery、provenance 和 gap 前/中/后 global ID preservation。
- [x] 7.2 新增完全反向的 Cam2 dropout、Cam1 base donor controlled recovery test。
- [x] 7.3 新增负例：两路都 lost、donor 仅 guided、pre-tick target observed、target frame unavailable、available 但 decode 失败、target geometry unavailable、错误 ROI 人物、lock reject、guided/base anchor、local identity epoch reset、base/guided same-tick duplicate 与两条 guidance 命中同一 candidate。
- [x] 7.4 运行相关 backend 测试、P1-0 timing authority/eligibility 回归、single-view 与 late_fusion_v1 differential regression，并执行严格 OpenSpec 校验。
