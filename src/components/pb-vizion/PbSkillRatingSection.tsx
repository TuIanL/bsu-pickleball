import { useMemo } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import type { PbDimensionKey } from "../../types/pbReport";
import {
  PB_DIMENSION_META,
  PB_DIMENSION_ORDER,
} from "../../types/pbReport";
import type { SkillRating } from "../../types/report";
import PbSkillPieChart from "./PbSkillPieChart";

const DIM_COLORS: Record<PbDimensionKey, string> = {
  kitchen: "#A855F7",
  ballctrl: "#3B82F6",
  defense: "#06B6D4",
  offense: "#F97316",
  courtiq: "#EAB308",
  targeting: "#EC4899",
};

const DIM_BG: Record<PbDimensionKey, string> = {
  kitchen: "#FAF5FF",
  ballctrl: "#EFF6FF",
  defense: "#ECFEFF",
  offense: "#FFF7ED",
  courtiq: "#FEFCE8",
  targeting: "#FDF2F8",
};

const LABEL_TO_DIM: Record<string, PbDimensionKey> = {
  "Kitchen Game": "kitchen",
  "网前对抗": "kitchen",
  "Ball Control": "ballctrl",
  "控球能力": "ballctrl",
  Defense: "defense",
  防守: "defense",
  Offense: "offense",
  进攻: "offense",
  "Court IQ": "courtiq",
  "球场智商": "courtiq",
  Targeting: "targeting",
  "落点精准": "targeting",
};

export default function PbSkillRatingSection() {
  const { report } = usePbReport();

  const skillRatings = useMemo<SkillRating[]>(() => {
    return report?.skillRatings ?? [];
  }, [report?.skillRatings]);

  const scoresRecord = useMemo<Record<PbDimensionKey, number>>(() => {
    const result: Record<PbDimensionKey, number> = {
      kitchen: 0.5,
      ballctrl: 0.5,
      defense: 0.5,
      offense: 0.5,
      courtiq: 0.5,
      targeting: 0.5,
    };

    if (!skillRatings || skillRatings.length === 0) return result;

    const mappedScores = new Map<PbDimensionKey, number>();

    for (const rating of skillRatings) {
      const dim =
        LABEL_TO_DIM[rating.label] ??
        (Object.keys(LABEL_TO_DIM).find((k) =>
          rating.label?.includes(k)
        )
          ? LABEL_TO_DIM[
              Object.keys(LABEL_TO_DIM).find((k) =>
                rating.label?.includes(k)
              ) as string
            ]
          : undefined);

      if (dim) {
        const raw = Math.max(0, Math.min(10, rating.score ?? 5));
        mappedScores.set(dim, raw / 10);
      }
    }

    let idx = 0;
    for (const key of PB_DIMENSION_ORDER) {
      if (mappedScores.has(key)) {
        result[key] = mappedScores.get(key) as number;
      } else if (skillRatings[idx]) {
        const raw = Math.max(0, Math.min(10, skillRatings[idx].score ?? 5));
        result[key] = raw / 10;
        idx++;
      }
    }

    return result;
  }, [skillRatings]);

  const scaledScores = useMemo<Record<PbDimensionKey, number>>(() => {
    const result = {} as Record<PbDimensionKey, number>;
    for (const key of PB_DIMENSION_ORDER) {
      const raw01 = scoresRecord[key] ?? 0.5;
      result[key] = Math.round((raw01 * 3.5 + 2) * 100) / 100;
    }
    return result;
  }, [scoresRecord]);

  const compositeScore = useMemo(() => {
    const values = PB_DIMENSION_ORDER.map((k) => scaledScores[k]);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    return Math.round(avg * 100) / 100;
  }, [scaledScores]);

  return (
    <div className="pb-card p-6">
      <div className="mb-6">
        <p className="text-xs font-bold uppercase tracking-wider text-gray-500">
          单场比赛
        </p>
        <h2 className="mt-1 text-2xl font-black text-[var(--pb-text-primary,#111827)]">
          技能评分
        </h2>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 items-center mb-8">
        <div className="text-center shrink-0">
          <div
            className="text-6xl font-black"
            style={{
              color: "var(--pb-text-primary,#111827)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {compositeScore.toFixed(2)}
          </div>
          <div className="mt-2 text-sm text-[var(--pb-text-secondary,#6b7280)] font-medium">
            综合评分
          </div>
        </div>

        <div className="w-full max-w-[280px] shrink-0">
          <PbSkillPieChart scores={scoresRecord} />
        </div>

        <div className="pb-long-term-compare flex-1 hidden">
          <div className="h-[220px] w-full rounded-xl border border-dashed border-gray-200 flex items-center justify-center text-sm text-gray-400">
            长期对比（预留）
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {PB_DIMENSION_ORDER.map((key) => {
          const meta = PB_DIMENSION_META[key];
          const color = DIM_COLORS[key];
          const bg = DIM_BG[key];
          const score = scaledScores[key];
          return (
            <div
              key={key}
              className="rounded-xl p-4 border"
              style={{
                backgroundColor: bg,
                borderColor: color,
              }}
            >
              <div className="flex items-baseline justify-between mb-2 gap-2 flex-wrap">
                <div>
                  <span
                    className="font-bold text-sm"
                    style={{ color }}
                  >
                    {meta.label}
                  </span>
                </div>
              </div>
              <div
                className="text-3xl font-black"
                style={{
                  color,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {score.toFixed(2)}
              </div>
              <div
                className="pb-dim-delta text-sm font-semibold mt-2 hidden"
                style={{ color: "#16A34A" }}
              >
                +0.01
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
