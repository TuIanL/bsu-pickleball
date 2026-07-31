## 1. 项目结构与 Schema 定义

- [x] 1.1 在 `pickleball-action-dataset/` 下创建 `src/pb_action_dataset/` Python 包（含 `__init__.py`、`pyproject.toml`），安装 opencv-python、imagehash、scikit-image、pydantic 依赖
- [x] 1.2 创建 `schemas/model_label_profiles.yaml`：定义 `legacy_baseline4`、`legacy_full9`、`action_family8` 和 `multitask_v1` 四个 Profile，每个含 target_type、classes 和派生规则
- [x] 1.3 创建 `schemas/canonical_manifest.schema.json`：定义 canonical_actions.jsonl 每行记录的 JSON Schema，包含必需字段、可选字段、枚举值和格式约束
- [x] 1.4 编写测试 `tests/test_label_mapping.py`：验证 forehand_drive → action_family=drive/stroke_side=forehand，dink+forehand → action_family=dink/stroke_side=forehand，dink+unknown → stroke_side=unknown 等映射规则

## 2. Canonical Manifest 生成

- [x] 2.1 实现 `src/pb_action_dataset/canonicalize.py`：读取 `actions.v3.json`、`label_schema.yaml` 和 `model_label_profiles.yaml`，对每条样本执行标签派生，生成 canonical 记录
- [x] 2.2 实现 `scripts/build_canonical_manifest.py` CLI：接受 `--annotations`、`--video-root`、`--profiles`、`--dedup-report`、`--output` 参数，输出 `canonical_actions.jsonl`
- [x] 2.3 确保可重复性：对同一输入重复执行两次，验证输出 SHA-256 一致；class_id 分配顺序稳定
- [x] 2.4 处理边界情况：skipped 样本不出现在 manifest 中；label_confidence=medium 标记 review_status=needs_review；缺失字段使用合理默认值
- [x] 2.5 编写测试 `tests/test_canonicalize.py`：验证记录结构完整、源标签保留、派生标签正确、eligibility 字段正确设置

## 3. 视频完整解码验证

- [x] 3.1 实现 `src/pb_action_dataset/media_validate.py`：对每个视频调用 `ffmpeg -v error -i <input> -f null -`，解析退出码和输出，记录实际解码帧数
- [x] 3.2 实现 `scripts/verify_media_decode.py` CLI：接受 `--video-root` 和 `--manifest`（canonical_actions.jsonl 路径），逐文件验证，输出 `reports/media_decode_report.csv`
- [x] 3.3 核对解码帧数与 `video_meta.num_frames`：允许 ±2 帧容差，超出则标记 `frame_count_mismatch`；核对实际时长与 `duration_ms`，偏差 > 5% 标记 `duration_mismatch`（仅 warning）
- [x] 3.4 对 `decode_status != passed` 的样本，自动将其所有 eligibility 设为 `excluded`，更新 canonical manifest
- [x] 3.5 编写测试 `tests/test_media_validate.py`：使用 fixtures 中的正常视频、损坏视频、空文件、帧数不匹配视频

## 4. 内容级重复检测

- [x] 4.1 实现 `src/pb_action_dataset/content_dedup.py` 第一层（SHA-256）：计算所有视频文件的 SHA-256 哈希，将哈希相同的归入 exact_duplicate 组
- [x] 4.2 实现第二层（感知哈希序列）：对每个视频在 10%/30%/50%/70%/90% 位置采样帧，计算每帧 pHash，生成 5 元素哈希向量；对所有视频对计算向量间平均 Hamming distance
- [x] 4.3 实现第三层（SSIM 复核）：对第二层筛选出的候选组（平均 Hamming distance < 阈值 × 5），抽取对应位置帧计算 SSIM，SSIM > 0.95 确认为 probable_reencoded_duplicate
- [x] 4.4 排除已知同源样本：共享 `source_video_id` 的样本不触发重复检测（已知是同源不同裁剪）
- [x] 4.5 实现 `scripts/detect_content_duplicates.py` CLI：接受 `--video-root` 和 `--manifest`，输出 `reports/duplicate_groups.csv`
- [x] 4.6 将去重结果写回 canonical manifest 的 `dedup` 字段：exact_duplicate 组中只保留一个主样本（其余标记 `dedup.exact_duplicate_group`），probable_reencoded_duplicate 样本标记 `dedup.perceptual_duplicate_group`
- [x] 4.7 编写测试 `tests/test_content_dedup.py`：使用 fixtures 中的相同文件、轻微转码文件、不同内容文件

