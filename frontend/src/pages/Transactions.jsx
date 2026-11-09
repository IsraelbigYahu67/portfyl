import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchTransactionsPage, createTransaction, deleteTransaction, fetchAllTradeNotes } from "../api";
import { Plus, Trash2, X, StickyNote } from "lucide-react";
import { useCurrency } from "../App";
import { TickerLink } from "../components/StockDetail";
import TradeNoteModal from "../components/TradeNoteModal";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { AsyncSection, Badge, Modal } from "../components/ui";
import Pagination from "../components/ui/Pagination";
import SegmentedControl from "../components/ui/SegmentedControl";
import { formatMoney, formatQuantity, formatTableDate } from "../lib/format";
import { formatValidationDetail } from "../lib/validationDetail";
import { msg, useT } from "../i18n/I18nProvider";

const TYPE_TONES = { buy: "gain", sell: "loss", dividend: "info" };
const TYPE_LABELS = { buy: msg("Buy"), sell: msg("Sell"), dividend: msg("Dividend") };
const TYPE_OPTIONS = [
  { value: "all", label: msg("All") },
  { value: "buy", label: msg("Buy") },
  { value: "sell", label: msg("Sell") },
  { value: "dividend", label: msg("Dividend") },
];
const typeLabel = (t, type) => (TYPE_LABELS[type] ? t(TYPE_LABELS[type]) : String(type ?? ""));

function TypeBadge({ type }) {
  const t = useT();
  return (
    <Badge tone={TYPE_TONES[type] ?? "neutral"}>
      {typeLabel(t, type)}
    </Badge>
  );
}

