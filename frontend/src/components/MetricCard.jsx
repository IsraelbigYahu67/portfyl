import { Info } from "lucide-react";
import SpotlightCard from "./reactbits/SpotlightCard";
import { useCountUp } from "../hooks/useCountUp";

function InfoIcon({ info }) {
  if (!info) return null;
  return (
    <span className="relative group inline-flex items-center">
      <button
        type="button"
        aria-label={`What is ${info.title}?`}
        className="inline-flex text-muted hover:text-ink cursor-help transition-colors"
      >
        <Info size={12} />
      </button>
      <span
        className="hidden group-hover:block group-focus-within:block absolute left-1/2 -translate-x-1/2 top-5 z-30 w-72
                   bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 shadow-[var(--shadow-ambient)]
                   text-[11px] leading-relaxed text-muted normal-case tracking-normal font-normal"
      >
        <span className="block font-semibold text-ink mb-1">{info.title}</span>
        <span className="block text-muted">{info.what}</span>
        {info.formula && (
          <span className="block mt-1.5 pt-1.5 border-t border-hairline font-mono text-[10px] text-brand">
            {info.formula}
          </span>
        )}
        {info.note && (
          <span className="block mt-1 text-[10px] text-muted italic">{info.note}</span>
        )}
      </span>
    </span>
  );
}

// `value` is normally a pre-formatted string (every current caller already
// formats via lib/format.js before passing it in). Passing a raw number
// instead opts into a count-up animation -- additive, backward compatible.
function MetricValue({ value }) {
  const isNumber = typeof value === "number" && Number.isFinite(value);
  const animated = useCountUp(isNumber ? value : 0, { enabled: isNumber });
  return isNumber ? animated.toLocaleString("en-US", { maximumFractionDigits: 0 }) : value;
}

export default function MetricCard({ icon: Icon, label, value, sub, positive, negative, loading, info }) {
  const subColor = positive ? "text-gain" : negative ? "text-loss" : "text-muted";

  return (
    <SpotlightCard className="card !bg-surface-card-elevated relative flex flex-col gap-1.5 min-w-0">
      {Icon && (
        <span className="absolute top-4 right-4 grid place-items-center w-7 h-7 rounded-lg bg-brand/10 text-brand">
          <Icon size={14} />
        </span>
      )}
      <span className="eyebrow flex items-center gap-1.5">
        {label}
        <InfoIcon info={info} />
      </span>
      {loading ? (
        <div className="h-8 w-28 bg-surface-hover rounded animate-pulse mt-1" />
      ) : (
        <span className="text-2xl font-display font-bold tabular-nums truncate tracking-tight text-ink">
          <MetricValue value={value} />
        </span>
      )}
      {sub && !loading && <span className={`text-[13px] font-semibold tabular-nums ${subColor}`}>{sub}</span>}
    </SpotlightCard>
  );
}

export { InfoIcon };
