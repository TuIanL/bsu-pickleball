## Context

匹克球动作数据集（`pickleball-action-dataset`）已发展到 v3.0.0，拥有 1084 条结构化标注、ffprobe 元数据、141 组来源分组、4 类基线（968 条）和全 9 类（1084 条）数据划分。当前缺失的是从「人工标注产物」到「机器学习可消费输入」之间的正式发布契约。

现有约束：
- `actions.v3.json` 是人工标注权威真值，不可修改
- v3 标签体系为多维结构（`stroke_type` × `stroke_side` × `hand_usage`），但 `forehand_drive`/`backhand_drive` 已将侧别融合进 `stroke_type`，存在不完全一致性
- `video_meta` 仅基于 ffprobe 提取，未验证实际解码能力
- 去重仅基于文件名归一化（`migrate_v2_to_v3.py`），未做内容级检测
- 视频文件存于外置硬盘，不在 Git 仓库中
- 已有 `baseline4` 和 `full9` splits，按 `source_video_id` 分组防泄漏

## Goals / Non-Goals

**Goals:**
- 定义 ML 标签 Profile，建立 v3 源标注到不同训练任务标签的确定性映射
- 生成可重复、哈希稳定的 `canonical_actions.jsonl`
- 对所有训练视频执行完整解码验证
- 执行 SHA-256 + 感知哈希 + 帧级复核三层内容去重
- 验证现有 splits 无跨集泄漏，必要时生成版本化替代 split
- 生成完整数量核算审计报告
- 生成不可变 `releases/v3.1.0/` 发布包（含 checksums）

**Non-Goals:**
- 不修改 `actions.v3.json` 源标注
- 不将 v3 多维标签改为 flat 标签
- 不人工复核全部 227 条 unknown side 样本
- 不根据 `hand_usage=two_hand` 推断 `stroke_side`
- 不重新实现已有 review_tool、ffprobe、split 机制
- 不训练 ST-GCN 或提取 RTMPose 骨架
- 不接入 FastAPI 或修改前端
- 不新建独立 ML 仓库

## Decisions

### 决策 1：两仓职责分离

**选择**：数据集工具代码放在 `pickleball-action-dataset/src/pb_action_dataset/`，训练代码以后放在 `pre-pickleball/ml/`。

**理由**：
- 数据验证、去重、审计和发布是数据集自身的能力，属于数据工程范畴
- 训练代码（ST-GCN、数据加载器、训练循环）是模型工程范畴
- 训练代码只消费 `releases/v3.1.0/` 不可变发布包，不直接读取数据集工作文件
- 避免 `pre-pickleball` 产品仓库引入数据工程依赖（ffmpeg、大型视频文件）

**替代方案**：
- 全放 `pre-pickleball/ml/`：会使产品仓库膨胀，引入不必要的数据工程依赖
- 新建独立 `pickleball-ml` 仓库：当前团队规模不需要第三个仓库的版本联动成本

### 决策 2：保留 v3 多维标签 + 派生 ML 视图

**选择**：源标注保留 `stroke_type`/`stroke_side`/`hand_usage` 三维结构，通过 `model_label_profiles.yaml` 定义从源标签到不同训练任务标签的确定性派生规则。

**理由**：
- `forehand_drive`/`backhand_drive` 已将侧别融合进 `stroke_type`，需要统一为 `action_family: drive` + `stroke_side: forehand/backhand`
- `dink`/`volley` 的侧别在 `stroke_side` 字段中，不在 `stroke_type` 中
- 多任务学习（action family + stroke side + hand usage）需要三个独立监督信号
- 保留源标签确保映射规则有误时可以回溯修正

**派生规则**（在 `canonicalize.py` 中实现）：

| v3 stroke_type | v3 stroke_side | action_family | stroke_side |
|---|---|---|---|
| forehand_drive | forehand | drive | forehand |
| backhand_drive | backhand | drive | backhand |
| dink | forehand | dink | forehand |
| dink | backhand | dink | backhand |
| dink | unknown | dink | unknown |
| volley | forehand | volley | forehand |
| volley | backhand | volley | backhand |
| volley | unknown | volley | unknown |
| drop_shot | * | drop_shot | *（保持原值） |
| smash | * | smash | * |
| lob | * | lob | * |
| serve | * | serve | * |
| other | * | other | * |

### 决策 3：任务级 Eligibility 代替全局 Accepted/Rejected

**选择**：不维护三份独立 JSONL（accepted/review/rejected），每条样本在 `canonical_actions.jsonl` 中携带 `eligibility` 字段，按训练任务声明是否可用。

