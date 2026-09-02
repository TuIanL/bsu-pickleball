## Context

当前 CaptureTake 已保存单摄/双摄视频、同步资产、Vidat/人工时间线、`rally` 片段和 `non_play` 事件；现有分析还可以产出球员检测、RTMPose 骨架、球检测和球路 artifact。人工标定适合提供回合的大致范围，但存在提前或滞后数秒的问题，不能未经处理地作为逐帧标签。

本变更首先面向离线实验：从 7-20 视频建立可复现数据集，比较原始 RGB、骨架/球路和多模态视觉输入，最后生成可人工复核的候选状态时间线。生产分析的默认语义时间线和人工权威边界不被直接替换。

## Goals / Non-Goals

**Goals:**

- 以源视频和人工粗标注为入口，生成包含 provenance、双摄关系、时间基准和质量诊断的数据集。
- 将人工起止误差表示为高可信区间、边界不确定区间和排除区间，避免错误硬标签污染训练。
- 支持 RGB-only、视觉中间表征和多模态融合实验，并按整场比赛隔离 train/validation/test。
- 输出逐时间窗状态概率、候选边界、置信度、模型版本和评估指标。
- 让人工复核结果可以回流为下一轮训练数据，支持逐步提高边界精度。

**Non-Goals:**

- 第一阶段不从零训练大型端到端视频模型。
- 第一阶段不把当前语义时间线或评分结果作为模型真值，也不让模型直接修改人工权威事件。
- 第一阶段不承诺跨场地、跨摄像机型号或实时低延迟泛化。
- 不改变现有球员、球路、评分和普通视频分析链路的默认行为。

## Decisions

### 1. 将问题建模为时序状态分段，而不是单帧二分类

模型以固定时间窗处理连续画面，输出 `pre_serve`、`rally_active`、`post_rally`、`timeout_or_side_change`、`unknown` 等状态概率；产品层再映射为比赛/非比赛。这样可以利用前后文，减少发球准备、捡球和回合结束瞬间的混淆。

备选方案是逐帧二分类，优点是实现简单，但容易在相邻帧间抖动，也无法表达边界不确定性，因此不作为主方案。

### 2. 使用源视频直接产生视觉输入，现有语义结果只作为审计参照

数据集生成器直接读取源视频和人工粗标注。RGB clip、骨架关键点、球检测/轨迹、光流或运动区域均视为视觉输入；不得把 `rally_active`、`non_play`、比分或现有语义裁决作为模型特征。骨架和球路输入同时保存置信度、可见性和缺失 mask，使模型能够学习处理视觉提取失败。

备选方案是只消费现有分析 artifact，成本低但会继承上游误差，无法验证模型是否真正理解画面，因此只用于对照实验。

### 3. 对人工时间线采用三段式弱监督

对每个粗标回合内部和外部生成高可信正/负样本；起止点附近按测得误差设置 `uncertain` 缓冲区，不参与硬分类损失和边界评分。若样本过短、缺少闭合边界或多种标注冲突，则标记为 `excluded` 或仅用于 clip-level 弱监督。

第一批数据先抽样精确复核边界，使用实际误差分布确定缓冲区，而不是预先假定固定秒数。

### 4. 双摄采用时间对齐后的晚融合

以 CaptureTake 的权威时间和同步锚点对齐两个机位。每个机位先独立编码 RGB/视觉特征，再在时序层融合；输入中包含机位 ID、每个模态的质量和缺失 mask。训练时使用 view dropout，使单个机位质量下降时仍能降级运行。

备选方案是直接拼接两路图像或把两路图像当作通道，不能充分处理角度差异，也会显著增加显存和数据量。

### 5. 先做可解释的实验矩阵，再决定正式模型

至少比较三组：RGB-only、骨架+球路、RGB+骨架+球路。数据量有限时使用预训练视觉 backbone 并冻结大部分参数，时序头优先采用 TCN/GRU 或小型 Transformer。所有实验共享相同数据切分和评估脚本，报告每个机位、比赛和状态类别的结果。

