import type { QuickEventDef } from "../../services/timelineQuickEvents";

interface Props {
  events: QuickEventDef[];
  isPending?: (type: string) => boolean;
  onAction: (event: QuickEventDef) => void;
}

const groupLabels: Record<string, string> = {
  hierarchy: "层级事件",
  match: "比赛状态",
  auxiliary: "辅助事件",
};

const colorMap: Record<string, { bg: string; border: string; text: string }> = {
  start_set: { bg: "#FFF7ED", border: "#FDBA74", text: "#EA580C" },
  end_set: { bg: "#FFF7ED", border: "#FDBA74", text: "#EA580C" },
  start_game: { bg: "#EEF3FF", border: "#A9C5FB", text: "#2D6AE5" },
  end_game: { bg: "#EEF3FF", border: "#A9C5FB", text: "#2D6AE5" },
  start_next_rally: { bg: "#EAF7EE", border: "#A3D9B4", text: "#3BAA62" },
  end_rally: { bg: "#F2F4F7", border: "#D0D5DD", text: "#475467" },
  start_timeout: { bg: "#FFF7ED", border: "#FDBA74", text: "#EA580C" },
  change_side: { bg: "#F3EEFF", border: "#C4B0F4", text: "#8B5CF6" },
  add_note: { bg: "#EEF3FF", border: "#A9C5FB", text: "#4F7DF3" },
  undo: { bg: "#FDEBEC", border: "#F5A3A8", text: "#E5484D" },
  rally_result_a: { bg: "#EAF7EE", border: "#A3D9B4", text: "#3BAA62" },
  rally_result_b: { bg: "#EEF3FF", border: "#A9C5FB", text: "#4F7DF3" },
  rally_replay: { bg: "#F2F4F7", border: "#D0D5DD", text: "#475467" },
};

export function EventActionToolbar({ events, isPending, onAction }: Props) {
  const grouped: Record<string, QuickEventDef[]> = {};
  for (const ev of events) {
    const g = ev.group || "auxiliary";
    if (!grouped[g]) grouped[g] = [];
    grouped[g].push(ev);
  }

  return (
    <div className="space-y-3">
      {Object.entries(grouped).map(([groupKey, groupEvents]) => (
        <div key={groupKey}>
          <p className="text-xs font-medium mb-1.5" style={{ color: "var(--capture-text-muted)" }}>{groupLabels[groupKey]}</p>
          <div className="flex flex-wrap gap-2">
            {groupEvents.map(event => {
              const pending = isPending?.(event.type) ?? false;
              const colors = colorMap[event.type] ?? { bg: "#F2F4F7", border: "#D0D5DD", text: "#475467" };
              const isUndo = event.type === "undo";
              return (
                <button
                  key={event.type}
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${pending ? "opacity-50 cursor-wait" : ""} ${isUndo ? "ml-2" : ""}`}
                  style={{ background: colors.bg, border: `1px solid ${colors.border}`, color: colors.text, height: 36 }}
                  onClick={() => onAction(event)}
                  disabled={pending}
                  type="button"
                  aria-label={event.label}
                >
                  {event.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
