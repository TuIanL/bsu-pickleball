# 独立复核报告 — `49767b9`

复核者：独立 QA Agent（未参与本 Change 实现）
复核方式：在独立工作树 `/tmp/qa-review-49767b9`（detached HEAD，工作区干净）中执行
复核时间：2026-11-15
被复核 SHA：`49767b9e57db22105cd7aeab9ba2d487b9846425`

## 总体结论

**PASS WITH CONCERNS**

七项检查中四项 PASS、三项 CONCERN。所有测试通过（`202 passed`），但结论不依赖这些断言，均为独立实测。

## 逐项结论

| # | 项 | 结论 | 关键证据 |
| --- | --- | --- | --- |
| 1 | 契约一致性 | CONCERN | 6 个反例全部被拒且错误位置精确；但 Schema 顶层必填不含 `tooling`、`occurrences` 非必需，与 verify 的强制检查不一致 —— 仅按 Schema 校验的第三方会接受缺工具版本的包 |
| 2 | 去重后引用完整性 | CONCERN | 真实 PTS 去重后 cam1/cam2 与 `pts_actual` 保留，引用全部可解析；但合并按 locator 字典序取 `group[0]`，实测 `real+required` 被 `fixture+optional` 覆盖且包仍 `complete` |
| 3 | 来源分类 | CONCERN | 扩展名/目录名/可解码性均未参与提升，无声明即 `unknown`；但拒绝只写进 `limitations`，伪视频作 optional 时资产仍标 `usage_kind=real`、`verification=verified`，包 `complete` |
| 4 | 完整性判定 | PASS | required 阻断、optional 不阻断、历史 `fail` 与完整性正交，均实测确认 |
| 5 | 非破坏性 | PASS | 真实构建 10 资产 mtime 无变化；覆写保护与 `publish` 拒绝均有效 |
| 6 | CLI 隔离 | PASS | 子进程实测 `app.main`/`app.database`/`sqlalchemy`/`fastapi`/`torch` 全未加载 |
| 7 | 可复现性 | PASS | 换路径后 `config_sha256` 仍为 `34244531…4afb`；真实重建与交付包 9/9 摘要一致 |

## 发现的问题

1. **中** — 去重合并吞掉每副本语义（`builder.py:574-593`）。胜者由 locator 字典序决定，`usage_kind`/`requirement`/`notion_task` 不合并也不校验。
2. **中** — 伪视频/合成夹具的拒绝不落到资产字段（`builder.py:367`、`:604-613`、`:523-531`、`:986-1008`）。`metadata_probe=failed` 对完整性判定与 verify 完全无影响。
3. **中** — 历史判定可能嫁给错误的运行（`builder.py:452-455`）。按目录取第一个质量报告，不校验 `job_id`。
4. **中** — 深度校验不覆盖去重副本（`builder.py:1052-1073`）。改副本 1 字节后 `verify --deep` 仍通过。
5. **低-中** — 历史产物解析失败直接抛栈（`cli.py:89`）。`ArtifactImportError` 未转换，退出码 1 与「校验未通过」同码。
6. **低** — 契约与校验器必填集合不一致。
7. **低** — `completeness_consistent` 与 Schema `allOf` 等价，冗余。
8. **低** — 只读证据未入包（`hashing.py:72,173-174` 算出但 `builder.py:291` 丢弃）。
9. **低** — `publish` 不做源根包含检查（`builder.py:1116` 传空 roots）。
10. **低** — `write_package` 只防同名文件（`builder.py:758-784`）。
11. **提示** — `run_refs[].consumes` 恒为 `[]`（`builder.py:489`）。
12. **提示** — CLI 依赖 pydantic（`locations.py:14,143`）。

## 无法验证的项

- 两个 `model_weight` 资产无法本机重算摘要：复核环境中 `models/` 仅有 `MODEL_MANIFEST.json`，实际权重不在该工作树。间接旁证：包内 `asset_id` 前 12 位与 `MODEL_MANIFEST.json` 记录一致。
- `verify --deep` 在便携包上不可用（无 `locations.local.json`，按设计）——非缺陷。

## 对「是否可视为通过独立复核」的判断

可以，但带条件。四项硬承诺（契约条件约束、机位与时间基准在去重后保留、只读不写、CLI 无应用栈依赖、跨机器摘要稳定、便携包无本机路径）均被独立实测证实。

不构成无条件通过的原因是问题 1、2、4 直接触及「不得用去重或声明掩盖事实」这一核心意图：`usage_kind`/`requirement` 会被字典序静默降级，伪视频在 optional 位置仍以 `real+verified` 进入 `complete` 包，去重副本的内容漂移不被深度校验发现。这些在 `49767b9` 的交付包中未被触发，但属于工具可被误用且无告警的路径。

建议修复后做一次聚焦复核。
