import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Target, Trash2 } from "lucide-react";
import { fetchAllocationTargetDrift, saveAllocationTargets } from "../api";
import { formatMoney, formatPercent } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiError";
import {
  draftErrors,
  draftFromDrift,
  draftTotal,
  fillFromCurrentWeights,
  newDraftRow,
  toPayload,
} from "../lib/allocationTargets";
import { AsyncSection, EmptyState } from "./ui";

const pct = (n) => formatPercent(n, { sign: false });
const TH = "text-left px-3 py-2 text-xs font-medium text-muted uppercase tracking-wider";
const TD = "px-3 py-2 text-sm";
const INPUT = "input text-sm py-1";

// Highlights large drift only; direction is in the sign. Neutral on purpose:
// a target is the user's plan, not advice (spec 2026-09-20 §4.2, §7).
function driftClass(drift) {
  if (drift == null) return "text-muted";
  return Math.abs(drift) >= 5 ? "text-[color:var(--chart-3)] font-medium" : "text-ink";
}

export default function AllocationTargets({ currency }) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState(null); // null = view mode
  const [newCount, setNewCount] = useState(0);
  const query = useQuery({
    queryKey: ["allocation-target-drift", currency],
    queryFn: () => fetchAllocationTargetDrift(currency),
  });
  const save = useMutation({
    mutationFn: (targets) => saveAllocationTargets(targets),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["allocation-target-drift"] });
      setRows(null);
    },
  });

  const drift = query.data;
  const targeted = (drift?.rows || []).filter((r) => r.target_pct != null);
  const startEditing = () => {
    save.reset();
    setRows(draftFromDrift(drift));
  };
  const update = (key, field, value) =>
    setRows((current) => current.map((r) => (r.key === key ? { ...r, [field]: value } : r)));
  const addRow = () => {
    const next = newCount + 1;
    setNewCount(next);
    setRows((current) => [...current, newDraftRow(next)]);
  };
  const removeRow = (key) =>
    setRows((current) =>
      current.flatMap((r) => (r.key !== key ? [r] : r.isNew ? [] : [{ ...r, target: "", group: "" }]))
    );

  return (
    <section aria-label="Target allocation" className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wider">Target allocation</h2>
        {rows == null && targeted.length > 0 && (
          <button type="button" className="btn-ghost text-sm" onClick={startEditing}>
            Edit targets
          </button>
        )}
      </div>

      <AsyncSection
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => query.refetch()}
        loading={<div className="animate-pulse h-24 text-muted text-sm">Loading targets...</div>}
      >
        {rows != null ? (
          <TargetEditor
            rows={rows}
            onChange={update}
            onAdd={addRow}
            onRemove={removeRow}
            onFill={() => setRows((current) => fillFromCurrentWeights(current))}
            onCancel={() => setRows(null)}
            onSave={() => save.mutate(toPayload(rows))}
            saving={save.isPending}
            saveError={save.error ? getApiErrorMessage(save.error, "We couldn't save your targets.") : null}
          />
        ) : targeted.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No target allocation yet"
            hint="Set a target weight for each holding to see how far the portfolio has drifted from your plan."
            action={(
              <button type="button" className="btn-primary text-sm" onClick={startEditing}>
                Set targets
              </button>
            )}
          />
        ) : (
          <TargetView drift={drift} currency={currency} />
        )}
      </AsyncSection>
    </section>
  );
}

