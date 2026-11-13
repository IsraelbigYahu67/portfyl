import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Plus, RefreshCw, TrendingUp, Trash2, Wallet } from "lucide-react";
import { Badge, Card, SectionHeader, SkeletonRows, EmptyState, ErrorState } from "../components/ui";
import Pagination from "../components/ui/Pagination";
import MetricCard from "../components/MetricCard";
import { formatDateTime, formatLongDate, formatMoney, formatTableDate, humanizeCode } from "../lib/format";
import CashBalanceChart from "../components/CashBalanceChart";
import {
  fetchCash,
  createCash,
  deleteCash,
  fetchCashBalance,
  fetchCashHistory,
  fetchCashReconciliation,
} from "../api";
import { useCurrency, usePortfolio } from "../App";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { useT212Sync } from "../hooks/useT212Sync";
import { msg, useT } from "../i18n/I18nProvider";

// Types offered for manual entry; the ledger can additionally contain imported
// rows (card debits, cashback, FX conversion legs) from a Trading 212 CSV.
const CASH_TYPES = ["deposit", "withdrawal", "fee", "interest"];

const TYPE_LABEL = {
  deposit: msg("Deposit"),
  withdrawal: msg("Withdrawal"),
  fee: msg("Fee"),
  fee_refund: msg("Fee refund"),
  interest: msg("Interest"),
  card_debit: msg("Card"),
  cashback: msg("Cashback"),
  fx_in: msg("FX in"),
  fx_out: msg("FX out"),
};

// Direction of each type's cash impact — mirrors backend signed_cash.
const CASH_IN = new Set(["deposit", "interest", "cashback", "fx_in", "fee_refund"]);

function TypeBadge({ type }) {
  const t = useT();
  return (
    <Badge tone={CASH_IN.has(type) ? "gain" : "loss"}>
      {TYPE_LABEL[type] ? t(TYPE_LABEL[type]) : humanizeCode(type)}
    </Badge>
  );
}

const LEDGER_PAGE_SIZE = 25;

// Imported Trading 212 notes arrive as "T212 INTEREST_ON_FREE_CASH": keep the
// source prefix and make the machine code readable. Free-text notes are left as typed.
function formatNote(note) {
  if (!note) return "—";
  const match = /^(T212 )?([A-Z_]+)$/.exec(note.trim());
  if (!match || (!match[1] && !match[2].includes("_"))) return note;
  return `${match[1] ?? ""}${humanizeCode(match[2])}`;
}

function DeleteEntryButton({ row, onDelete }) {
  const t = useT();
  const type = TYPE_LABEL[row.type] ? t(TYPE_LABEL[row.type]) : humanizeCode(row.type);
  return (
    <button
      type="button"
      onClick={() => onDelete(row)}
      aria-label={t("Delete {type} on {date}", { type, date: row.date })}
      className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-muted hover:text-loss transition-colors"
    >
      <Trash2 size={14} />
    </button>
  );
}

function signedAmount(row) {
  return `${CASH_IN.has(row.type) ? "+" : "−"}${formatMoney(row.amount, row.currency)}`;
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
    label: msg("Matches your recorded history"),
  },
  different: {
    icon: AlertTriangle,
    tone: "text-loss",
    badge: "bg-loss/10 text-loss",
    label: msg("Differs from your recorded history"),
  },
};

