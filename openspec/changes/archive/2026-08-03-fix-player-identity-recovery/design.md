## Context

当前球员身份链路由 `MultiObjectTracker`、`PlayerLockManager`、`PlayerIdentityManager` 和视频 overlay 播放解析组成。归档的硬锁变更已经统一了 `Player_1`..`Player_4` 命名，并禁止 LOST 槽位回退或被其他候选占用，但真实视频仍暴露出恢复链路不完整：

- `PlayerLockManager` 逐个处理 LOST 槽位，未在同一帧预留已被其他槽位认领的 track，因此两个槽位可能绑定同一个新 track。
- bootstrap 主要写入 `assignment_side`，没有可靠填充 `side_hint`，重连评分无法使用初始象限信息。
- 短暂漏检产生新 track 时，候选必须先进入 `eligible_track_ids` 才能到达身份层；锁定层未及时给 hint、selector 又未建议该 track 时，检测框没有 `player_id`，前端显示 `person`。
- `resolveDetectionFrame()` 在相邻 overlay 帧之间只插值 bbox 和 confidence，当前帧为空身份时不会继承同一 track 的下一帧 canonical 身份。

本 change 是跨后端状态机、身份分配、overlay 播放和真实视频验证的联合修复。测试视频位于 `/Users/tuian/Downloads/测试视频25s.mp4`，只作为本机回归输入，不进入仓库。

## Goals / Non-Goals

**Goals:**

- 保证同一分析任务内每个锁定槽位最多绑定一个当前 track；一个 track 在同一帧最多属于一个 P 槽位。
- 在短暂漏检或 tracker 换 ID 后，尽早将合格的新 track 绑定回原 `Player_1`..`Player_4`，而不是长期退化为 `person`。
- 让 bootstrap 的 P1-P4 象限元数据参与重连评分，同时不把 side/quadrant 当作不可变的球员身份。
- 保持身份层不创建第 5 个球员身份，保持 lock hint 优先于 soft takeover。
- 增加可重复的单元、overlay 解析和真实视频回归证据，并明确旧任务 artifact 不会因刷新而重新计算。

**Non-Goals:**

- 不实现跨比赛或跨任务的长期 ReID。
- 不引入外观 embedding 模型或新的第三方跟踪器。
- 不改变球检测、姿态估计、球场标定和计分逻辑。
- 不修改历史分析任务的 artifact；验证必须创建新分析任务。
- 不把测试视频复制到仓库或提交到版本控制。

## Decisions

### 1. Lock manager 负责同帧一对一恢复分配

保留 `PlayerLockManager` 作为 canonical identity 的唯一权威。每次 `update()` 先识别仍匹配原 `current_track_id` 的 LOCKED 槽位，再对没有匹配的 LOCKED/LOST 槽位和未占用的当前观测构建重连候选。候选分配必须同时满足：

- 一个 track 只能被一个 slot 预留；
- 一个 slot 每帧最多接受一个 track；
- 已被正常 LOCKED 槽位消费的 track 不进入重连候选；
- 重连分配后输出唯一的 `track_identity_hints`，并把候选加入 `eligible_track_ids`。

候选按 reconnect score 降序进行确定性的一对一分配，分数相同按 slot identity 和 track_id 稳定排序。这样不引入 Hungarian 等新依赖，但可以消除当前重复认领问题。重连仍然是“绑定回原 slot”，不是把已锁定身份替换给其他 slot。

### 2. 短暂漏检使用同槽位恢复窗口

在 LOCKED 槽位暂时找不到旧 track 时，lock manager 在进入持久 LOST 前尝试对未占用的新 track 做同槽位恢复；命中后保持该 slot 的 canonical identity，更新当前 track 和 hint。若没有合格候选，继续使用 `lost_grace_frames` 进入 LOST；LOST 仍然保持硬锁到底。

这样短暂换 ID 不必等待槽位先进入 LOST 才能恢复身份，同时不会允许候选填入别的 P 槽位。身份层的 soft takeover 继续保留为没有 lock hint 时的有限兜底，但不会取代 lock manager 的重连判定。

