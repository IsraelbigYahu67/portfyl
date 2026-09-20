import SpotlightCard from "../reactbits/SpotlightCard";
import { DeltaPill } from "./DeltaPill";
import { InfoIcon } from "../MetricCard";
import { useCountUp } from "../../hooks/useCountUp";

const SUB_TONE = { gain: "text-gain", loss: "text-loss", muted: "text-muted" };

function KpiValue({ value, format, countUp }) {
  const isNumber = countUp && typeof value === "number" && Number.isFinite(value);
  const animated = useCountUp(isNumber ? value : 0, { enabled: isNumber });
  if (!isNumber) return value ?? null;
  return format(animated);
}

export default function KpiBox({
  icon: Icon,
  label,
  value,
  format = (v) => String(v),
  delta = null,
  sub = null,
  subTone = "muted",
  info = null,
  loading = false,
  size = "md",
  className = "",
  countUp = false,
}) {
  const dense = size === "sm";
  return (
    <SpotlightCard
      className={`card !bg-surface-card-elevated flex flex-col gap-1 min-w-0 ${dense ? "!p-3" : ""} ${className}`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="eyebrow flex items-center gap-1.5">
          {label}
          <InfoIcon info={info} />
        </span>
        {Icon && (
          <span className="grid place-items-center w-7 h-7 rounded-lg bg-brand/10 text-brand shrink-0">
            <Icon size={14} />
          </span>
        )}
      </div>
      {loading ? (
        <div className="h-7 w-24 bg-surface-hover rounded animate-pulse mt-1" />
      ) : (
        <span className={`financial-data font-display font-bold tracking-tight ${dense ? "text-lg" : "text-3xl"}`}>
          <KpiValue value={value} format={format} countUp={countUp} />
        </span>
      )}
      {delta && !loading && (
        <DeltaPill value={delta.value} pct={delta.pct} currency={delta.currency} size="sm" />
      )}
      {sub && !loading && (
        <span className={`text-sm font-semibold ${SUB_TONE[subTone] || SUB_TONE.muted}`}>{sub}</span>
      )}
    </SpotlightCard>
  );
}
