# PR #5 范围审计

审计对象：`workbuddy/main-e3fcd91e` → `main`。首次审计时 15 个提交（head `714fda2`），修复阶段复核时 28 个（head `75fa80f`），收尾时 30 个（head `11b8e77`，新增均为文档与产物）。分类结论三次一致。
审计日期：2026-11-15。执行人：实施者（非独立复核）。

## 结论摘要

PR 内包含三类改动，其中只有第三类属于本 Change：

| 类别 | 提交 | 文件数 | 是否属于本 PR | 是否已获批 |
| --- | --- | --- | --- | --- |
| fix-target 归档 | `1100f47` | 6（纯 rename） | **否** | 是 |
| target-subject-provider 主规格 | `1100f47` | 1（新增 58 行） | **否** | 是 |
| restore 规格增量修复 | `1100f47` | 3（+20 行） | **否** | 是 |
| establish 实施 | `e1ddc6c`…`714fda2` | 36 | 是 | 是 |

**建议：保持现状，在 PR 描述中把 `1100f47` 标注为「前置清理」。** 拆分需要 rebase 改写 14 个提交的 SHA 并重建 PR，收益仅为粒度纯净，代价与风险不成比例。若必须拆分，见文末方案。

## 逐项说明

### 1. fix-target-subject-provider-integration 归档（6 个文件）

**改了什么**：`openspec/changes/fix-target-subject-provider-integration/` 下 6 个文件移动到 `archive/2026-11-12-fix-target-subject-provider-integration/`，内容零改动（100% rename）。

**为何存在**：该 Change 11/11 任务完成、经 PR #3/#4 合入 main（`bd136d6`）、CI 全绿，但始终未执行归档。归档是 OpenSpec 流程的收尾步骤，缺失会导致活跃 Change 列表虚高、主规格不更新。

**是否已获批**：是。2026-11-12 会话中实施者提出「归档 fix-target」，负责人回复「一起提交吧」，随即执行 `openspec archive`。

**是否应属于本 PR**：**否**。它与科研证据基线无关，属于前一 Change 的流程补账。

### 2. `openspec/specs/target-subject-provider/spec.md`（新增 58 行）

**改了什么**：新建主规格文件，含 5 条 Requirement。

**为何存在**：这不是手工新增，而是 `openspec archive` 的固有行为 —— 归档时把 Change 的 delta 合并进主规格（CLI 输出 `target-subject-provider: create`，`+ 5 added`）。

**是否已获批**：是，随归档一并获批。

**是否应属于本 PR**：**否**，与第 1 项同源，不可单独剥离。

### 3. restore-confirmed-four-player-joint-analysis 规格增量修复（3 个文件）

**改了什么**：

| 文件 | 改动 | 性质 |
| --- | --- | --- |
| `multiview-fused-player-overlay/spec.md` | `已确认身份标签统一` → `身份标签统一` | 场景改名 |
| `structured-heatmap/spec.md` | 补回 `分析完成后返回热力图数据`（+6 行） | 补漏场景 |
| `multiview-player-identity-stability/spec.md` | 补回 `双打侧映射一致` / `单打侧映射一致`（+12 行），断言改写 | 补漏 + 语义对齐 |

**为何存在**：该 Change 的 MODIFIED 块漏掉了主规格已有的 Scenario。`openspec archive` 对 MODIFIED 采取整块替换，校验器会拒绝丢失 Scenario 的写法 —— 当时 `validate --all` 为 218 passed / 1 failed，且若强行归档会丢失 4 个场景。

**是否已获批**：是。第三行的断言改写（`P1/2=near` → 按冻结 Team + 端位 + 视角推导）于 2026-11-12 向负责人说明「原断言与新 design 直接矛盾」，负责人回复「按你这个说的做就行」；前两行为纯补漏，未改变设计意图。

**是否应属于本 PR**：**否**。但它是本 PR CI 中 `openspec` 检查通过的前提 —— 不修则 `validate --all` 始终为 1 failed。

## 附：评审第 2 条的规格覆盖对照

评审要求「检查初始端位、视角朝向、动态换边和历史任务兼容性」。对应内容位于 `restore-confirmed-four-player-joint-analysis/specs/multiview-player-identity-stability/spec.md`：

| 检查项 | 覆盖位置 | 表述 |
| --- | --- | --- |
| 初始端位 | requirement 正文 + `初始端位相反` 场景 | `initial_team_a_end=end_b` 时 P1/P2 → end_b，P3/P4 → end_a |
| 视角朝向 | requirement 正文 | 结合 canonical 端位及当前视角朝向计算展示侧 |
| 动态换边 | `初始端位相反` 场景第二条断言 | 切换展示机位只改变画面投影，不改变 canonical Team/端位归属 |
| 历史任务兼容 | requirement 正文末句 + `历史任务缺名册` 场景 | 旧 Job 缺冻结名册时保留历史槽位映射并标注来源，不得伪称为用户确认 |

四项均有覆盖，无需补写。该规格属于 `restore` Change，不在本 PR 的实现范围。

## 附：评审第 5 条的实现缺口（已于 `e9288e5` 关闭）

评审有条件批准「相同 SHA-256 的 PTS 归并」，条件为：

> 必须完整保留 Cam1/Cam2 各自的使用关系、机位角色和时间映射，不得因内容去重而丢失上下文。

**该条件现已满足。** 契约在 `e9288e5` 重构为「内容资产 + 使用关系」两层：`asset` 只携带字节事实，`usage` 各自携带 `locator`/`view_role`/`usage_kind`/`requirement`/`source_root_id`/`time_base`。交付包中 `a_15c5d2b304d3` 保留两条 `usage`（cam1、cam2，均为 `real`/`required`/`pts_actual`）。

以下为审计当时的记录，保留以便追溯问题演进：

- manifest 的 `asset` 只有单个 `locator`；
- 另一份副本仅以 `notes` 文本形式提及（「同内容副本（未重复登记）：asset://…」）；
- `locations.local.json` 的 `alternate_locators` 只在本机映射中保存字符串，不含机位角色或时间语义。

即：去重后**无法从产物判断哪一份是 Cam1、哪一份是 Cam2，也无法知道两者各自对应的时间基准**。这与评审条件冲突，属于必须修复项。

## 若必须拆分

1. 从 `1100f47` 建分支 `chore/openspec-cleanup`，推送并开 PR；
2. 在 `workbuddy/main-e3fcd91e` 执行 `git rebase --onto bd136d6 1100f47`；
3. 强推分支，关闭 PR #5 并以新分支重建。

代价：28 个提交 SHA 全部改写，PR #5 需重建，已有 CI 结果作废。**不建议在当前阶段执行。**
