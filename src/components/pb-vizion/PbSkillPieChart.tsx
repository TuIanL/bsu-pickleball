import { useMemo } from "react";
import type { PbDimensionKey } from "../../types/pbReport";
import { PB_DIMENSION_META, PB_DIMENSION_ORDER } from "../../types/pbReport";
import { EChart } from "../platform/viz/EChart";
import type { EChartsCoreOption } from "echarts/core";

const DIM_COLORS: Record<PbDimensionKey, string> = {
  kitchen: "#A855F7",
  ballctrl: "#3B82F6",
  defense: "#06B6D4",
  offense: "#F97316",
  courtiq: "#EAB308",
  targeting: "#EC4899",
};

interface PbSkillPieChartProps {
  scores: Record<PbDimensionKey, number>;
}

export default function PbSkillPieChart({ scores }: PbSkillPieChartProps) {
  const option = useMemo<EChartsCoreOption>(() => {
    const data = PB_DIMENSION_ORDER.map((key) => {
      const meta = PB_DIMENSION_META[key];
      const raw = Math.max(0, Math.min(1, scores[key] ?? 0));
      return {
        name: meta.label,
        value: raw,
        itemStyle: {
          color: DIM_COLORS[key],
        },
      };
    });

    return {
      tooltip: {
        trigger: "item",
        formatter: "{b}: {d}%",
      },
      legend: {
        show: false,
      },
      series: [
        {
          name: "技能评分",
          type: "pie",
          radius: ["0%", "75%"],
          avoidLabelOverlap: false,
          label: {
            show: false,
          },
          labelLine: {
            show: false,
          },
          emphasis: {
            scale: true,
            scaleSize: 6,
          },
          data,
        },
      ],
    };
  }, [scores]);

  return (
    <div className="w-full" style={{ minHeight: 220 }}>
      <EChart option={option} height={220} />
    </div>
  );
}
