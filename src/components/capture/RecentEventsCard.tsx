interface RecentEvent {
  id: string;
  label: string;
  timestamp: string;
  type: string;
}

interface Props {
  events: RecentEvent[];
  onViewAll?: () => void;
}

const typeIcon: Record<string, string> = {
  start_set: "●", end_set: "○",
  start_game: "●", end_game: "○",
  start_next_rally: "●", end_rally: "○",
  add_note: "◆",
  side_change: "⇄",
  start_timeout: "▣",
};

const typeColor: Record<string, string> = {
  start_set: "#F08A3C", end_set: "#F08A3C",
  start_game: "#4F7DF3", end_game: "#4F7DF3",
  start_next_rally: "#3BAA62", end_rally: "#3BAA62",
  add_note: "#8B5CF6",
  side_change: "#EC6D9E",
  start_timeout: "#F59E42",
};

export function RecentEventsCard({ events, onViewAll }: Props) {
  const visible = events.slice(-5);
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)", boxShadow: "var(--capture-shadow-card)" }}>
      <h3 className="text-sm font-bold mb-3" style={{ color: "var(--capture-text-primary)" }}>最近事件</h3>
      {visible.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--capture-text-muted)" }}>暂无事件</p>
      ) : (
        <div className="space-y-2">
          {visible.map(evt => (
            <div key={evt.id} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5">
                <span style={{ color: typeColor[evt.type] || "var(--capture-text-muted)" }}>
                  {typeIcon[evt.type] || "●"}
                </span>
                <span style={{ color: "var(--capture-text-primary)" }}>{evt.label}</span>
              </span>
              <span style={{ color: "var(--capture-text-muted)" }}>{evt.timestamp}</span>
            </div>
          ))}
        </div>
      )}
      {events.length > 5 && onViewAll && (
        <button className="mt-2 text-xs font-medium" style={{ color: "var(--capture-brand-primary)" }} onClick={onViewAll} type="button">
          查看全部事件
        </button>
      )}
    </div>
  );
}
