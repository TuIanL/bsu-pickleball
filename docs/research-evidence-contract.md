# 科研证据清单契约（research_evidence_manifest.v1）

面向科研复盘的只读资产索引契约。回答一个问题：**这份分析用的到底是哪些字节、哪些代码、哪些模型**，以及哪些部分已经核验、哪些还不知道。

契约本体在 `backend/contracts/research_evidence/v1/schemas/research_evidence_manifest.schema.json`，实现位于 `backend/app/research_evidence/`。

## 非目标

本项目只登记身份与核验事实，不做以下事情：

- 不搬迁、不复制、不重编码原始资产。
- 不加载权重、不运行模型、不启动应用 lifespan 或数据库。
- 不用当前 HEAD 反推历史运行版本。
- 不把索引完整当作算法质量通过。

## 三层身份

路径不是身份，绝对路径不离开本机。

| 层 | 存放位置 | 形态 | 是否随分享包导出 |
| --- | --- | --- | --- |
| 内容身份 `asset_id` | manifest | `a_` + sha256 前 12 位 | 是 |
| 逻辑定位 `locator` | manifest | `asset://<root_id>/<relative_path>` | 是 |
| 本地位置 | `locations.local.json` | 授权根绝对路径 + 相对路径 | **否** |

`asset_id` 只由内容摘要派生，因此同一份字节在不同平台、不同挂载点、不同副本目录下得到同一个 ID。两个不同摘要若前 12 位相同，`assign_content_ids` 直接报错，不做静默合并。

`locations.local.json` 的 `schema_version` 固定为 `pb.research-evidence-locations.v1.0`，其 `source_roots` 记录每个授权根的逻辑 ID、绝对路径与环境类别，`assets` 记录每个 `asset_id` 的规范 locator 与备用副本位置。

## 顶层字段

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 固定 `pb.research-evidence-manifest.v1.0` |
| `package_id` | `pkg_` + 12 位十六进制，标识一个索引包 |
| `baseline.selected_revision` | 科研候选基线，只允许一个，且必须 `status=known` 并钉到 40 位 commit |
| `baseline.reference_revisions` | 历史对照，可含 `status=unknown`，不代表候选基线 |
| `assets[]` | 资产清单 |
| `run_refs[]` | 运行记录 |
| `checks[]` | 逐项核验结果 |
| `completeness` | `complete` 或 `partial` |
| `limitations[]` | 限制条款，含是否阻断完整声明 |

## 资产字段

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `kind` | `source_video` / `pts_sidecar` / `sync_manifest` / `calibration` / `roster` / `model_weight` / `model_config` / `model_package` / `job_artifact` / `annotation` / `other` | 资产类别 |
| `usage_kind` | `real` / `fixture` / `unknown` | 用途类型，不等于质量 |
| `usage_basis` | 见下节 | 分类依据，可省略但不应推测 |
| `requirement` | `required` / `optional` | 只有 `required` 参与 `complete` 判定 |
| `digest` | `{status, sha256, reason}` | `status=unknown` 时 `sha256` 必须为 `null` 且给出 `reason` |
| `availability` | `present` / `missing` / `unreachable` / `not_checked` | 文件在不在 |
| `verification` | `verified` / `mismatch` / `not_checked` / `unknown` | 内容对不对 |

`availability` 与 `verification` **正交**：文件不在是 `unreachable + not_checked`，不是 `mismatch`。`mismatch` 只用于「读到了，但摘要对不上」。

## 来源等级与 usage_kind 判定顺序

1. **操作者显式声明**（`basis=operator_declared`）优先。
2. 否则采用**来源根策略**（`basis=root_policy`）。测试夹具根声明为 `fixture`。
3. 两者都没有时，即使文件头是合法容器，结果也是 `unknown`（`basis=no_evidence`）。
4. 文件头无法识别时记为 `unknown` 且 `basis=container_unverified`。

**没有任何路径会把文件自动提升为 `real`。** 扩展名、目录名、能否解码都不构成来源证据。

## 正式输入准入

`assert_formal_input_eligible` 逐条拒绝：

- `usage_kind=fixture`：合成或测试夹具。
- `usage_kind=unknown`：来源未知。
- 容器无法识别：疑似伪视频或损坏文件（例如文本改名为 `.mp4`）。
- 扩展名与实际容器不一致：疑似改名伪装。
- `digest.status != known`：内容摘要未知。

容器只读文件头判定，支持 mp4 / avi / matroska / mpegts。不调用 ffmpeg，不解码，因此大文件与慢速外接盘的开销相同。

**合成素材可以是完全合法的 AVI，仍然会被拒绝** —— 结构合法与科研可用是两件事。

## 判定规则

- `completeness=complete` 要求：所有 `required` 资产 `present` 且 `verified`，且不存在 `block_completeness=true` 的 limitation。
- `optional` 资产未核验不影响 `complete`。
- `algorithm_verdict.result` 与 `completeness` 无关：`complete` + `fail` 是合法且常见的组合，表示「证据齐全，但质量确实没过」。
- 历史产物缺版本时写 `status=unknown`、`commit=null`，禁止用当前 HEAD 补齐。

## 覆盖矩阵

所有示例位于 `backend/contracts/research_evidence/v1/fixtures/`。

| 文件 | 预期 | 覆盖点 |
| --- | --- | --- |
| `manifest.complete.example.json` | 通过 | 完整包 + 算法 fail + optional 未核验仍 complete |
| `manifest.partial-windows-missing.example.json` | 通过 | PB-004 阻断、`partial`、不可达与摘要未知 |
| `manifest.historical-gap.example.json` | 通过 | 历史运行版本不可知、结论原样照录 |
| `manifest.fixture-present.example.json` | 通过 | 合成夹具与真实素材共存且可区分 |
| `invalid.known-digest-without-sha.json` | 拒绝 | 声称已知却无摘要 |
| `invalid.unknown-digest-with-sha.json` | 拒绝 | 声称未知却携带摘要值 |
| `invalid.absolute-path-locator.json` | 拒绝 | 分享包出现本机绝对路径 |
| `invalid.complete-with-blocking-limitation.json` | 拒绝 | 完整声明与阻断限制共存 |
| `invalid.unknown-baseline.json` | 拒绝 | 候选基线未钉到 commit |
| `invalid.complete-required-unverified.json` | 拒绝 | 必需资产未核验却声明完整 |

## 操作流程

1. **登记**：声明授权来源根，CLI 只在根内读取，不做全盘扫描。
2. **核验**：分块摘要、受限元数据探测、超时与取消分别记录；元数据成功不升级为全解码成功。
3. **落盘**：`manifest.json` + `checks.json` 可分享，`locations.local.json` 留在本机。
4. **分享前检查**：`assert_no_local_paths` 扫描所有字符串字段，命中 POSIX、Windows 盘符或 UNC 形式即拒绝，包括嵌在说明文字中的路径。

## 权威来源

- 契约：`backend/contracts/research_evidence/v1/schemas/research_evidence_manifest.schema.json`
- 实现：`backend/app/research_evidence/{identity,locations,classification}.py`
- 测试：`backend/tests/test_research_evidence_{contract,locations,classification}.py`
- 提案：`openspec/changes/establish-research-evidence-baseline/`
