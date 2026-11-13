# 验证记录：真实参考 take 只读索引

对应 `establish-research-evidence-baseline` 任务 4.1。本文件记录一次真实构建的输入、范围、结果与独立检查。

## 环境与身份

| 项 | 值 |
| --- | --- |
| 构建工具代码 | `2bec387`（research_evidence 模块所在提交） |
| 科研候选基线 | `bd136d6`（manifest `baseline.selected_revision`） |
| 历史对照 | `99c0f19`（11/10 审计快照，仅对照） |
| 工作区状态 | clean，空 patch（`e3b0c442…b855`） |
| 运行环境 | macOS，`miniconda3` Python 3.13，jsonschema 4.26 |
| 输出位置 | 临时目录 `/tmp/pe-4-1-run/pkg2`（非项目内，验证用） |

基线 `bd136d6` 描述的是**分析代码**的科研候选版本；索引工具本身是其后新增的代码。两者刻意分开记录：不把新工具混进旧基线，也不因新工具存在而抬高旧基线。

## 授权来源根

| root_id | 路径 | 类别 |
| --- | --- | --- |
| `root_captures` | `/Volumes/Elements/项目/匹克球/视频录制/captures` | external_disk |
| `root_models` | `…/前期展示web/pre-pickleball/models` | repository |

## 索引范围

参考 take：`take_sync_20260720_122645_317228`（2026-07-20）。

| asset_id | kind | 覆盖对象 | 摘要 | 核验 |
| --- | --- | --- | --- | --- |
| `a_f16e5a2f015c` | source_video | `174_merged.mp4` | 1180 MB | verified |
| `a_bc957337e964` | source_video | `175_merged.mp4` | 1180 MB | verified |
| `a_15c5d2b304d3` | pts_sidecar | 两机位 PTS（内容相同，归并） | 3.4 MB | verified |
| `a_efd2005d6d3c` | sync_manifest | `manifest.json` | 681 B | verified |
| `a_6399ff9fb89e` | roster | `metadata/recording_session.json` | — | verified |
| `a_d7c96c6f30ba` | calibration | `metadata/canonical_court_frame.json` | — | verified |
| `a_ca301b40c4b9` | calibration | `metadata/metric-court-scene/current.json` | — | verified |
| `a_42f960449bad` | sync_manifest | `timeline/sync_calibration.json` | — | verified |
| `a_4d3e73ddd312` | model_weight | RTMPose Halpe26 checkpoint | 53.3 MB | verified |
| `a_a13afa56c259` | model_weight | court-line `best.pt` | 19.7 MB | verified |

结果：`completeness=complete`，`limitations=[]`。

**11 个配置条目归并为 10 个资产**：两个机位的 `.pts.jsonl` 字节完全相同（SHA-256 前 16 位均为 `15c5d2b304d31d4f`），按内容身份合并为一个资产，另一个位置记入 `alternate_locators`。这不是去重优化，而是「路径不是 ID」的直接后果。

媒体元数据（L1，未解码）：两路均为 1920×1080、60 fps、698.8 s。

## 核验范围与等级

| 等级 | 覆盖 | 说明 |
| --- | --- | --- |
| L0 存在性 | 10/10 | 全部在授权根内解析成功 |
| L1 元数据 | 2/2 视频 | ffprobe 读容器头；未解码 |
| L2 摘要 | 10/10 | 全文件分块 SHA-256，8 MiB 分块 |
| L3 全解码 | 0/10 | **未执行**，不作为本项结论 |
| 算法质量 | — | 本项不涉及推理，未产生任何质量判定 |

耗时：build 30.7 s，verify 18.0 s，`verify --deep` 18.0 s。

## 独立检查

1. **引用可解析**：`verify` 的 `references_resolve`、`locations_cover_assets`、`unique_asset_ids`、`unique_locators` 全部通过；13 项检查无一失败。
2. **源文件未被改写**：记录 10 个源文件的 `size` 与 `mtime_ns`，再执行一次完整 build（输出到另一目录），重新比对 —— **无一变化**。
3. **分享包无本机路径**：`no_local_paths` 通过；`locations.local.json` 仅存在于本机包，`publish` 不导出。

## 部分包验证（4.2）

在同一 take 上追加一个缺失的 Windows 产物与两个历史 job，验证「缺必需来源只交付 partial」与「历史 fail 原样保留」。

