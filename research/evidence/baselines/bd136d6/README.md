# 科研证据索引 — bd136d6

便携索引，用于证明参考 take 的分析输入是哪份字节、哪个模型、哪个代码版本。**不含任何原始媒体、模型权重或本机路径。**

## 生成信息

| 项 | 值 |
| --- | --- |
| `package_id` | `pkg_7f3a9c21b4de` |
| 生成时间 | 2026-11-15T01:29:52Z |
| 索引工具版本 | `169c44d`（工具代码工作区干净） |
| 构建配置摘要 | `34244531ab1d5419c2b8ee6251175fa297391181478bbfe05014cdb8acfd4afb` |
| 科研分析基线 | `bd136d6` |
| 历史对照 | `99c0f19`（11/10 审计快照） |
| `completeness` | `partial` |

三个版本分开记录：分析基线看 `baseline.selected_revision`，工具版本看 `tooling.revision`，历史运行版本看 `run_refs[].code_revision`（一律 `unknown`，未用当前 HEAD 回填）。

本目录的交付提交晚于工具版本提交 `169c44d`；两者之间工具代码未改动，因此 `tooling.revision` 仍然准确。

## 资产清单（11）

| asset_id | 类型 | 机位 | 可用性 | 核验 |
| --- | --- | --- | --- | --- |
| `a_f16e5a2f015c` | source_video | cam1 | present | verified |
| `a_bc957337e964` | source_video | cam2 | present | verified |
| `a_15c5d2b304d3` | pts_sidecar | cam1 + cam2 | present | verified |
| `a_efd2005d6d3c` | sync_manifest | — | present | verified |
| `a_42f960449bad` | sync_manifest | — | present | verified |
| `a_6399ff9fb89e` | roster | — | present | verified |
| `a_d7c96c6f30ba` | calibration | — | present | verified |
| `a_ca301b40c4b9` | calibration | — | present | verified |
| `a_4d3e73ddd312` | model_weight（RTMPose Halpe26） | — | present | verified |
| `a_a13afa56c259` | model_weight（court-line best.pt） | — | present | verified |
| `a_win_job_0d8ec77a76` | job_artifact（Windows） | — | **missing** | unknown |

**`a_15c5d2b304d3` 是两个机位共用的 PTS**：两份 `.pts.jsonl` 字节完全相同（同一 SHA-256），按内容身份归并为一个资产，但 `occurrences` 保留了两条记录 —— cam1 与 cam2 各自的定位串和时间基准（`pts_actual`）。去重没有抹掉机位语义。

## 核验覆盖

| 等级 | 覆盖 |
| --- | --- |
| L0 存在性 | 11/11 |
| L1 元数据 | 2/2 视频（1920×1080、60 fps、698.8 s，仅容器头） |
| L2 摘要 | 11/11（分块 SHA-256，8 MiB） |
| L3 全解码 | 0/11，未执行 |
| 算法质量 | 未运行任何推理 |

## 已知限制

1. **PB-004 阻断**：最新 Windows 整段产物 `job-0d8ec77a76` 未取得，包只能声明 `partial`。缺失项在 `limitations` 中标为 `block_completeness=true`。
2. **历史 fail 保留**：`job-43e7475fd8` 判定 `fail`（观测覆盖 1.1–210.0s），以非阻断限制记录；索引完整性不受算法质量影响，两者不相互覆盖。
3. **同范围相反结论未归因**：`job-7ab0b2ea60`（pass）与 `job-934cb696fd`（fail）覆盖完全相同的 7.0–13.0 秒，两者均无 `config_signature`，当前无法解释（PB-020）。
4. **未全解码**：容器元数据成功不等于逐帧可解。
5. 本索引不构成科研验收通过，也不改变任何历史质量结论。

## 复现

```bash
cd backend

# 1. 复制模板并替换两个占位符
cp research/evidence/baselines/bd136d6/build-config.template.json /tmp/roots.json
#    将 <CAPTURES_ROOT> 与 <MODELS_ROOT> 换成本机授权根

# 2. 构建
python scripts/research_evidence.py build --config /tmp/roots.json --output /tmp/pkg

# 3. 校验（需要本机映射才能做深度复核）
python scripts/research_evidence.py verify --package /tmp/pkg --deep
```

替换路径不会改变 `config_sha256` —— 该摘要只覆盖 `package_id`、`assets`、`historical_jobs` 与 `baseline`，刻意排除 `source_roots` 的本机路径。若重建后摘要仍为 `34244531…`，说明被索引的内容集合与分析基线一致。

## 本目录不含

- 原始视频、PTS 边车、模型权重
- `locations.local.json`（本机位置映射，留在构建机器）
- 任何绝对路径、账号或密钥

`manifest.json` 已通过 `verify --shareable` 全部 11 项检查，其中 `no_local_paths` 确保不含本机路径。
