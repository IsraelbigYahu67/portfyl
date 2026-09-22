import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Percent, Plus, RefreshCw, TrendingUp, Trash2, Wallet } from "lucide-react";
import { Card, SectionHeader, SkeletonRows, EmptyState, ErrorState } from "../components/ui";
import MetricCard from "../components/MetricCard";
import { formatDateTime, formatLongDate, formatMoney } from "../lib/format";
import CashBalanceChart from "../components/CashBalanceChart";
import {
  fetchCash,
  createCash,
  deleteCash,
  fetchCashBalance,
  fetchCashHistory,
  fetchCashReconciliation,
  fetchInterestRates,
  saveInterestRates,
} from "../api";
import { useCurrency } from "../App";
import { useT212Sync } from "../hooks/useT212Sync";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";

// Types offered for manual entry; the ledger can additionally contain imported
// rows (card debits, cashback, FX conversion legs) from a Trading 212 CSV.
const CASH_TYPES = ["deposit", "withdrawal", "fee", "interest"];

const TYPE_LABEL = {
  deposit: "Deposit",
  withdrawal: "Withdrawal",
  fee: "Fee",
  interest: "Interest",
  card_debit: "Card",
  cashback: "Cashback",
  fx_in: "FX in",
  fx_out: "FX out",
};

// Direction of each type's cash impact — mirrors backend signed_cash.
const CASH_IN = new Set(["deposit", "interest", "cashback", "fx_in"]);