function AddModal({ onClose }) {
  const t = useT();
  const qc = useQueryClient();
  const toast = useToast();
  const tickerRef = useRef(null);
  const [form, setForm] = useState({
    ticker: "", type: "buy", shares: "", price: "", currency: "USD", date: new Date().toISOString().slice(0, 10), notes: "",
  });

  const mut = useMutation({
    mutationFn: createTransaction,
    onSuccess: () => {
      ["transactions", "holdings", "summary", "heatmap", "performance"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
      toast.success(form.type === "dividend" ? t("Dividend added") : t("Transaction added"));
      onClose();
    },
  });

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    mut.mutate({ ...form, shares: parseFloat(form.shares), price: parseFloat(form.price) });
  };

  return (
    <Modal open onClose={onClose} titleId="add-transaction-title" initialFocusRef={tickerRef} className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 id="add-transaction-title" className="font-bold text-lg">{t("Add Transaction")}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("Close")}
            className="inline-flex h-11 w-11 items-center justify-center rounded-md text-muted hover:text-ink md:h-8 md:w-8"
          >
            <X size={18} />
          </button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted mb-1 block">{t("Ticker")} *</label>
              <input ref={tickerRef} className="input uppercase" placeholder={t("e.g. {example}", { example: "AAPL" })} aria-label={t("Ticker")} value={form.ticker} onChange={set("ticker")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">{t("Type")} *</label>
              <select className="input" value={form.type} onChange={set("type")} aria-label={t("Type")}>
                <option value="buy">{t("Buy")}</option>
                <option value="sell">{t("Sell")}</option>
                <option value="dividend">{t("Dividend")}</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">{t("Shares")} *</label>
              <input className="input" type="number" min="0.00000001" step="any" placeholder={t("e.g. {example}", { example: "10" })} aria-label={t("Shares")} value={form.shares} onChange={set("shares")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">{t("Price per share")} *</label>
              <input className="input" type="number" min="0.00000001" step="any" placeholder={t("e.g. {example}", { example: "185.50" })} aria-label={t("Price per share")} value={form.price} onChange={set("price")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">{t("Date")} *</label>
              <input className="input" type="date" aria-label={t("Date")} value={form.date} onChange={set("date")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">{t("Currency")}</label>
              <input className="input" placeholder="USD" aria-label={t("Currency")} value={form.currency} onChange={set("currency")} />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted mb-1 block">{t("Notes")}</label>
            <input className="input" placeholder={t("Optional")} aria-label={t("Notes")} value={form.notes} onChange={set("notes")} />
          </div>
          {mut.error && (
            <p role="alert" className="text-loss text-xs">
              {formatValidationDetail(mut.error.response?.data?.detail, {
                t,
                fallback: t("Failed to add transaction"),
              })}
            </p>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">{t("Cancel")}</button>
            <button type="submit" className="btn-primary flex-1" disabled={mut.isPending}>
              {mut.isPending ? t("Saving…") : t("Add")}
            </button>
          </div>
        </form>
    </Modal>
  );
}

export default function Transactions() {
  const t = useT();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [noteTarget, setNoteTarget] = useState(null);
  const [typeFilter, setTypeFilter] = useState("all");
  const currency = useCurrency()?.currency || "USD";
  const [params, setParams] = useSearchParams();

  const offset = Number(params.get("offset") || 0);
  const limit = Number(params.get("limit") || 50);
  const filter = params.get("q") || "";

  const updateParams = (patch, resetOffset = false) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => {
      if (v === undefined || v === null || v === "") next.delete(k);
      else next.set(k, String(v));
    });
    if (resetOffset) next.set("offset", "0");
    setParams(next, { replace: true });
  };

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["transactions", offset, limit, filter],
    queryFn: () => fetchTransactionsPage({ offset, limit, q: filter }),
    placeholderData: (previousData) => previousData,
  });
  const fetched = data?.items ?? [];
  // The type filter is client-side over the fetched page.
  const txns = typeFilter === "all" ? fetched : fetched.filter((txn) => txn.type === typeFilter);
  const total = data?.total ?? 0;

  const { data: allNotes = [] } = useQuery({ queryKey: ["trade-notes-all"], queryFn: fetchAllTradeNotes });
  const notesMap = Object.fromEntries(allNotes.map((n) => [n.transaction_id, n]));

  const delMut = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: () => {
      ["holdings", "summary", "heatmap", "performance"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
      qc.invalidateQueries({ queryKey: ["transactions"] });
      toast.success(t("Transaction deleted"));
      // If the deleted row was the only one on this page, step back one page.
      if (fetched.length === 1 && offset > 0) {
        updateParams({ offset: String(Math.max(0, offset - limit)) });
      }
    },
    onError: (err) =>
      toast.error(err.response?.data?.detail || t("Failed to delete transaction")),
  });

  const handleDelete = async (txn) => {
    const ok = await confirm({
      title: t("Delete transaction?"),
      message: txn.type === "dividend"
        ? t("Dividend {ticker} on {date} will be permanently removed.", { ticker: txn.ticker, date: txn.date })
        : t("{type} {shares} {ticker} on {date} will be permanently removed.", {
          type: typeLabel(t, txn.type),
          shares: txn.shares,
          ticker: txn.ticker,
          date: txn.date,
        }),
      confirmLabel: t("Delete"),
      danger: true,
    });
    if (ok) delMut.mutate(txn.id);
  };

  const hasFilter = filter.trim().length > 0;
  const noteButton = (txn, extra = "") => (
    <button
      onClick={() => setNoteTarget(txn)}
      className={`inline-flex h-11 w-11 items-center justify-center rounded-md transition-colors md:h-8 md:w-8 ${extra} ${notesMap[txn.id] ? "text-brand hover:text-brand/80" : "text-muted hover:text-ink"}`}
      title={notesMap[txn.id] ? t("Edit note") : t("Add note")}
      aria-label={notesMap[txn.id]
        ? t("Edit note for {ticker} on {date}", { ticker: txn.ticker, date: txn.date })
        : t("Add note for {ticker} on {date}", { ticker: txn.ticker, date: txn.date })}
    >
      <StickyNote size={14} />
    </button>
  );
  const deleteButton = (txn) => (
    <button
      onClick={() => handleDelete(txn)}
      aria-label={t("Delete {type} {ticker} on {date}", { type: typeLabel(t, txn.type), ticker: txn.ticker, date: txn.date })}
      className="inline-flex h-11 w-11 items-center justify-center rounded-md text-muted hover:text-loss transition-colors md:h-8 md:w-8"
    >
      <Trash2 size={14} />
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold">{t("Transactions")}</h1>
        <div className="flex gap-2 flex-wrap items-center">
          <SegmentedControl
            aria-label={t("Filter by type")}
            options={TYPE_OPTIONS.map((option) => ({ ...option, label: t(option.label) }))}
            value={typeFilter}
            onChange={setTypeFilter}
          />
          <input
            aria-label={t("Filter transactions by ticker")}
            className="input w-48"
            placeholder={t("Filter by ticker…")}
            value={filter}
            onChange={(e) => updateParams({ q: e.target.value }, true)}
          />
          <button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2">
            <Plus size={15} />
            {t("Add")}
          </button>
        </div>
      </div>

      <AsyncSection
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        loading={<div className="card animate-pulse h-40 flex items-center justify-center text-muted">{t("Loading…")}</div>}
        isEmpty={fetched.length === 0}
        empty={(
          <div className="card text-muted text-sm text-center py-12">
            {hasFilter
              ? t("No transactions match “{filter}”.", { filter })
              : t("No transactions yet. Import a CSV or add one manually.")}
          </div>
        )}
      >
        <div className="card p-0 overflow-hidden">
          {txns.length === 0 && (
            <p className="text-muted text-sm text-center py-12">
              {t("No transactions of this type on this page.")}
            </p>
          )}
          <ul className="md:hidden divide-y divide-surface-border">
            {txns.map((txn) => (
              <li key={txn.id} className="flex items-start justify-between gap-3 px-4 py-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-sm">
                      <TickerLink ticker={txn.ticker}>{txn.ticker}</TickerLink>
                    </span>
                    <TypeBadge type={txn.type} />
                  </div>
                  <p className="text-sm text-muted tabular-nums">
                    {formatTableDate(txn.date)} · {formatQuantity(txn.shares, currency)} × {formatMoney(txn.price, txn.currency)}
                  </p>
                  {txn.notes && <p className="text-xs text-muted truncate">{txn.notes}</p>}
                </div>
                <div className="shrink-0 text-right">
                  <p className="tabular-nums text-sm font-medium">{formatMoney(txn.shares * txn.price, txn.currency)}</p>
                  {/* Wide gap: the destructive button must not sit next to the note one. */}
                  <div className="flex justify-end gap-5">
                    {noteButton(txn)}
                    {deleteButton(txn)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-surface-border">
                <tr>
                  {[t("Date"), t("Ticker"), t("Type"), t("Shares"), t("Price"), t("Total"), t("Currency"), t("Notes"), ""].map((h, i) => (
                    <th key={h || i} scope="col" className={`${[3, 4, 5, 8].includes(i) ? "text-right" : "text-left"} px-4 py-3 whitespace-nowrap text-xs font-medium text-muted uppercase tracking-wider`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {txns.map((txn) => (
                  <tr key={txn.id} className="hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-sm text-ink whitespace-nowrap tabular-nums">{formatTableDate(txn.date)}</td>
                    <td className="px-4 py-3 font-mono font-bold text-sm">
                      <TickerLink ticker={txn.ticker}>{txn.ticker}</TickerLink>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <TypeBadge type={txn.type} />
                    </td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right">{formatQuantity(txn.shares, currency)}</td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right">{formatMoney(txn.price, txn.currency)}</td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right font-medium">
                      {formatMoney(txn.shares * txn.price, txn.currency)}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted">{txn.currency}</td>
                    {/* One Notes column: the imported note text, then the
                        button for the user's own trade note. */}
                    <td className="px-4 py-3 text-sm text-muted">
                      <div className="flex items-center gap-1">
                        {noteButton(txn, "shrink-0")}
                        <span className="max-w-xs truncate">{txn.notes || ""}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">{deleteButton(txn)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4">
            <Pagination
              offset={offset}
              limit={limit}
              total={total}
              onOffsetChange={(next) => updateParams({ offset: String(next) })}
              onLimitChange={(next) => updateParams({ limit: String(next) }, true)}
              ariaLabel={t("Transactions pages")}
            />
          </div>
        </div>
      </AsyncSection>

      {open && <AddModal onClose={() => setOpen(false)} />}
      {noteTarget && <TradeNoteModal transaction={noteTarget} onClose={() => setNoteTarget(null)} />}
    </div>
  );
}