### 6. 模型输出先进入候选 artifact 和人工复核

推理结果保存状态概率、平滑后的状态、候选起止边界、边界误差估计、输入覆盖率、模型包版本和阈值。第一阶段只作为 Shadow/候选时间线展示；只有人工确认后的边界才可进入正式时间线。连续状态使用最短持续时间、迟滞和 `unknown` 降级，避免逐帧抖动或强行二选一。

### 7. 模型包必须包含权重以外的运行契约

模型发布包至少包含模型权重、标签映射、采样 FPS、clip 长度、特征 schema、归一化参数、阈值、训练数据版本、代码/配置版本和评估报告。模型缺失或输入质量不足时，系统返回 unavailable/insufficient_evidence，不阻塞已有分析。

### 8. 人工边界复核复用片段管理工作台

有效回合边界直接复用现有 CaptureSegment、双摄视频播放、逐帧控制和可拖动时间线。工作台增加 `pending/confirmed/corrected/excluded` 复核队列；原始 `start_ms/end_ms` 不覆盖，修正值继续写入 `corrected_start_ms/corrected_end_ms`，复核决定写入现有 `segment_edit_operations` 审计表。这样评分校准、Vidat 版本管理和比赛状态训练数据仍各自保持清晰职责，不新增一次性标注工作台。

工作台同时支持补录漏记的 rally。用户通过共享播放头设置新增回合的完整起止边界后，系统创建一条 `active/closed/manual` 的 CaptureSegment，初始复核状态为 `pending`，并写入创建操作审计；如果新增回合位于已有回合之间，按 take 时间顺序调整后续回合 ordinal，保留受影响 ID 和序号变更记录。新增回合不得与现有 active rally 发生时间重叠，避免把标注重复误当成漏记。

由于单个录像对应一局比赛，工作台也支持修正 rally ordinal：用户可以从当前选中的 rally 输入真实分序号并让后续 active rally 按时间连续编号，也可以将整段视频按时间从第 1 分统一编号。该操作只修改 ordinal 和系统默认的“第 N 分”标签，不覆盖人工自定义标签、不修改任何起止边界，并将每条序号变化写入编辑审计。

工作台对边界倒置、结束点缺失或其他非法边界保留可选中的异常态。异常回合使用安全播放上下文，允许先把一端写入本地草稿，再定位另一端；只有两端重新形成合法时长后才提交边界复核结果。

双摄复核时两个视频实例共享页面级播放控制器和同一个 take 时间基准。任意视角发出的播放/暂停、拖动或逐帧请求都由控制器同时作用于两个视角；播放过程中以主视角时钟持续校正另一视角，边界按钮只读取这个共享播放头，避免用户在两个画面之间分别操作后产生边界偏差。

### 9. 第一阶段先学习有效回合/非比赛，视觉模态按消融顺序递增

7 场视频已逐回合人工复核，因此第一阶段将每个 take 的完整时间轴二分为 `rally_active` 与 `non_play`；发球前准备、回合后反应、捡球、交谈、等待、换边和暂停均作为有意义的非比赛负样本保留。`pre_serve`、`post_rally` 和 `timeout_or_side_change` 暂不作为硬标签，因为当前人工复核只确认了有效回合边界；后续需增加子状态标注或可复核的弱标签规则。

训练输入按共享切分依次比较：双摄 RGB-only；四人 RTMPose 与球场归一化位置；骨架加球检测/球路；RGB 与结构化视觉特征晚融合。RTMPose 和球检测必须携带置信度、可见性、插值标记和 missing mask，“未检测到球”不得直接解释为“场上无球”。球场线、网和边界通过每个机位的场地标定/单应性转换为静态几何元数据，用于归一化球员与球的位置、速度和出界关系，不作为强制决定比赛结束的规则。

