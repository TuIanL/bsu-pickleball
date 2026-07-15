export function RailMeta({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex flex-col gap-1 rounded-2xl bg-[#F5FAF1] p-3">
      <span className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">{label}</span>
      <strong className="break-words text-sm font-semibold text-[#14241B]">{value}</strong>
    </li>
  );
}
