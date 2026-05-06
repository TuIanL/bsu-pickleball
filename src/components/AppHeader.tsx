import type { LucideIcon } from "lucide-react";
import { Activity, Camera } from "lucide-react";
import { productCopy } from "../data/productCopy";

interface AppHeaderProps {
  sections: ReadonlyArray<{
    id: string;
    label: string;
    icon: LucideIcon;
  }>;
  onNavigate: (id: string) => void;
}

export function AppHeader({ sections, onNavigate }: AppHeaderProps) {
  return (
    <header className="app-header">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          <Activity size={22} />
        </div>
        <div>
          <strong>{productCopy.brand}</strong>
          <span>{productCopy.tagline}</span>
        </div>
      </div>

      <nav className="section-nav" aria-label="页面导航">
        {sections.map(({ id, label, icon: Icon }) => (
          <button
            className="nav-button"
            key={id}
            onClick={() => onNavigate(id)}
            title={label}
            type="button"
          >
            <Icon size={17} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="capture-pill" aria-label="采集状态">
        <Camera size={16} aria-hidden="true" />
        <span>60fps 视觉采集</span>
      </div>
    </header>
  );
}