function CashReconciliationCard({ data, isLoading, isError, onRetry, connected, currency, onSync, syncing }) {
  const t = useT();
  return (
    <Card>
      <SectionHeader icon={Wallet}>{t("Current Trading 212 balance")}</SectionHeader>
      {isLoading ? (
        <SkeletonRows rows={2} cols={2} />
      ) : isError ? (
        <ErrorState message={t("Couldn't load your broker balance.")} onRetry={onRetry} />
      ) : !data || data.status === "unavailable" ? (
        <EmptyState
          icon={Wallet}
          title={connected ? t("No Trading 212 balance synced yet") : t("No Trading 212 connected")}
          hint={
            connected
              ? t("Sync your Trading 212 connection to see your current broker balance here.")
              : t("Connect Trading 212 in Settings to see your current broker balance alongside your recorded cash history.")
          }
          action={
            connected ? (
              <button type="button" className="btn-primary" onClick={onSync} disabled={syncing}>
                {syncing ? t("Syncing…") : t("Sync now")}
              </button>
            ) : (
              <Link className="btn-primary" to="/settings?section=connections">{t("Connect {broker}", { broker: "Trading 212" })}</Link>
            )
          }
        />
      ) : data.status === "no_ledger_history" ? (
        <div className="space-y-3">
          <div>
            <p className="text-xs text-muted">{t("Trading 212 (broker snapshot)")}</p>
            <p className="text-2xl font-display font-bold tabular-nums text-ink">
              {formatMoney(data.broker_amount, currency)}
            </p>
            {data.broker_as_of && (
              <p className="text-xs text-muted mt-1">
                {t("As of {date}", { date: formatLongDate(data.broker_as_of) })}
                {data.broker_updated_at && ` · ${t("synced {time}", { time: formatDateTime(data.broker_updated_at) })}`}
              </p>
            )}
          </div>
          <p className="text-xs text-muted">
            {t("No recorded cash history yet. Add deposits and withdrawals, or import your transaction history, so Portfyl can compare them against this broker balance.")}
          </p>
          <Link className="btn-ghost" to="/import">{t("Import transactions")}</Link>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs text-muted">{t("Trading 212 (broker snapshot)")}</p>
              <p className="text-2xl font-display font-bold tabular-nums text-ink">
                {formatMoney(data.broker_amount, currency)}
              </p>
              {data.broker_as_of && (
                <p className="text-xs text-muted mt-1">
                  {t("As of {date}", { date: formatLongDate(data.broker_as_of) })}
                  {data.broker_updated_at && ` · ${t("synced {time}", { time: formatDateTime(data.broker_updated_at) })}`}
                </p>
              )}
            </div>
            <div>
              <p className="text-xs text-muted">{t("Recorded ledger history")}</p>
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
            <span className="font-medium">{t((STATUS_COPY[data.status] ?? STATUS_COPY.different).label)}</span>
            {data.status === "different" && (
              <span className="text-xs opacity-90">({t("{amount} difference", { amount: formatMoney(data.difference, currency) })})</span>
            )}
            {data.status === "matched" && (
              <span className="text-xs opacity-90">({t("within {amount}", { amount: formatMoney(data.tolerance, currency) })})</span>
            )}
          </div>

          {data.status === "different" && (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-muted">
                {t("A difference usually means your recorded history is incomplete, not that either number is wrong. Import missing transactions or sync your broker connection — Portfyl never adjusts the ledger automatically to force a match.")}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary flex items-center gap-1.5"
                  onClick={onSync}
                  disabled={syncing}
                >
                  <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
                  {syncing ? t("Syncing…") : t("Sync now")}
                </button>
                <Link className="btn-ghost" to="/import">{t("Import transactions")}</Link>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export default function Cash() {
  const t = useT();
  // useCurrency() reads CurrencyContext (provided by App's CurrencyProvider);
  // outside that provider (e.g. in tests) the context is null, so fall back to USD.
  const currency = useCurrency()?.currency || "USD";
  const currentPortfolio = usePortfolio()?.current;
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
  const t212 = useT212Sync({
    portfolioId: currentPortfolio?.id,
    currency,
    includePositions: false,
  });

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
      toast.success(t("Cash entry deleted"));
    },
    onError: (err) =>
      toast.error(err?.response?.data?.detail || t("Failed to delete cash entry")),
  });
  const sync = t212.syncMutation;
  const handleSync = () => t212.sync(undefined, {
    onSuccess: () => toast.success(t("Synced with {broker}", { broker: "Trading 212" })),
    onError: (err) => toast.error(err?.response?.data?.detail || t("Sync failed")),
  });

  const handleDelete = async (r) => {
    const ok = await confirm({
      title: t("Delete this cash entry?"),
      message: t("{type} of {amount} on {date} will be permanently removed.", {
        type: TYPE_LABEL[r.type] ? t(TYPE_LABEL[r.type]) : humanizeCode(r.type),
        amount: formatMoney(r.amount, r.currency),
        date: r.date,
      }),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (ok) del.mutate(r.id);
  };

  const [form, setForm] = useState({ type: "deposit", amount: "", currency: "CZK", date: "", note: "" });

  const [ledgerOffset, setLedgerOffset] = useState(0);
  const ledgerRows = rows.data ?? [];
  const lastPageStart = Math.max(0, Math.ceil(ledgerRows.length / LEDGER_PAGE_SIZE) - 1) * LEDGER_PAGE_SIZE;
  const pageOffset = Math.min(ledgerOffset, lastPageStart);
  const pageRows = ledgerRows.slice(pageOffset, pageOffset + LEDGER_PAGE_SIZE);

  const submit = (e) => {
    e.preventDefault();
    add.mutate({ ...form, amount: Number(form.amount) });
    setForm((f) => ({ ...f, amount: "", note: "" }));
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">{t("Cash")}</h1>

      <CashReconciliationCard
        data={reconciliation.data}
        isLoading={reconciliation.isLoading}
        isError={reconciliation.isError}
        onRetry={reconciliation.refetch}
        connected={t212.connected}
        currency={currency}
        onSync={handleSync}
        syncing={sync.isPending}
      />

      <MetricCard
        icon={Wallet}
        label={t("Recorded balance")}
        value={formatMoney(balance.data?.total, currency)}
        sub={balance.data?.total_accrued > 0 ? t("+{amount} interest", { amount: formatMoney(balance.data.total_accrued, currency) }) : null}
        positive={balance.data?.total_accrued > 0}
        loading={balance.isLoading}
      />

      {(history.data?.series?.length ?? 0) >= 2 && (
        <Card>
          <SectionHeader icon={TrendingUp}>{t("Balance over time")}</SectionHeader>
          <CashBalanceChart data={history.data.series} currency={currency} />
        </Card>
      )}

      <Card>
        <SectionHeader icon={Plus}>{t("Add cash flow")}</SectionHeader>
        <form onSubmit={submit} className="flex flex-wrap gap-2 items-end">
          <select
            className="input w-auto"
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
          >
            {CASH_TYPES.map((type) => (
              <option key={type} value={type}>{t(TYPE_LABEL[type])}</option>
            ))}
          </select>
          <input
            className="input w-28"
            type="number"
            step="0.01"
            placeholder={t("Amount")}
            aria-label={t("Amount")}
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
            placeholder={t("Note")}
            aria-label={t("Note")}
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
          <button className="btn-primary" type="submit" disabled={add.isPending}>
            {add.isPending ? t("Adding…") : t("Add")}
          </button>
        </form>
        {add.isError && (
          <p className="text-loss text-xs mt-2">
            {add.error?.response?.data?.detail || t("Failed to add cash flow")}
          </p>
        )}
      </Card>

      <Card>
        <SectionHeader icon={Wallet}>{t("Ledger")}</SectionHeader>
        {rows.isLoading ? (
          <SkeletonRows rows={5} cols={4} />
        ) : (rows.data?.length ?? 0) === 0 ? (
          <EmptyState icon={Wallet} title={t("No cash flows yet")} hint={t("Add an opening balance deposit to start.")} />
        ) : (
          <>
            <ul className="md:hidden divide-y divide-hairline">
              {pageRows.map((r) => (
                <li key={r.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted tabular-nums">{formatTableDate(r.date)}</span>
                      <TypeBadge type={r.type} />
                    </div>
                    {r.note && <p className="text-xs text-muted break-words">{formatNote(r.note)}</p>}
                  </div>
                  <div className="shrink-0 flex items-center gap-1">
                    <span className={`font-sans tabular-nums text-sm ${CASH_IN.has(r.type) ? "text-gain" : "text-loss"}`}>
                      {signedAmount(r)}
                    </span>
                    <DeleteEntryButton row={r} onDelete={handleDelete} />
                  </div>
                </li>
              ))}
            </ul>
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-hairline">
                  <tr>
                    {[
                      [t("Date"), "text-left"],
                      [t("Type"), "text-left"],
                      [t("Amount"), "text-right"],
                      [t("Note"), "text-left pl-6"],
                      ["", "text-right"],
                    ].map(([h, cls], i) => (
                      <th key={i} scope="col" className={`py-2 whitespace-nowrap text-xs font-medium text-muted uppercase tracking-wider ${cls}`}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((r) => (
                    <tr key={r.id} className="border-b border-hairline">
                      <td className="py-2 text-muted whitespace-nowrap tabular-nums">{formatTableDate(r.date)}</td>
                      <td className="py-2"><TypeBadge type={r.type} /></td>
                      <td className={`py-2 font-sans tabular-nums text-right whitespace-nowrap ${CASH_IN.has(r.type) ? "text-gain" : "text-loss"}`}>
                        {signedAmount(r)}
                      </td>
                      <td className="py-2 pl-6 text-muted">{formatNote(r.note)}</td>
                      <td className="py-2 text-right">
                        <DeleteEntryButton row={r} onDelete={handleDelete} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {ledgerRows.length > LEDGER_PAGE_SIZE && (
              <Pagination
                offset={pageOffset}
                limit={LEDGER_PAGE_SIZE}
                total={ledgerRows.length}
                onOffsetChange={setLedgerOffset}
                ariaLabel={t("Cash ledger pages")}
              />
            )}
          </>
        )}
      </Card>
    </div>
  );
}
