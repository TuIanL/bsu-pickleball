## Why

匹克球动作数据集（`pickleball-action-dataset`）已演进至 v3.0.0，包含 1084 条结构化标注、ffprobe 元数据、141 组来源分组、4 类基线和全 9 类数据划分。但当前缺少机器学习消费所需的三项关键保障：(1) 缺少从 v3 多维标签到模型训练标签的确定性映射与可重复派生机制；(2) 缺少视频内容的逐文件解码验证——现有 `video_meta` 仅基于 ffprobe 元数据，不能证明每个视频均可完整解码；(3) 缺少基于视频内容（SHA-256 + 感知哈希）的重复检测，当前去重仅依赖文件名归一化，存在训练/测试集跨集泄漏风险。

现在启动机器学习训练之前，必须先完成这层质量加固与发布契约，否则训练结果的可靠性无法保证。

## What Changes

- 新增 ML 标签 Profile 定义（`model_label_profiles.yaml`），建立 v3 源标注到不同训练任务标签视图的确定性映射规则，支持 `legacy_baseline4`、`legacy_full9`、`action_family8` 和 `multitask_v1` 四种训练 Profile
- 新增 Canonical Manifest Schema 与生成工具（`build_canonical_manifest.py`），从 `actions.v3.json` 自动生成可重复、哈希稳定的 `canonical_actions.jsonl`，每条记录同时保留源标签和派生标签，确保可回溯
- 新增逐文件视频解码验证，通过完整解码（`ffmpeg -v error -f null -`）确认每个训练视频可读取，不仅依赖 ffprobe 元数据
- 新增三层内容级重复检测：SHA-256 文件哈希 → 采样帧感知哈希序列 → 候选组帧级相似度复核，区分完全重复、疑似转码重复、同源不同片段和非重复
- 新增 Split 完整性校验，验证现有 `baseline4` 和 `full9` 划分无跨集泄漏（source_video_id、重复文件、疑似转码副本），若发现泄漏则生成版本化替代 split
- 新增审计报告生成，提供从 1084 条原始记录到各 Profile 可训练样本的完整数量核算
- 新增 `releases/v3.1.0/` 不可变发布包，包含 canonical manifest、Schema、splits、审计报告和校验和

所有新增代码写入 `pickleball-action-dataset/src/pb_action_dataset/`，不修改 `actions.v3.json` 源文件，不入侵 `pre-pickleball` 产品后端。

## Capabilities

### New Capabilities

- `dataset-ml-release-contract`: 定义数据集从人工标注到机器学习消费的完整发布契约，包括标签 Profile 映射、Canonical Manifest 生成、视频解码校验、内容级重复检测、Split 完整性验证和审计报告，输出不可变 `releases/v3.1.0/` 发布包

### Modified Capabilities

_无。本 Change 不修改任何已有 spec 的行为约束。`action-classification-preprocessing` 的 clip 导出管线不受影响；本 Change 新增的数据集质量加固位于其上游。_

## Impact

- 新增代码目录：`pickleball-action-dataset/src/pb_action_dataset/`（canonicalize、media_validate、content_dedup、split_validate、audit、release 六个模块）
- 新增 Schema 文件：`pickleball-action-dataset/schemas/model_label_profiles.yaml`、`canonical_manifest.schema.json`
- 新增脚本：`pickleball-action-dataset/scripts/build_canonical_manifest.py`、`verify_media_decode.py`、`detect_content_duplicates.py`、`validate_split_integrity.py`、`build_dataset_release.py`
- 新增发布目录：`pickleball-action-dataset/releases/v3.1.0/`
- 不修改 `pre-pickleball/` 下任何文件
- 不修改 `actions.v3.json`
- 不重启或修改任何运行时服务