### 3. 保存 bootstrap 象限元数据并区分 home 与当前 side

bootstrap 将候选的推断象限写入 slot 的 `side_hint`，至少覆盖 `near_left`、`near_right`、`far_left`、`far_right`（单打为 near/far）。`assignment_side` 继续表示当前 quota 占用语义；`side_hint` 用于重连辅助，不作为永久 player identity，也不阻止球员在比赛中换位。

如果实现需要记录不可变的初始象限，则新增内部 `home_quadrant` 字段；对外仍只暴露 canonical player ID，且不得用象限重新编号。

### 4. 统一恢复候选的 eligibility 和身份样本

lock manager 产生的 pending/reconnect track 必须进入 `PlayerLockUpdate.eligible_track_ids`，并在同一帧通过 `track_identity_hints` 交给 `PlayerIdentityManager`。身份层按以下顺序处理：

1. lock hint；
2. 已有 `track_to_player` 映射；
3. 合格且距离受限的 soft takeover；
4. `unmatched` 诊断。

只有步骤 1-3 成功才为 overlay 构建 `player_by_track`。soft takeover 样本继续标记为 `tentative`，但仍显示 canonical P ID；没有身份的框才显示 `person`。

### 5. Overlay 插值只继承可证明的身份

`resolveDetectionFrame()` 对相邻帧中相同 `track_id` 的 detection，在使用下一帧 bbox/confidence 插值时同步继承下一帧的 canonical `player_id` 和 label（当当前帧为空且下一帧已有身份）。不根据空间距离在前端猜测不同 track 的身份；不同 track 的恢复必须来自后端 lock/identity artifact。

### 6. 真实视频回归保留基线并创建新任务

回归流程使用 `/Users/tuian/Downloads/测试视频25s.mp4`，通过现有视频上传/注册流程得到可分析的 video ID，再用相同标定、source FPS 和 frame stride 创建新 analysis job。旧 job 不删除、不覆盖，作为 baseline。

回归记录至少包括：新旧 job ID、视频与参数、每个 P 槽位的 track history、P ID 数量、同帧重复绑定数、重连诊断数量、overlay 中 `person` 连续区间、trajectory 覆盖度以及人工抽查的恢复时间点。

## Risks / Trade-offs

- [位置相近的两名球员交叉时可能产生错误重连] → 同帧一对一分配、side/quadrant 辅助评分和诊断记录限制错误扩散；不引入未经验证的外观 ReID。
- [过早恢复可能把短暂误检绑定到 P 槽位] → 仅对 target-court 合格观测使用恢复门控，并保留 score 阈值、confidence 阈值和 `tentative` 状态。
- [前端身份继承可能短暂显示上一身份] → 只对相同 `track_id` 且下一帧已有 canonical ID 时继承；track 变化场景由后端 hint 决定。
- [25 秒视频可能不足以覆盖所有真实遮挡模式] → 同时保留合成状态机测试、overlay 解析测试和真实视频 artifact 证据；把未覆盖情形记录为 residual risk。
- [外部下载路径在其他机器不存在] → 不把路径写入运行时代码；测试任务以本机回归记录为证据，自动化测试使用合成 fixture。

## Migration Plan

1. 先实现 lock manager 的同帧一对一恢复、side_hint 填充和对应后端单测。
2. 再接通短暂恢复候选到 identity manager/pipeline，补充换 track、无 hint、soft takeover 和 overlay label 测试。
3. 更新前端检测帧解析，使同 track 的下一帧 canonical identity 可继承。
4. 运行后端与前端定向测试，再使用指定视频创建全新分析任务。
5. 对比新旧 artifact，确认 P1-P4 稳定性后再考虑归档本 change；失败时只回滚新代码，不删除旧分析任务。

## Open Questions

- 真实视频是否包含完整四名场上球员，还是需要按实际可识别人数验收 `effective_player_count`？
- 短暂漏检恢复窗口是否沿用现有 `lost_grace_frames`，还是需要单独增加可配置的 `recovery_candidate_frames`？
- 真实视频回归结果是保存为仓库内 markdown 证据，还是只保留任务 artifact 路径和任务 ID？