function TargetView({ drift, currency }) {
  const [showUntargeted, setShowUntargeted] = useState(false);
  const targetedRows = drift.rows.filter((r) => r.target_pct != null);
  const untargetedRows = drift.rows.filter((r) => r.target_pct == null);
  const shownRows = showUntargeted ? [...targetedRows, ...untargetedRows] : targetedRows;
  const remaining = Math.max(0, 100 - drift.target_total_pct);
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">
        {pct(drift.target_total_pct)} of 100% assigned
        {drift.is_complete ? (
          " · complete"
        ) : (
          <span className="text-[color:var(--chart-3)]"> · {pct(remaining)} not assigned</span>
        )}
        {" · "}Weights use imported transactions at the latest quotes; cash is not included.
      </p>
      {drift.missing_price_tickers.length > 0 && (
        <p className="text-xs text-[color:var(--chart-3)]">
          No current price for {drift.missing_price_tickers.join(", ")}. These holdings are valued at 0,
          so their drift may be off.
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-surface-border">
            <tr>
              <th className={TH}>Ticker</th>
              <th className={`${TH} hidden sm:table-cell`}>Group</th>
              <th className={`${TH} text-right`}>Target</th>
              <th className={`${TH} text-right`}>Current</th>
              <th className={`${TH} text-right`} title="Current weight minus target weight">Drift</th>
              <th className={`${TH} text-right`} title="Value change that would bring this holding to its target">
                Value to target
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {shownRows.map((r) => (
              <tr key={r.ticker}>
                <td className={`${TD} font-mono font-bold`}>
                  {r.ticker}
                  {!r.held && <span className="ml-1.5 financial-meta font-normal text-muted">not held</span>}
                </td>
                <td className={`${TD} text-muted hidden sm:table-cell`}>{r.group ?? "—"}</td>
                <td className={`${TD} text-right tabular-nums`}>
                  {r.target_pct == null ? <span className="text-xs text-muted">No target</span> : pct(r.target_pct)}
                </td>
                <td className={`${TD} text-right tabular-nums`}>{pct(r.current_pct)}</td>
                <td className={`${TD} text-right tabular-nums ${driftClass(r.drift_pct)}`}>
                  {r.drift_pct == null ? "—" : formatPercent(r.drift_pct)}
                </td>
                <td className={`${TD} text-right tabular-nums`}>
                  {r.value_to_target == null ? "—" : formatMoney(r.value_to_target, currency)}
                </td>
              </tr>
            ))}
            {untargetedRows.length > 0 && (
              <tr>
                <td colSpan={6} className={TD}>
                  <button
                    type="button"
                    className="min-h-11 text-brand hover:underline md:min-h-0"
                    aria-expanded={showUntargeted}
                    onClick={() => setShowUntargeted((v) => !v)}
                  >
                    {untargetedRows.length} {untargetedRows.length === 1 ? "holding" : "holdings"} without a target
                  </button>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {drift.groups.length > 0 && (
        <ul aria-label="Target groups" className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
          {drift.groups.map((g) => (
            <li key={g.group}>
              <span className="text-ink font-medium">{g.group}</span>: target {pct(g.target_pct)} · current{" "}
              {pct(g.current_pct)} · drift {formatPercent(g.drift_pct)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TargetEditor({ rows, onChange, onAdd, onRemove, onFill, onCancel, onSave, saving, saveError }) {
  const errors = draftErrors(rows);
  const total = draftTotal(rows);
  let newIndex = 0;
  return (
    <div className="space-y-3">
      {/* relative: keeps the absolutely positioned sr-only header inside the scroller */}
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[30rem]">
          <thead className="border-b border-surface-border">
            <tr>
              <th className={TH}>Ticker</th>
              <th className={`${TH} text-right`}>Target %</th>
              <th className={`${TH} text-right`}>Current</th>
              <th className={TH}>Group</th>
              <th className={TH}><span className="sr-only">Remove</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {rows.map((r) => {
              const label = r.isNew ? `new row ${++newIndex}` : r.ticker;
              return (
                <tr key={r.key}>
                  <td className={`${TD} font-mono font-bold`}>
                    {r.isNew ? (
                      <input
                        className={`${INPUT} w-24`}
                        aria-label={`Ticker for ${label}`}
                        value={r.ticker}
                        maxLength={32}
                        onChange={(e) => onChange(r.key, "ticker", e.target.value)}
                      />
                    ) : (
                      r.ticker
                    )}
                  </td>
                  <td className={`${TD} text-right`}>
                    <input
                      className={`${INPUT} text-right w-20`}
                      aria-label={`Target for ${label}`}
                      inputMode="decimal"
                      value={r.target}
                      placeholder="—"
                      onChange={(e) => onChange(r.key, "target", e.target.value)}
                    />
                  </td>
                  <td className={`${TD} text-right tabular-nums text-muted`}>{pct(r.currentPct)}</td>
                  <td className={TD}>
                    <input
                      className={`${INPUT} w-32`}
                      aria-label={`Group for ${label}`}
                      value={r.group}
                      maxLength={40}
                      placeholder="Optional"
                      onChange={(e) => onChange(r.key, "group", e.target.value)}
                    />
                  </td>
                  <td className={TD}>
                    <button
                      type="button"
                      className="btn-ghost p-1"
                      aria-label={`Remove target for ${label}`}
                      onClick={() => onRemove(r.key)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-ghost text-sm flex items-center gap-1" onClick={onAdd}>
          <Plus size={14} /> Add ticker
        </button>
        <button type="button" className="btn-ghost text-sm" onClick={onFill}>
          Use current weights
        </button>
      </div>

      <p className="text-xs text-muted">
        Total {pct(total)} of 100%. Leave a target empty for “no target”. You can save before reaching 100%.
      </p>
      {errors.length > 0 && (
        <ul role="alert" className="text-xs text-loss space-y-1">
          {errors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      )}
      {saveError && <p role="alert" className="text-xs text-loss">{saveError}</p>}

      <div className="flex gap-2 justify-end">
        <button type="button" className="btn-ghost text-sm" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
        <button
          type="button"
          className="btn-primary text-sm"
          onClick={onSave}
          disabled={saving || errors.length > 0}
        >
          {saving ? "Saving..." : "Save targets"}
        </button>
      </div>
    </div>
  );
}
