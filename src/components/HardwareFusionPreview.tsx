import type { CSSProperties } from "react";
import { Cpu, Gauge, ShieldCheck, Zap } from "lucide-react";
import { productCopy } from "../data/productCopy";
import type { HardwarePreview } from "../types/report";

interface HardwareFusionPreviewProps {
  preview: HardwarePreview;
}

export function HardwareFusionPreview({ preview }: HardwareFusionPreviewProps) {
  return (
    <section className="section-band hardware-band" id="hardware">
      <div className="section-inner hardware-layout">
        <div className="hardware-copy">
          <div className="eyebrow">
            <Cpu size={16} aria-hidden="true" />
            <span>{productCopy.hardware.badge}</span>
          </div>
          <h2>{preview.phaseLabel}</h2>
          <p>{preview.disclaimer}</p>
        </div>

        <div className="hardware-metrics" aria-label="模拟传感指标">
          {preview.metrics.map((metric) => (
            <article className="hardware-metric" key={metric.id}>
              <Gauge size={18} aria-hidden="true" />
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <p>{metric.detail}</p>
            </article>
          ))}
        </div>

        <div className="sweet-zone-panel">
          <div className="panel-heading compact">
            <div>
              <span className="panel-kicker">TENG 阵列</span>
              <h3>3x3 甜区触点分布</h3>
            </div>
            <span className="simulated-chip">
              <ShieldCheck size={15} aria-hidden="true" />
              二期预览
            </span>
          </div>
          <div className="paddle-face" aria-label="甜区九宫格">
            {preview.sweetZone.map((cell) => (
              <span
                className={cell.id === preview.highlightedCellId ? "zone-cell active" : "zone-cell"}
                key={cell.id}
                style={{ "--zone": cell.intensity } as CSSProperties}
              />
            ))}
          </div>
        </div>

        <div className="fusion-list" aria-label="视觉与体感融合说明">
          {preview.fusionPoints.map((point) => (
            <article className="fusion-item" key={point.insight}>
              <div className="fusion-pair">
                <span>视觉</span>
                <strong>{point.visual}</strong>
              </div>
              <Zap size={18} aria-hidden="true" />
              <div className="fusion-pair">
                <span>球拍</span>
                <strong>{point.sensor}</strong>
              </div>
              <p>{point.insight}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