人工逐帧复核后的边界只保留 ±250ms 转换不确定区；统计得到的旧标注 P90 误差（开始 1.4s、结束 2.363s）仅用于未来混入未复核旧标注时的降级缓冲，分别向上取整为 1.5s 和 2.5s。当前 7 场训练数据全部使用复核后边界，不再套用大缓冲。

### 10. 本地只生成元数据和任务包，所有重计算在远程服务器执行

RGB clip manifest 是 metadata-only 清单，不在本地解码视频或物化大量 clip 文件。本地仅执行数据审计、人工复核、标签快照、manifest 生成与校验、远程任务打包；视频解码/索引、RGB 抽帧与特征提取、RTMPose、球检测/跟踪、场地坐标投影、训练、评估和批量推理均标记为 remote-required。

媒体以 `matchstate://2026-07-20/{source_session_id}/{camera_role}` 作为跨机器稳定身份，本机 `/Volumes/Elements/...` 绝对路径只保留为 provenance。远程任务通过 `MATCH_STATE_DATASET_ROOT` 和 `remote_relative_path` 解析媒体，任务包不得包含凭据。14 个源视频上传一次后，RGB、骨架和球路特征按数据清单、提取器版本、采样 FPS 与预处理配置哈希缓存，后续消融实验命中相同 cache key 时不得重复计算。

效果优先的第一版 RGB manifest 使用 4 秒上下文、0.5 秒滑动步长、每机位 12 FPS（目标 48 帧），并在窗口内部每 250ms 写入 `rally_active/non_play/uncertain/padding` 标签和 loss mask。manifest 保留靠近视频首尾的窗口并显式记录 padding；它只引用逻辑媒体 URI，不在本地解码或裁切视频。两个机位均保留当前 take-time mapping 和 `pending_validation` 同步状态，必须在任务 2.4 验证后才能用于正式双摄训练。

数据切分以完整 `capture_take_id` 为唯一分组单位。主实验使用固定 5/1/1 的 train/validation/test，按总时长、回合数和状态比例选择平衡组合；所有模型与消融共享该切分。由于仅有 7 场，最终候选架构还需报告 7 折 leave-one-take-out 结果，避免一次单场测试的偶然性。切分以 overlay manifest 关联 RGB 清单，不改写或复制 clip；同一双摄逻辑媒体 URI 不得跨集合。

远端同步门禁同时使用 PTS 网格和内容级运动证据：7 场 cam_1/cam_2 的 60 FPS sidecar 在帧数、首尾 PTS 和 SHA-256 上逐场完全一致；8 FPS 低分辨率运动相关诊断估计的 cam_2 残余 offset 均为 -125ms、0 或 +125ms，低于 250ms 门槛。报告以 `match_state_dual_sync_report.v1` 保存并纳入训练 provenance；RGB manifest 本身保持不可变，由训练门禁引用该通过报告解除 `pending_validation`。

结构化视觉缓存使用 `match_state_structured_feature_profile.v1`：每机位按源视频 PTS 以 12 FPS 单次顺序解码，YOLO11x 提取最多四名场上球员，RTMPose-m Body7/Halpe26 的官方 ONNX 模型经 RTMLib/ONNX Runtime CUDA 输出 26 点骨架，专用 pickleball YOLO 保留全部球候选，场线分割每 60 秒采样一次静态几何。逐帧记录检测置信度、关键点可见性、球缺失语义和 `structured_loss_mask`；球缺失固定解释为 `unknown_not_no_ball`。当前数据没有经过验证的每机位单应性，因此第一版缓存保留归一化图像坐标和场线多边形，并显式将 `court_projection_available=false`，不得伪造球场坐标。

#### Canonical-sync v2 对齐准备