| 项 | 结果 |
| --- | --- |
| `completeness` | `partial` |
| `a_win_job_0d8ec77a76` | `availability=missing`、`digest=unknown`、`usage_kind=unknown` |
| 阻断限制 | `asset_missing`，`block_completeness=true`，`notion_task=PB-004` |
| 历史 run 1 | `job-43e7475fd8`，1.1–210.0s，`fail`，`code_revision=unknown` |
| 历史 run 2 | `job-7ab0b2ea60`，7.0–13.0s，`pass`，`code_revision=unknown` |
| 历史失败限制 | `historical_run_failed`，`block_completeness=false` |
| `verify` | 11 项全部通过（partial 是合法状态，不是校验失败） |

两条限制刻意区别对待：**缺 Windows 产物阻断完整性声明**，**历史 fail 不阻断索引完整性**。后者属于算法质量结论，与「索引是否完整」正交；把它升级为阻断项会混淆两个维度，把它降级为静默则等于抹掉结论。

历史 run 的 `code_revision` 一律为 `unknown`，不使用当前 HEAD 回填。`run_refs` 中的范围来自轨道时间戳推导，不是任务声明的分析窗口。

## 已知限制

| 限制 | 影响 | 跟踪 |
| --- | --- | --- |
| 最新 Windows 整段产物未取得 | `job-0d8ec77a76`、`job-2b677c38af` 在外接盘与仓库均零命中，未纳入本次索引 | PB-004 |
| 历史产物无 `config_signature` | 同范围相反结论无法归因（见 `docs/research-evidence-contract.md`） | PB-020 |
| 未执行全解码 | L3 未覆盖，可能遗漏容器声明与逐帧可解性的差异 | 本项 Non-Goal |
| 模型来自主工作区 | 模型文件位于 `demo/ai-race-education-coach` 工作目录，不随分支变化 | PB-020 |

本次索引**不代表**四人质量 FAIL 消失，也不构成科研验收通过。

## 复现

```bash
cd backend
python scripts/research_evidence.py build \
  --config /tmp/pe-4-1-run/roots.json \
  --output /tmp/pe-4-1-run/pkg_new
python scripts/research_evidence.py verify --package /tmp/pe-4-1-run/pkg_new
python scripts/research_evidence.py verify --package /tmp/pe-4-1-run/pkg_new --deep
```

配置见 `/tmp/pe-4-1-run/roots.json`（临时文件，不随仓库保存；正式配置待负责人确认输出位置后落盘）。

## 构建期发现并修复的缺陷

真实数据暴露了两个单测覆盖不到的问题，均已修复并补回归测试：

1. **媒体准入误伤非媒体资产**：`assert_formal_input_eligible` 被无差别套用到 JSON 与模型权重，导致 9 个合法资产被判「文件头不是受支持的媒体容器」。现仅对 `kind=source_video` 执行。
2. **同内容副本产生重复 `asset_id`**：两个 PTS 文件内容相同却各生成一条资产，违反唯一性。现按内容身份归并，副本记入 `alternate_locators`。

## 规格—代码—测试—证据矩阵（4.3）

6 个 Requirement、10 个 Scenario 全部映射。