## 5. Split 完整性校验

- [x] 5.1 实现 `src/pb_action_dataset/split_validate.py`：逐项执行校验：source_video_id 不跨集、重复文件不跨集、skipped 不出现、ID 存在性、ID 唯一性
- [x] 5.2 实现 `scripts/validate_split_integrity.py` CLI：接受 `--splits-dir`、`--manifest`、`--output`，输出 `reports/split_integrity_report.json`
- [x] 5.3 校验通过时，将现有 split 文件原样复制到 `releases/v3.1.0/splits/`
- [x] 5.4 校验失败时，生成 `baseline4_v2_*.txt` 或 `full9_v2_*.txt`，保留旧版文件，在审计报告中记录泄漏详情和修复措施
- [x] 5.5 编写测试 `tests/test_split_validate.py`：模拟正常 split、跨集泄漏 split、包含 skipped 的 split、包含未知 ID 的 split、重复 ID 的 split

## 6. 审计报告与 v3.1.0 发布包

- [x] 6.1 实现 `src/pb_action_dataset/audit.py`：生成完整数量核算（原始 → active → skipped → 各 Profile eligible）、类别分布、媒体统计、数据问题汇总
- [x] 6.2 输出 `reports/dataset_summary.md`（供团队阅读）和 `reports/dataset_audit.csv`（结构化统计）
- [x] 6.3 输出 `reports/source_groups.csv`：从 provenance 提取所有 source_video_id 及其样本列表
- [x] 6.4 自动派生 `views/review_ids.txt`（label_confidence=medium）、`views/rejected_ids.txt`（skipped + 解码失败）、`views/side_masked_ids.txt`（stroke_side=unknown）
- [x] 6.5 实现 `src/pb_action_dataset/release.py` 和 `scripts/build_dataset_release.py`：组装 `releases/v3.1.0/` 完整目录结构
- [x] 6.6 生成 `release_manifest.json`（含版本号、父版本、各项 SHA-256、构建命令、时间戳）和 `checksums.sha256`（所有发布文件校验和）
- [x] 6.7 验收测试：验证发布包完整可读、canonical manifest 哈希与 release_manifest 一致、所有校验和可验证

## 7. 测试 Fixtures 准备

- [x] 7.1 准备正常视频 fixture：一个可解码的短 MP4（~30 帧），对应一条完整 v3 标注
- [x] 7.2 准备损坏视频 fixture：一个 0 字节文件 + 一个无法解码的二进制文件
- [x] 7.3 准备重复视频 fixture：两个完全相同的 MP4 + 一个轻微转码版本（分辨率不同）
- [x] 7.4 准备标注 fixture：包含正常样本、skipped 样本、medium confidence 样本、unknown side 样本的迷你 `actions.fixture.json`
- [x] 7.5 准备 split fixture：正常 split + 含跨集泄漏的 split + 含未知 ID 的 split

## 8. 文档与收尾

- [x] 8.1 更新 `pickleball-action-dataset/README.md`：添加 v3.1.0 发布说明、ML 消费指南、canonical manifest 字段说明
- [x] 8.2 确保 `actions.v3.json` 未被修改（对比 SHA-256）
- [x] 8.3 生成最终 `releases/v3.1.0/reports/dataset_summary.md` 供团队审核
