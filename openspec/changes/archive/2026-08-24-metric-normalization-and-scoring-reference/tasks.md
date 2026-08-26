## 1. 定义指标与参考契约

- [x] 1.1 定义 `metric-definition-profile.v1` 的 Python/Pydantic 与 TypeScript 类型，覆盖 metric key、单位、来源字段、scope、赛制、方向、上下文和描述性标记
- [x] 1.2 定义 `evidence-sufficiency-profile.v1`，覆盖最小样本、分母规则、空分母、低样本和覆盖率降级行为
- [x] 1.3 定义 `scoring-reference-profile.v1`，覆盖 `expert_threshold`、`target_range`、`empirical_percentile`、参数、fallback、reference source、version 和 profile hash
- [x] 1.4 定义 `normalized-metric-snapshot.v1` 与 `score_eligibility`，明确 raw/canonical/utility/percentile 字段以及不生成 dimension/overall score 的约束
- [x] 1.5 建立首版 metric 白名单，只登记当前 canonical artifact 能证明来源的指标，并将 PB Vision-only 指标标记为 planned/unsupported 或 display-only

## 2. 实现指标规范化引擎

- [x] 2.1 实现从 `metric-snapshot.v1` 读取指标定义、充分度 profile 和 scoring reference profile 的组合器，不修改输入 artifact
- [x] 2.2 实现单位、数值范围、分子/分母和 canonical value 校验，明确区分 `null`、`0`、空分母和缺失字段
- [x] 2.3 实现 `higher_better`、`lower_better`、`target_range`、`context_dependent` 和 `descriptive_only` 的方向处理
- [x] 2.4 实现 score eligibility 派生逻辑，覆盖 eligible、display_only、insufficient_evidence、not_applicable、unsupported、failed 及可解释的 eligibility reasons
- [x] 2.5 实现专家阈值和目标区间到 `[0,1]` utility score 的确定性映射；无经验参考人群时 percentile 必须保持 null
- [x] 2.6 实现 evidence、provenance、source metric ID、definition/reference 版本和 profile hash 的完整传递，禁止写入悬空 evidence ID
- [x] 2.7 实现确定性的 metric ID、稳定排序和 diagnostics/score_coverage 生成，确保相同输入与 profile 可重复生成
- [x] 2.8 确保 `ShotQuality.score`、PB Vision `coach_advice.value`/`avg_rank` 和检测置信度不会单独获得正式评分资格

## 3. 接入分析产物流程

- [x] 3.1 增加 `normalized_metrics_json_path`、公开 url、status 和 detail 字段，并实现 CaptureTake 与 legacy outputs 路径解析
- [x] 3.2 注册 `normalized-metrics` artifact API，返回 `normalized-metric-snapshot.v1` JSON，并复用现有路径穿越、绝对路径和跨 job 保护
- [x] 3.3 在真实 job 完成流程中生成 normalized artifact；规范化失败或参考 profile 缺失不得阻塞既有视觉产物、report 或 insights
- [x] 3.4 保证文件、Pipeline result 和 API 的 schema version、status、detail 与实际可读性一致；缺失可选产物返回 404
- [x] 3.5 增加前端 normalized metric 类型与 analysis client getter，但不接入旧 `skillRatings` 或渲染最终评分 UI

## 4. 测试、文档与交接

- [x] 4.1 增加 schema 测试，覆盖 available、display_only、insufficient_evidence、not_applicable、unsupported、failed、空 metrics 和字段语义校验
- [x] 4.2 增加方向与参考测试，覆盖专家阈值、目标区间、上下文缺失、缺少 profile、无 population 时 percentile 为 null 和不合成群体分布
- [x] 4.3 增加样本与分母测试，覆盖低样本、zero denominator、null 不转 0、单打双打不适用和候选 evidence 排除
- [x] 4.4 增加重复生成与 evidence 完整性测试，验证除 generated_at 外逐字段一致、稳定排序和无悬空引用
- [x] 4.5 增加 artifact path/API/legacy job/非阻塞降级测试，验证旧 tracking、trajectory、report 和 insights 行为不受破坏
- [x] 4.6 增加 PB Vision 外部字段隔离测试，确认 `coach_advice.value`、`avg_rank`、ShotQuality 和 detector confidence 不会生成正式 utility
- [x] 4.7 编写面向后续 `performance-score.v1` 的交接说明，明确 normalized artifact、reference profile、eligibility 和 score coverage 的输入边界
- [x] 4.8 运行后端、前端类型/单测、构建和改动文件 lint，更新任务验证记录