交付证据已同步到 Notion：[14｜科研证据基线索引交付](https://app.notion.com/p/417f602574aa819889dfcea71980ecb3)，评审状态为「待评审」。

| # | Requirement / Scenario | 代码 | 测试 | 真实证据 |
| --- | --- | --- | --- | --- |
| R1 | 科研资产身份与本地位置分离 | `identity.py`、`locations.py` | `test_same_content_across_platform_paths_shares_one_identity`、`test_identical_content_at_two_paths_collapses_to_one_asset` | 两个 PTS 字节相同 → 归并为 `a_15c5d2b304d3`，`alternate_locators` 保留 175 位置 |
| R1·S1 | 两台机器保存同一视频 | 同上 | `test_different_content_at_equivalent_paths_stays_distinct`、`test_windows_separators_are_normalised` | 逻辑定位串不含平台前缀；`locations.local.json` 独存本机路径 |
| R1·S2 | 内容尚不能读取 | `builder.py` 强制显式 `asset_id` | `test_unreadable_asset_requires_an_explicit_asset_id`、`test_unreadable_asset_with_explicit_id_is_recorded_as_missing` | `a_win_job_0d8ec77a76`：`missing` + `digest=unknown` + 原因说明 |
| R2 | 真实素材与测试夹具显式分类 | `classification.py` | `test_text_pretending_to_be_video_is_refused`、`test_synthetic_avi_under_test_root_is_refused` | 10 个真实资产全部 `container=mp4`，无误判 |
| R2·S1 | 合成视频位于上传目录 | 同上 | `test_fake_video_is_refused_even_when_declared_real`、`test_renamed_container_is_refused` | 伪视频与改名伪装均被拒 |
| R2·S2 | 来源用途无法确定 | `classify_usage_kind`（无依据 → unknown） | `test_recognisable_container_without_evidence_stays_unknown` | 缺失 Windows 资产 `usage_kind=unknown`，未提升为 real |
| R3 | 核验结果区分访问与完整性 | `hashing.py`、`media_probe.py` | `test_state_matrix_matches_documented_rules` | `verify --deep` 分开报告 `deep_digest_match` 与 `deep_assets_readable` |
| R3·S1 | 外接盘恢复挂载 | `inspect_file` 重算 + 新报告 | `test_deep_verify_separates_missing_from_changed_files` | 175 在本轮 ffprobe 成功（设计阶段曾记 15 秒超时），旧结论未被改写 |
| R3·S2 | 媒体探测超时 | `probe_media` 的 `status=timeout` | `test_probe_timeout_is_distinct_from_error`、`test_timeout_is_recorded_as_not_checked` | 本轮无真实超时，由单测覆盖；超时不写 `mismatch` |
| R4 | 运行证据冻结版本和适用范围 | `importers.py`、`builder._import_historical_runs` | `test_range_is_labelled_as_derived_not_declared`、`test_run_never_carries_a_backfilled_revision` | 9 个历史 job 导入，`code_revision` 一律 `unknown` |
| R4·S1 | 旧签名没有包含同步内容 | 同上 | `test_never_recorded_fields_are_always_flagged_missing`、`test_null_config_signature_is_recorded_instead_of_invented` | 每次导入固定 4 项缺失：`code_revision`、`sync_digest`、`config_signature`、`baseline_job_id` |
| R4·S2 | 文档只有便携摘要 | `builder.py` 无 tracks 不造范围 | `test_job_without_tracks_gets_no_invented_range` | `job-e97318f10c` 无轨道 → 记 `historical_run_range_unknown`，不写 `run_refs` |
| R5 | 失败和部分证据不被导出结论覆盖 | `builder._completeness` + limitations | `test_short_pass_and_long_fail_coexist_without_merging`、`completeness_consistent` 系列 | `partial`：`asset_missing` 阻断 + `historical_run_failed` 不阻断 |
| R5·S1 | 短片通过而全段失败 | `pair_runs_with_quality`（不合并、不择优） | `test_long_fail_does_not_erase_an_enclosed_short_pass`、`test_no_run_may_claim_to_cover_the_whole_take` | `job-43e7475fd8`（fail，1.1–210.0s）与 `job-7ab0b2ea60`（pass，7.0–13.0s）并列 |
| R6 | 证据核验不修改原始资产 | 前后快照、`write_package` 拒绝覆写、`publish` 排除本机映射 | `test_inspection_does_not_modify_the_input`、`test_publish_excludes_the_local_mapping` | 10 个文件两次构建后 size/mtime 全部未变 |
| R6·S1 | 核验失败或被取消 | `cli.py` 中断路径、先构建后写盘 | `test_cancelled_build_leaves_sources_untouched`、`test_interrupted_manifest_build_returns_no_partial_package` | 中断退出码 130，源文件字节级不变，无半成品包 |

## 自审结论

逐项核对后确认，本 Change 的实现**不包含**以下行为：

| 排除项 | 依据 |
| --- | --- |
| 模型推理 | 只做文件头读取、ffprobe 元数据、SHA-256；无权重加载、无 tensor 运算 |
| 数据库迁移/写入 | 子进程测试断言 `app.database`、`sqlalchemy` 未加载；无 DDL/DML |
| 部署或发布 | `publish` 只复制两个 JSON 到用户指定目录，无网络请求、无上传 |
| 原始资产修改 | 10 个文件两次构建后 size/mtime 完全一致；`inspect_file` 返回 `input_unchanged` |
| 历史结论改写 | 历史 `fail` 原样进入 `run_refs` 与非阻断 limitation，未升级也未降级 |

**独立复核状态：待安排。** 本文件由实施者自审产生，不构成独立复核结论。按 4.3 要求，需由未参与实现的复核者确认上述排除项；在此之前不应对外声称已通过独立验证。
