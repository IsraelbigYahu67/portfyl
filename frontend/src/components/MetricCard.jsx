import { Info } from "lucide-react";

function InfoIcon({ info }) {
  if (!info) return null;
  return (
    <span className="relative group inline-flex items-center">
      <button
        type="button"
        aria-label={`What is ${info.title}?`}
        className="inline-flex text-slate-400 hover:text-slate-600 cursor-help transition-colors"
      >
        <Info size={12} />
      </button>
      <span
        className="hidden group-hover:block group-focus-within:block absolute left-1/2 -translate-x-1/2 top-5 z-30 w-72
                   bg-white border border-surface-border rounded-lg px-3 py-2 shadow-lg
                   text-[11px] leading-relaxed text-slate-600 normal-case tracking-normal font-normal"
      >
        <span className="block font-semibold text-slate-800 mb-1">{info.title}</span>
        <span className="block text-slate-500">{info.what}</span>
        {info.formula && (
          <span className="block mt-1.5 pt-1.5 border-t border-surface-border font-mono text-[10px] text-brand">
            {info.formula}
          </span>
        )}
        {info.note && (
          <span className="block mt-1 text-[10px] text-slate-400 italic">{info.note}</span>
        )}
      </span>
    </span>
  );
}

export default function MetricCard({ label, value, sub, positive, negative, loading, info }) {
  const subColor = positive ? "text-emerald-600" : negative ? "text-red-600" : "text-slate-500";

  return (
    <div className="card flex flex-col gap-1 min-w-0">
      <span className="text-[11px] text-slate-500 uppercase tracking-wider font-medium flex items-center gap-1.5">
        {label}
        <InfoIcon info={info} />
      </span>
      {loading ? (
        <div className="h-8 w-28 bg-slate-100 rounded animate-pulse mt-1" />
      ) : (
        <span className="text-[22px] font-bold tabular-nums truncate tracking-tight">{value}</span>
      )}
      {sub && !loading && <span className={`text-[13px] font-semibold ${subColor}`}>{sub}</span>}
    </div>
  );
}

export { InfoIcon };
