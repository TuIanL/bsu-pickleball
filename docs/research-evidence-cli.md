# 科研证据索引 CLI 使用与撤回

`backend/scripts/research_evidence.py` 把授权来源根里的指定文件登记成一个可校验的证据包。三条硬规则：

- **不扫描磁盘**：每个文件都要在配置里点名，授权根只限定范围，不作为搜索范围。
- **不改动源资产**：全程只读，读前读后各取一次 size/mtime 作为未被修改的证据。
- **不覆写**：输出目录必须为空，已存在同名产物直接拒绝。

## 命令一览

| 命令 | 作用 |
| --- | --- |
| `build` | 按配置生成 `manifest.json`、`checks.json`、`locations.local.json` |
| `verify` | 校验结构、契约、引用完整性与路径泄露 |
| `verify --deep` | 额外按本机映射重算摘要，检测内容是否被改动 |
| `verify --shareable` | 按分享包口径校验，允许缺少本机映射 |
| `publish` | 导出可分享副本，只含 manifest 与 checks |

## 完整流程

在 `backend/` 目录下执行。

**1. 写配置**

```json
{
  "package_id": "pkg_7f3a9c21b4de",
  "source_roots": [
    {
      "root_id": "root_captures",
      "path": "/Volumes/Elements/项目/匹克球/视频录制/captures",
      "source_kind": "external_disk"
    }
  ],
  "assets": [
    {
      "root_id": "root_captures",
      "relative_path": "2026-07-20/take_sync_20260720_122645_317228/174_merged.mp4",
      "kind": "source_video",
      "usage_kind": "real",
      "requirement": "required"
    }
  ],
  "baseline": {
    "selected_revision": {
      "label": "selected_baseline",
      "status": "known",
      "commit": "bd136d661bf391104b9193752f7c868878e63a48",
      "worktree_clean": true,
      "dirty_patch": {
        "status": "known",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      },
      "note": null
    },
    "reference_revisions": []
  }
}
```

`baseline.selected_revision` 是必填项。没有它，包会拒绝构建 —— 科研基线必须由负责人钉到具体提交。

**2. 构建**

```bash
python scripts/research_evidence.py build --config roots.json --output ./out/pkg_7f3a9c21b4de
```

**3. 校验**

```bash
python scripts/research_evidence.py verify --package ./out/pkg_7f3a9c21b4de
python scripts/research_evidence.py verify --package ./out/pkg_7f3a9c21b4de --deep
```

`--deep` 需要外接盘在线。盘未挂载时 `deep_assets_readable` 会失败，这属于「重新核验未通过」，不是「内容被改动」—— 两种结论在输出里分开显示。

**4. 导出分享包**

```bash
python scripts/research_evidence.py publish --package ./out/pkg_7f3a9c21b4de --output ./share/pkg_7f3a9c21b4de
python scripts/research_evidence.py verify --package ./share/pkg_7f3a9c21b4de --shareable
```

分享包只有 `manifest.json` 与 `checks.json`。`locations.local.json` 留在本机，不随包导出。

## 撤回

索引是**纯增量、只写新目录**的产物，撤回只需删除输出目录：

```bash
rm -rf ./out/pkg_7f3a9c21b4de
```

- 源资产、模型、数据库、历史 Job 不会被触碰，因此无需回滚源端。
- 已分享出去的包无法撤回，但它不含任何本机路径，只含逻辑定位串与摘要。
- 需要重建时换一个新的输出目录即可，旧目录不会被复用。

## 失败与中断

| 情形 | 行为 |
| --- | --- |
| 输出目录非空 | 构建前拒绝，不产生任何文件 |
| 输出目录在授权根内 | 构建前拒绝 |
| 配置缺 `baseline` | 加载配置时拒绝 |
| 资产摘要不可得且未给 `asset_id` | 构建失败，不写盘 |
| 按 Ctrl-C 中断 | 退出码 130，提示「源资产未被修改」 |
| 单文件超时 | 记为 `not_checked`，包标 `partial` |

构建先在内存中完成全部资产处理并通过契约自检，之后才写盘。因此**失败或中断不会留下半成品包**：要么输出目录为空，要么三个文件齐全。

**部分日志的辨认方式**：中断时 stderr 会打印「已中断；源资产未被修改」；构建失败时打印具体原因（哪条资产、哪个字段、哪个引用）。判读时以输出目录是否存在产物为准 —— 空目录即未写出任何结果。

## 常见错误

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `输出目录位于授权来源根内` | 输出指到了素材目录里 | 换到素材根之外的新目录 |
| `输出目录已存在且非空` | 复用了旧目录 | 删掉旧目录或换个新名字 |
| `配置必须提供 baseline.selected_revision` | 缺少科研基线 | 补上负责人确认的 commit |
| `无法为 ... 派生内容身份` | 文件不可读或超时 | 先修可读性，或为已知缺失项显式给 `asset_id` |
| `manifest 含本机绝对路径` | 旧包或手改引入 | 重新构建，不要手改 manifest |
| `deep_assets_readable` 失败 | 外接盘未挂载 | 挂载后重跑，不要当成内容损坏 |

## 相关文件

- 实现：`backend/app/research_evidence/`
- 契约：`backend/contracts/research_evidence/v1/schemas/research_evidence_manifest.schema.json`
- 字段与等级说明：`docs/research-evidence-contract.md`