后续机器学习的双摄时间真相源固定复用既有的 `FrameTimingProvider`、`dual_camera_sync` 和 `CanonicalAnalysisClock` 契约，不在本变更中另写一套 offset/rate 公式。远程离线 runner 使用与后端相同版本的同步核心快照，仅增加一个 feature-cache adapter：以 cam_1 的 source PTS 为 canonical tick，调用既有 `map_reference_time`/`build_frame_map` 选择 cam_2 的真实源帧，再从已经完成的结构化缓存中取该源帧对应的骨架、球候选和场地线。

同步资产 manifest 必须显式声明 `camera_role -> camera_id`（本批数据为 `cam_1 -> 174`、`cam_2 -> 175`，来源为 session metadata），并绑定每场的 14 个 source-PTS sidecar、`sync_calibration.json`、锚点文件、文件 SHA-256 和 `sync_revision`。缺少 PTS 或校准时不得静默退回零偏移；最多生成单视角/兼容模式记录并标记 `timing_authority=missing` 或 `legacy_nominal_fps`。

v2 对齐层不覆盖旧的 `cache/aligned-features-v1`。每个 canonical tick 和每个视角同时记录：`canonical_timestamp_ms`、`source_frame_index`、`source_pts_ms`、`mapped_target_pts_ms`、`alignment_error_ms`、`timing_authority`、`sync_quality`、`sync_revision` 和 `missing_mask`。锚点有效区间内标记 `authoritative`；有效区间外但 affine 映射仍落在媒体范围内标记 `extrapolated`，不得计入 authoritative joint eligibility；超出媒体范围或选择误差超限标记 `unavailable`。

结构化派生速度/加速度使用 canonical 时间差计算，而不是 cam_2 的未映射本地时间。RGB JPEG 缓存因生成时已规整为 12 FPS，只能将规则输出帧绑定到映射后的媒体时间，并额外记录 RGB 输出量化误差；它不宣称 JPEG 本身带有原始 source PTS。现有 RGB-only v1 保留为 nominal-sync baseline，v2 需要更新 loader 后再单独训练和评估。

本轮准备阶段已实际完成并封口：7 场共 53,142 条 12 FPS canonical 记录，34,768 条 joint authoritative、18,370 条 extrapolated、4 条尾部 unavailable；全量 verifier 通过，source selection 最大误差 8.333ms、feature selection 最大误差 50.0ms。旧 v1 cache 与 RGB baseline 保持原样，v2 仅作为新的可回滚输入层。

远端 RTX 2080 Ti 冒烟门禁已通过：真实回合时段双机位各 24 帧均识别四人并输出 4×26 关键点，短片段轨迹 ID 稳定为 1–4，双摄采样时间差约 15–22ms；球候选置信度中位数约 0.52/0.56。全量结构化提取以版本化模型/配置 SHA-256 作为缓存身份后台执行，完成前任务 2.3 保持未勾选，且不得启动训练。

首次全量任务在 RTX 2080 Ti 上中断于第一个机位，只产生未封口的 `frames.jsonl.partial`/`court-line.jsonl.partial`，没有任何 `summary.json: status=complete` 缓存，因此不能作为可复用特征。迁移至 RTX 4090 后，14 个媒体文件共 4,751,770,876 字节均与 immutable manifest 的逐文件尺寸一致；提取脚本、配置及 YOLO11x、pickleball ball、court-line、RTMPose ONNX 权重 SHA-256 均与首次运行一致。旧 partial 被保留到 `cache/interrupted-2080ti-structured-v1`，新任务在标准 `cache/structured-v1` 中完成了 14/14 个机位的原子缓存；最终共 106,296 条 12 FPS 结构化帧记录、106,269 条 pose usable 记录、94,223 条 ball observed 记录和 153 条场线记录，所有 JSONL 均可解析且计数与 summary 一致。最后一个机位从 418 条 partial 记录安全续跑完成，未启动训练。

