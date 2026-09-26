import type { ShotLanding } from "../../../types/shotLandings";

export function LandingCourtMap({ landings, selectedId, onSelect }: { landings: ShotLanding[]; selectedId?: string; onSelect: (id: string) => void }) {
  const points = landings.filter((item) => Number.isFinite(item.target_x_ft) && Number.isFinite(item.target_y_ft));
  return (
    <svg aria-label="连续落点球场图" className="h-auto w-full rounded-xl bg-[#173b2a]" viewBox="-2 -2 24 28">
      <rect x="0" y="0" width="20" height="22" fill="#34865d" stroke="white" strokeWidth=".25" />
      <line x1="0" y1="7" x2="20" y2="7" stroke="white" strokeWidth=".2" />
      <line x1="10" y1="0" x2="10" y2="7" stroke="white" strokeWidth=".2" />
      <line x1="0" y1="0" x2="20" y2="0" stroke="#e8faf0" strokeWidth=".45" />
      {points.map((item) => (
        <circle key={item.landing_id} cx={item.target_x_ft!} cy={item.target_y_ft!}
          r={selectedId === item.shot_id ? .62 : .38}
          fill={item.court_location === "outside_court" ? "#fb923c" : item.target_relation === "target_half" ? "#fef08a" : "#93c5fd"}
          stroke={selectedId === item.shot_id ? "white" : "#173b2a"} strokeWidth=".18"
          onClick={() => onSelect(item.shot_id)} className="cursor-pointer" />
      ))}
    </svg>
  );
}