**样例**：
```json
{
  "eligibility": {
    "legacy_baseline4": "eligible",
    "legacy_full9": "eligible",
    "action_family8": "eligible",
    "stroke_side_head": "masked",
    "hand_usage_head": "eligible"
  }
}
```

**理由**：
- 227 条 unknown side 不能监督正反手，但完全可以训练动作类型
- 避免维护三份文件导致的数据不一致
- 训练代码读取时按 head 掩码 loss，不丢弃样本

### 决策 4：三层内容去重

**选择**：
1. 第一层：文件 SHA-256 哈希（识别完全相同的文件）
2. 第二层：在 10%/30%/50%/70%/90% 位置采样帧，对每帧计算感知哈希（pHash），生成帧序列哈希向量，比较向量相似度（识别转码/轻微裁切/分辨率变化的副本）
3. 第三层：对第二层识别出的候选组，抽取对应位置帧做 SSIM 复核

**输出分类**：
- `exact_duplicate`：SHA-256 完全一致 → 只保留一个训练主样本
- `probable_reencoded_duplicate`：感知哈希高度相似 + SSIM > 0.95 → 必须进入同一 split
- `related_clip_same_source`：同一 `source_video_id` 的不同裁剪 → 依靠 source_video_id 防泄漏
- `not_duplicate`：正常保留

**理由**：
- 单纯 SHA-256 漏掉转码副本（如 `_from_mov` 版本）
- 单帧 pHash 在相同球场背景下假阳性过高（大量视频背景几乎相同）
- 帧序列相似度比较可区分「同一动作的转码版」和「同一球场背景的不同动作」

### 决策 5：完整解码验证，不只 ffprobe

**选择**：对每个训练视频执行 `ffmpeg -v error -i input.mp4 -f null -` 完整解码，并核对实际解码帧数与 `video_meta.num_frames`。

**解码状态分类**：
- `passed`：完整解码成功，帧数匹配
- `decode_error`：ffmpeg 报告解码错误
- `truncated_stream`：解码帧数 < num_frames（设 ±2 帧容差）
- `frame_count_mismatch`：解码帧数 ≠ num_frames（超出容差）
- `duration_mismatch`：实际时长与 `duration_ms` 偏差 > 5%
- `missing_file`：视频文件不存在

**理由**：
- ffprobe 只读容器元数据，不验证实际编码流
- 动作 clip 仅 1-3 秒，完整解码成本极低（约 0.1 秒/文件）
- 损坏的视频进入训练会导致静默的数据错误

### 决策 6：Split 校验优先于重建

**选择**：先对现有 `baseline4` 和 `full9` splits 进行完整性校验，仅在发现泄漏时生成版本化替代 split。

**校验项**：
- 同一 `source_video_id` 不得跨 train/val/test
- `exact_duplicate` 和 `probable_reencoded_duplicate` 组不得跨 split
- skipped 样本（12 条）不得出现在任何 split 中
- split 中的 `sample_id` 必须存在于 `actions.v3.json`
- 同一 `sample_id` 不得同时出现在两个集合中
- 各 split 样本数为整数且之和等于类别总样本数

**替代方案**：
- 直接重建 split：会破坏已有实验的可复现性，且现有 split 可能本来就是正确的

## Risks / Trade-offs

**[风险] 感知哈希假阳性**：相同球场背景下不同动作的帧可能产生相似 pHash → **缓解**：使用帧序列（5 帧）而非单帧比较，且第二层阈值设得较高（Hamming distance < 阈值 × 帧数），第三层 SSIM 作为最终裁决。

**[风险] 视频文件不在 Git 中**：`videos/` 目录为空，解码验证和内容去重需要访问外置硬盘上的实际文件 → **缓解**：脚本接受 `--video-root` 参数指向实际视频存储路径；在 CI 中 skip 视频依赖的测试。

**[风险] 227 条 unknown side 被丢弃**：如果下游训练代码不理解 `eligibility` 掩码机制，可能错误地将 unknown side 样本排除在所有训练之外 → **缓解**：在 `canonical_actions.jsonl` 的文档和 Schema 中明确 `masked` 语义；`views/side_masked_ids.txt` 提供快捷筛选列表。

**[权衡] drop_shot 不重命名为 drop**：保持 `drop_shot` 名称，与 v3 一致，但和学术界常见的 `drop` 命名有差异 → **理由**：重命名需要同步修改所有 splits、统计和已有实验记录，收益不足以覆盖迁移成本。

## Open Questions

_无。所有关键决策已在探索阶段确定。_
