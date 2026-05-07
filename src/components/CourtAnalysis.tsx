import { MapPinned, Route, Target } from "lucide-react";
import { useMemo, useState } from "react";
import { productCopy } from "../data/productCopy";
import type { CourtMode, ReportSession } from "../types/report";

interface CourtAnalysisProps {
  session: ReportSession;
}

const modeOptions: Array<{
  id: CourtMode;
  icon: typeof Target;
}> = [
  { id: "heat", icon: Target },
  { id: "routes", icon: Route },
  { id: "movement", icon: MapPinned },
];

export function CourtAnalysis({ session }: CourtAnalysisProps) {
  const [mode, setMode] = useState<CourtMode>("heat");
  const movementPolyline = useMemo(
    () => session.movementPath.map((point) => `${point.x},${point.y}`).join(" "),
    [session.movementPath]
  );

  return (
    <section className="court-panel" aria-label="球场可视化">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">球场地图</span>
          <h2>球路、落点与步法轨迹</h2>
        </div>
        <div className="segmented-control" role="tablist" aria-label="球场视图">
          {modeOptions.map(({ id, icon: Icon }) => (
            <button
              aria-selected={mode === id}
              className={mode === id ? "active" : ""}
              key={id}
              onClick={() => setMode(id)}
              title={productCopy.courtModes[id]}
              type="button"
            >
              <Icon size={16} aria-hidden="true" />
              <span>{productCopy.courtModes[id]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="court-layout">
        <div className="court-stage">
          <svg className="court-svg" viewBox="0 0 100 100" role="img" aria-label="匹克球场分析图">
            <defs>
              <marker
                id="routeArrow"
                markerHeight="7"
                markerWidth="7"
                orient="auto"
                refX="6"
                refY="3.5"
              >
                <path d="M0,0 L7,3.5 L0,7 Z" fill="currentColor" />
              </marker>
            </defs>
            <rect className="court-base" height="88" rx="3" width="62" x="19" y="6" />
            <line className="court-line" x1="50" x2="50" y1="6" y2="94" />
            <line className="court-line" x1="19" x2="81" y1="50" y2="50" />
            <line className="court-line kitchen" x1="19" x2="81" y1="39" y2="39" />
            <line className="court-line kitchen" x1="19" x2="81" y1="61" y2="61" />
            <line className="court-line" x1="19" x2="81" y1="6" y2="6" />
            <line className="court-line" x1="19" x2="81" y1="94" y2="94" />

            <g className={mode === "heat" ? "viz-layer active" : "viz-layer"}>
              {session.landingPoints.map((point) => (
                <g key={point.id}>
                  <circle
                    className="heat-halo"
                    cx={point.x}
                    cy={point.y}
                    r={7 + point.intensity * 8}
                  />
                  <circle
                    className="heat-dot"
                    cx={point.x}
                    cy={point.y}
                    r={2.7 + point.intensity * 2}
                  />
                </g>
              ))}
            </g>

            <g className={mode === "routes" ? "viz-layer active route-layer" : "viz-layer route-layer"}>
              {session.routes.map((route) => (
                <g key={route.id}>
                  <line
                    className="route-line"
                    markerEnd="url(#routeArrow)"
                    x1={route.from.x}
                    x2={route.to.x}
                    y1={route.from.y}
                    y2={route.to.y}
                  />
                  <circle className="route-start" cx={route.from.x} cy={route.from.y} r="2.3" />
                  <circle className="route-end" cx={route.to.x} cy={route.to.y} r="3" />
                </g>
              ))}
            </g>

            <g className={mode === "movement" ? "viz-layer active movement-layer" : "viz-layer movement-layer"}>
              <polyline className="movement-line" points={movementPolyline} />
              {session.movementPath.map((point, index) => (
                <circle
                  className={index === session.movementPath.length - 1 ? "movement-dot current" : "movement-dot"}
                  cx={point.x}
                  cy={point.y}
                  key={`${point.x}-${point.y}-${index}`}
                  r={index === session.movementPath.length - 1 ? 3.2 : 2.2}
                />
              ))}
            </g>
          </svg>
        </div>

        <div className="court-insights">
          {session.routes.map((route) => (
            <article className="route-summary" key={route.id}>
              <span>{route.result}</span>
              <strong>{route.label}</strong>
              <p>
                {route.from.label} → {route.to.label}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