function TypeBadge({ type }) {
  const inflow = CASH_IN.has(type);
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
        inflow ? "bg-gain/10 text-gain" : "bg-loss/10 text-loss"
      }`}
    >
      {TYPE_LABEL[type] || type}
    </span>
  );
}

// Broker snapshot vs. recorded ledger history are shown side by side, never
// merged — a mismatch must stay visible instead of one source silently
// winning. See docs/superpowers/specs/2026-09-20-portfyl-snowball-gap-
// roadmap-design.md section 4.1.
const STATUS_COPY = {
  matched: {
    icon: CheckCircle2,
    tone: "text-gain",
    badge: "bg-gain/10 text-gain",
    label: "Matches your recorded history",
  },
  different: {
    icon: AlertTriangle,
    tone: "text-loss",
    badge: "bg-loss/10 text-loss",
    label: "Differs from your recorded history",
  },
};

function CashReconciliationCard({ data, isLoading, isError, onRetry, connected, currency, onSync, syncing }) {
  return (
    <Card>
      <SectionHeader icon={Wallet}>Current Trading 212 balance</SectionHeader>
      {isLoading ? (
        <SkeletonRows rows={2} cols={2} />
      ) : isError ? (
        <ErrorState message="Couldn't load your broker balance." onRetry={onRetry} />
      ) : !data || data.status === "unavailable" ? (
        <EmptyState
          icon={Wallet}
          title={connected ? "No Trading 212 balance synced yet" : "No Trading 212 connected"}
          hint={
            connected
              ? "Sync your Trading 212 connection to see your current broker balance here."
              : "Connect Trading 212 in Settings to see your current broker balance alongside your recorded cash history."
          }
          action={
            connected ? (
              <button type="button" className="btn-primary" onClick={onSync} disabled={syncing}>
                {syncing ? "Syncing…" : "Sync now"}
              </button>
            ) : (
              <Link className="btn-primary" to="/settings?section=connections">Connect Trading 212</Link>
            )
          }
        />
      ) : data.status === "no_ledger_history" ? (
        <div className="space-y-3">
          <div>
            <p className="text-xs text-muted">Trading 212 (broker snapshot)</p>
            <p className="text-2xl font-display font-bold tabular-nums text-ink">
              {formatMoney(data.broker_amount, currency)}
            </p>
            {data.broker_as_of && (
              <p className="text-xs text-muted mt-1">
                As of {formatLongDate(data.broker_as_of)}
                {data.broker_updated_at && ` · synced ${formatDateTime(data.broker_updated_at)}`}
              </p>
            )}
          </div>
          <p className="text-xs text-muted">
            No recorded cash history yet. Add deposits and withdrawals, or import your
            transaction history, so Portfyl can compare them against this broker balance.
          </p>
          <Link className="btn-ghost" to="/import">Import transactions</Link>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs text-muted">Trading 212 (broker snapshot)</p>
              <p className="text-2xl font-display font-bold tabular-nums text-ink">
                {formatMoney(data.broker_amount, currency)}
              </p>
              {data.broker_as_of && (
                <p className="text-xs text-muted mt-1">
                  As of {formatLongDate(data.broker_as_of)}
                  {data.broker_updated_at && ` · synced ${formatDateTime(data.broker_updated_at)}`}
                </p>
              )}
            </div>
            <div>
              <p className="text-xs text-muted">Recorded ledger history</p>
              <p className="text-2xl font-display font-bold tabular-nums text-ink">
                {formatMoney(data.ledger_amount, currency)}
              </p>
            </div>
          </div>

          <div className={`mt-4 flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-sm ${(STATUS_COPY[data.status] ?? STATUS_COPY.different).badge}`}>
            {(() => {
              const StatusIcon = (STATUS_COPY[data.status] ?? STATUS_COPY.different).icon;
              return <StatusIcon size={16} className={(STATUS_COPY[data.status] ?? STATUS_COPY.different).tone} />;
            })()}
            <span className="font-medium">{(STATUS_COPY[data.status] ?? STATUS_COPY.different).label}</span>
            {data.status === "different" && (
              <span className="text-xs opacity-90">({formatMoney(data.difference, currency)} difference)</span>
            )}
            {data.status === "matched" && (
              <span className="text-xs opacity-90">(within {formatMoney(data.tolerance, currency)})</span>
            )}
          </div>

          {data.status === "different" && (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-muted">
                A difference usually means your recorded history is incomplete, not that either number is
                wrong. Import missing transactions or sync your broker connection — Portfyl never adjusts
                the ledger automatically to force a match.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary flex items-center gap-1.5"
                  onClick={onSync}
                  disabled={syncing}
                >
                  <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
                  {syncing ? "Syncing…" : "Sync now"}
                </button>
                <Link className="btn-ghost" to="/import">Import transactions</Link>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export default function Cash() {
  // useCurrency() reads CurrencyContext (provided by App's CurrencyProvider);
  // outside that provider (e.g. in tests) the context is null, so fall back to USD.
  const currency = useCurrency()?.currency || "USD";
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();

  const rows = useQuery({ queryKey: ["cash"], queryFn: fetchCash });
  const balance = useQuery({
    queryKey: ["cash-balance", currency],
    queryFn: () => fetchCashBalance(currency),
  });
  const history = useQuery({
    queryKey: ["cash-history", currency],
    queryFn: () => fetchCashHistory(currency),
  });
  const reconciliation = useQuery({
    queryKey: ["cash-reconciliation", currency],
    queryFn: () => fetchCashReconciliation(currency),
  });
  const { status: t212Status, sync } = useT212Sync({ includeHistory: false });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cash"] });
    qc.invalidateQueries({ queryKey: ["cash-balance"] });
    qc.invalidateQueries({ queryKey: ["cash-history"] });
    qc.invalidateQueries({ queryKey: ["cash-reconciliation"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
  };

  const add = useMutation({ mutationFn: createCash, onSuccess: invalidate });
  const del = useMutation({
    mutationFn: deleteCash,
    onSuccess: () => {
      invalidate();
      toast.success("Cash entry deleted");
    },
    onError: (err) =>
      toast.error(err?.response?.data?.detail || "Failed to delete cash entry"),
  });
  const handleSync = () => sync.mutate(undefined, {
    onSuccess: (result) => {
      if (result.cash_error) toast.error("Trading 212 balance could not be refreshed.");
      else toast.success("Synced with Trading 212");
    },
    onError: (err) => toast.error(err?.response?.data?.detail || "Sync failed"),
  });

  const handleDelete = async (r) => {
    const ok = await confirm({
      title: "Delete this cash entry?",
      message: `${r.type} of ${formatMoney(r.amount, r.currency)} on ${r.date} will be permanently removed.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (ok) del.mutate(r.id);
  };

  const [form, setForm] = useState({ type: "deposit", amount: "", currency: "CZK", date: "", note: "" });

  const submit = (e) => {
    e.preventDefault();
    add.mutate({ ...form, amount: Number(form.amount) });
    setForm((f) => ({ ...f, amount: "", note: "" }));
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Cash</h1>

      <CashReconciliationCard
        data={reconciliation.data}
        isLoading={reconciliation.isLoading}
        isError={reconciliation.isError}
        onRetry={reconciliation.refetch}
        connected={t212Status.data?.connected === true}
        currency={currency}
        onSync={handleSync}
        syncing={sync.isPending}
      />

      <MetricCard
        icon={Wallet}
        label="Recorded balance"
        value={formatMoney(balance.data?.total, currency)}
        sub={balance.data?.total_accrued > 0 ? `+${formatMoney(balance.data.total_accrued, currency)} interest` : null}
        positive={balance.data?.total_accrued > 0}
        loading={balance.isLoading}
      />

      {(history.data?.series?.length ?? 0) >= 2 && (
        <Card>
          <SectionHeader icon={TrendingUp}>Balance over time</SectionHeader>
          <CashBalanceChart data={history.data.series} currency={currency} />
        </Card>
      )}

      <Card>
        <SectionHeader icon={Plus}>Add cash flow</SectionHeader>
        <form onSubmit={submit} className="flex flex-wrap gap-2 items-end">
          <select
            className="input w-auto"
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
          >
            {CASH_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input
            className="input w-28"
            type="number"
            step="0.01"
            placeholder="Amount"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            required
          />
          <input
            className="input w-20"
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
          />
          <input
            className="input w-40"
            type="date"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
            required
          />
          <input
            className="input flex-1"
            placeholder="Note"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
          <button className="btn-primary" type="submit" disabled={add.isPending}>
            {add.isPending ? "Adding…" : "Add"}
          </button>
        </form>
        {add.isError && (
          <p className="text-loss text-xs mt-2">
            {add.error?.response?.data?.detail || "Failed to add cash flow"}
          </p>
        )}
      </Card>

      <Card>
        <SectionHeader icon={Wallet}>Ledger</SectionHeader>
        {rows.isLoading ? (
          <SkeletonRows rows={5} cols={4} />
        ) : (rows.data?.length ?? 0) === 0 ? (
          <EmptyState icon={Wallet} title="No cash flows yet" hint="Add an opening balance deposit to start." />
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {rows.data.map((r) => (
                <tr key={r.id} className="border-b border-hairline">
                  <td className="py-2 text-muted">{r.date}</td>
                  <td className="py-2"><TypeBadge type={r.type} /></td>
                  <td className={`py-2 font-sans tabular-nums text-right ${CASH_IN.has(r.type) ? "text-gain" : "text-loss"}`}>
                    {CASH_IN.has(r.type) ? "+" : "−"}{formatMoney(r.amount, r.currency)}
                  </td>
                  <td className="py-2 text-muted">{r.note}</td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => handleDelete(r)}
                      aria-label={`Delete ${r.type} on ${r.date}`}
                      className="text-muted hover:text-red-600 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card>
        <SectionHeader icon={Percent}>Interest (T212-style accrual)</SectionHeader>
        <InterestRates currency={currency} />
      </Card>
    </div>
  );
}

function InterestRates() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cash-rates"], queryFn: fetchInterestRates });
  const [draft, setDraft] = useState(null);
  const rows = draft ?? (q.data ?? []);
  const save = useMutation({
    mutationFn: saveInterestRates,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cash-rates"] });
      qc.invalidateQueries({ queryKey: ["cash-balance"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      setDraft(null);
    },
  });
  const set = (i, patch) => setDraft(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () =>
    setDraft([...rows, { currency: "USD", annual_rate: 0, enabled: true, start_date: null }]);

  if (q.isLoading) return <SkeletonRows rows={2} cols={3} />;
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            className="input w-20"
            value={r.currency}
            onChange={(e) => set(i, { currency: e.target.value.toUpperCase() })}
          />
          <input
            className="input w-24"
            type="number"
            step="0.01"
            value={(r.annual_rate * 100).toFixed(2)}
            onChange={(e) => set(i, { annual_rate: Number(e.target.value) / 100 })}
          />{" "}
          <span className="text-xs text-muted">% p.a.</span>
          <label className="text-xs flex items-center gap-1">
            <input
              type="checkbox"
              checked={r.enabled}
              onChange={(e) => set(i, { enabled: e.target.checked })}
            />{" "}
            enabled
          </label>
          <input
            className="input w-40"
            type="date"
            value={r.start_date ?? ""}
            onChange={(e) => set(i, { start_date: e.target.value || null })}
          />
        </div>
      ))}
      <div className="flex gap-2">
        <button className="btn-ghost" onClick={addRow}>
          + Currency
        </button>
        <button className="btn-primary" disabled={!draft} onClick={() => save.mutate(rows)}>
          Save
        </button>
      </div>
    </div>
  );
}
