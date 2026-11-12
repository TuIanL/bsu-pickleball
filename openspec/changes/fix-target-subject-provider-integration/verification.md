# 集成验证记录

## 范围与授权

基线main0ce572b；来源155fbb4。本次对话明确批准四项修复、回归测试及通过后合入main。原演示/人物提取/历史分支和3个原worktree不修改。独立集成worktree负责本次代码与测试，未执行Archive、部署、数据库迁移或真实模型发布。

## 本地结果（2026-11-12）

- Python3.11.15干净临时环境按哈希锁安装，49个锁定包及项目可编辑安装成功；原有39个版本均未升级，uv pip check通过。
- provider/契约/分发/跟踪相关回归：42 passed。
- 完整基础后端：1985 passed、5 skipped、22 warnings，74.92秒。命令沿用现有CI对两份外部素材测试的排除口径，没有新增跳过或删除断言。
- 前端：103个文件、803测试通过；TypeScript及生产构建通过，首屏静态JS gzip142199字节；lint0错误、43条既有警告。
- 后端ruff（既有F401/F841门禁）通过；5个新Python模块的异常策略检查0违规；本Change strict校验通过，git diff --check通过。

## 规格到证据

| Requirement | 实现 | 验证 |
| --- | --- | --- |
| 独立导出与确认边界 | 独立provider，无产品API接线 | 多候选保留、无标签输入、隔离子进程不导入app.database |
| 安装依赖可复现 | pyproject单一来源、requirements锁入口、原版本约束 | 干净哈希安装、pip check、仓库外CLI help |
| 契约随分发包提供 | importlib.resources、包内镜像及摘要 | 完整集合/字节一致，sdist→离线wheel→独立目录Schema/fixture/CLI导入 |
| 实际媒体声明一致 | 元数据/完整帧数核验、越界/重复拒绝、失败不发布 | 真实3帧声明2/5、尺寸/fps、无效fps、提前结束、原结果保护 |
| 有效跟踪配置可追溯 | 固定motion默认、显式算法、有效配置摘要 | 环境变量motion/legacy/无效值均不暗改默认结果；显式算法1/2候选及不同摘要 |

## 既有基础门禁支撑修复

首次完整检查1981通过、3失败、6跳过。Windows恢复测试在非Windows环境缺少psutil及Windows-only的进程flag替身；取消录制测试让假进程立即返回，导致取消前就结束。修复仅补开发依赖与测试替身：Windows测试提供已mock Popen的flag哨兵，取消测试用事件等到kill后退出；生产录制及Windows运行脚本均未修改。三个原失败用例均通过，完整复跑通过。

## 交付状态

[PR #3](https://github.com/TuIanL/bsu-pickleball/pull/3)的准确提交为b128bdd011380b6e39b4b2a771054aaae88e6bca；[PR CI](https://github.com/TuIanL/bsu-pickleball/actions/runs/43158737250)及[分支push CI](https://github.com/TuIanL/bsu-pickleball/actions/runs/43158707537)全部成功后，按负责人本轮授权合入main，合并提交为49a553255eb598871a4c92b29676778fc40e9c3f。远端基础后端为1985 passed、5 skipped、22 warnings（62.22秒），quality、backend-lint、openspec三项门禁均通过。

合并后核对：原provider提交155fbb4已是origin/main祖先；其他原有分支及两个归档标签均与操作前快照一致，三个原worktree的HEAD保持f6a1d53、ea2224e、155fbb4，原主工作区仍为干净的演示分支。任务5.1/5.2据此完成；本记录与任务勾选作为合并后的纯文档补充，不改动已验证代码。临时集成worktree将在文档推送并同步本地主线后回收。

| 验证维度 | 结果 |
| --- | --- |
| 完整性 | 11/11实施任务完成（含合并后稳定性补充），5/5新增Requirement有实现与测试证据 |
| 正确性 | 5/5Requirement映射，8/8Scenario覆盖；媒体异常不发布，配置与分发回归通过 |
| 一致性 | 隔离整合、单一依赖源、包资源、固定默认算法与CFR边界符合design；沿用现有pytest与质量门禁模式 |

本Change的规格/任务/设计核验未发现Critical、Warning或Suggestion；完成Verify不自动触发Archive或主规格同步。上述检查仅覆盖本Change明确的工程行为，不扩展为真实科研准确率结论。

远端5项跳过有明确原因：三项真实双摄take素材未提供；一项RTMPose测试所需torch不在基础环境；一项脱敏真实任务包未提供。另两份依赖外部材料的测试文件仍按原CI命令排除，未新增排除项。

## 合并后CI补查与稳定性修复

[主线合并复跑43159321161](https://github.com/TuIanL/bsu-pickleball/actions/runs/43159321161)出现既有心跳测试失败：1984 passed、1 failed、5 skipped，质量步骤中其他测试未失败。`test_worker_heartbeat_runs_without_stage_progress_callbacks`固定睡眠50ms后要求至少三次心跳，持久化/调度开销使实际仅两次；该测试和生产Worker在原集成中均未修改。

补充仅修改测试：用事件确认至少三次持久化心跳，最多等待3秒，并在finally停止及join线程；保留心跳次数、租约ID和线程结束断言。生产Worker及Provider行为不变，使用同一临时集成分支，不修改原有分支。相关心跳/provider/契约/分发46 passed，完整基础后端1985 passed、5 skipped、22 warnings（37.54秒）。新增6.1任务已在准确提交CI通过并按既有授权合入main后记录完成。本次补充不撤销原PR在合并前实际通过的CI证据，也不把合并后的失败写成通过。

## 稳定性补充交付

[PR #4](https://github.com/TuIanL/bsu-pickleball/pull/4)准确提交03a5d766e7c9e2f7c3d021cb9e9e70683ed7cda0的[PR CI](https://github.com/TuIanL/bsu-pickleball/actions/runs/43160386613)及[分支CI](https://github.com/TuIanL/bsu-pickleball/actions/runs/43160353061)均全部成功；前端803通过，完整基础后端1985通过、5跳过（PR 75.81秒、分支65.57秒）。按授权合入main，合并提交34c2cea7426343938e95413ba67c7beb52ae087f；合并后的完整Git tree与已测试03a5d76相同。任务11/11完成，本次后续只更新验收文档与任务勾选。

为保留失败历史：[旧纯文档提交2e15f86的CI](https://github.com/TuIanL/bsu-pickleball/actions/runs/43159946307)曾在VideoAnalysisCard的机位切换播放位置断言失败（0而非36.964）。该前端组件及测试未被本轮修改，之后补充提交的两次独立完整前端运行均803通过；本次未另改前端或把历史失败抹去，此间歇性失败列为后续工程稳定性观察项。

## 限制

未运行真实权重/摄像设备或科研准确率验证；本次是工程与合成回归。CFR工具不替代VFR/双摄PTS合同。分发回归验证契约、导入及CLI help，不宣称完成无Git环境的正式模型运行发布。四人整段历史FAIL及旧研究提案状态保持原意。