训练阶段先固定 `match_state_training_profile.v1` 和 `match_state_model_package.v1`。本地 `scripts/match_state_experiment.py` 只提供 metadata 校验和远程任务打包，不解码视频、不做本地训练；它在训练前强制校验数据/标签/结构化特征 schema、RGB 清单哈希、7/7 双摄同步通过、按 `capture_take_id` 的无泄漏切分和三组实验矩阵。当前已生成 `match-state-training-job-2026-07-20.v1`，job id 为 `msj_6dde8bf78e635b3864ca`；训练配置固定随机种子 20260720、4 秒窗口、12 FPS/48 帧、uncertain 区间 mask 和远程 CUDA 执行策略。模型包要求权重、训练配置、评估报告及完整数据/代码 provenance，模型不可用时保留现有分析流程。

RGB-only baseline 已在 RTX 4090 上完成完整训练。训练使用双摄共享 R3D-18 预训练编码器和晚融合，前 3 个 epoch 冻结视觉骨干，第 4 个 epoch 起解冻，并在验证集连续 7 个 epoch 不再提升后自然 early stopping；最佳 checkpoint 为第 15 个 epoch。固定切分包含 train/validation/test=5925/1321/1108 个 high-confidence 窗口；验证集最佳 macro-F1=0.9799，测试集 accuracy=0.9711、macro-F1=0.9651。测试集 `rally_active` precision=0.9840、recall=0.9194、F1=0.9506，`non_play` precision=0.9660、recall=0.9935、F1=0.9796，混淆矩阵为 `[[308,27],[5,768]]`。模型、测试报告和 provenance 已写入版本化运行目录。该结果说明纯 RGB 双摄输入已经能作为第一版基线，但由于当前只有 7 场且测试按整场分组，后续仍需用骨架/球路、融合和 leave-one-take-out 实验验证跨场次稳定性；不直接替换人工候选时间线。

## Risks / Trade-offs

- [人工标签整体偏移] → 先做边界抽样复核，使用不确定缓冲区和弱监督；不要把粗标注逐帧硬化。
- [模型学习场地背景而非比赛状态] → 按整场比赛切分，使用不同球员留出测试、颜色/裁剪增强，并报告跨日期泛化结果。
- [骨架或球检测漏检] → 保留 RGB 分支、置信度和 missing mask，并做 RGB-only 与融合消融。
- [双摄时间未完全对齐] → 使用既有同步锚点和 PTS provenance，记录残余偏差；对齐失败的样本不得静默训练。
- [球员身份交换] → 不把稳定的 Player ID 当作必要输入，使用球场区域/集合编码或排列不敏感的聚合方式。
- [状态边界定义不一致] → 在标签 profile 中明确 `pre_serve` 是否属于比赛时间，并将未知/暂停等状态单独建类。
- [训练集规模不足] → 第一阶段冻结预训练 backbone，只训练轻量时序头；模型仅作为候选，不直接接管生产语义。

## Migration Plan

1. 只读盘点 7-20 视频、双摄关系和现有标注，生成审计报告。
2. 抽样精确复核边界，锁定第一版标签 profile 和不确定缓冲区。
3. 生成不可变实验数据集，先离线运行三组输入消融实验。
4. 在按比赛隔离的测试集上评估；达不到门槛时保留人工流程，不启用自动覆盖。
5. 达标后将预测以候选时间线接入复核页面；回流人工修正结果生成下一版数据集。

回滚方式是关闭学习模型候选输出并继续使用当前人工/现有语义流程；模型 artifact 和数据集版本均不可覆盖，便于复现和比较。

## Open Questions

- 可接受的自动边界误差是 ±0.5 秒、±1 秒还是其他值？
- 第一阶段主要目标是录制后离线分析，还是需要同步支持录制中的实时识别？

已确认：`rally_active` 只指有效回合，不包含发球前准备；7-20 数据使用外接盘正常双摄对局，排除三个短测试 session 和媒体不可用录制，暂不使用输赢/比分标签。
