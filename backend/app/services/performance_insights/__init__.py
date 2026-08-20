"""Performance Insights Engine —— 洞察引擎服务包。

架构（change design.md D1/D2）：
    AnalysisPipelineResult（已落盘产物）
            ↓
    PerformanceEvidenceAssembler     ← 只读 artifacts，事实层
            ↓
    InsightRuleEngine（rule_profile v1）  ← 解释层，权威维度状态
            ↓
    performance_insights.json（落盘，可独立再生成）
            ↓
    AnalysisReportProjector          ← 投影层，只展示不判断

四条硬不变量（specs/performance-insights）：
1. 真实报告零 demo 结论（import 守卫测试保证）；
2. 每条 finding ≥1 条真实 evidence；
3. 数据不足输出 insufficient_evidence 而非硬算分；
4. 不生成未经校准的技能分 / 历史趋势 / 战术结论。
"""

from app.services.performance_insights.service import (
    generate_and_persist_insights,
    generate_insights_for_result,
    regenerate_insights_for_job,
)

__all__ = [
    "generate_and_persist_insights",
    "generate_insights_for_result",
    "regenerate_insights_for_job",
]
