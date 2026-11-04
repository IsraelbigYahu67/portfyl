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
import { formatValidationDetail, uiLanguage } from "../lib/validationDetail";

const TYPE_TONES = { buy: "gain", sell: "loss", dividend: "info" };
const TYPE_LABELS = { buy: "Buy", sell: "Sell", dividend: "Dividend" };
const TYPE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "buy", label: "Buy" },
  { value: "sell", label: "Sell" },
  { value: "dividend", label: "Dividend" },
];

function TypeBadge({ type }) {
  return (
    <Badge tone={TYPE_TONES[type] ?? "neutral"}>
      {TYPE_LABELS[type] ?? String(type ?? "")}
    </Badge>
  );
}

function AddModal({ onClose }) {
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
      toast.success(`${form.type === "dividend" ? "Dividend" : "Transaction"} added`);
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
          <h2 id="add-transaction-title" className="font-bold text-lg">Add Transaction</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="inline-flex h-11 w-11 items-center justify-center rounded-md text-muted hover:text-ink md:h-8 md:w-8"
          >
            <X size={18} />
          </button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted mb-1 block">Ticker *</label>
              <input ref={tickerRef} className="input uppercase" placeholder="e.g. AAPL" value={form.ticker} onChange={set("ticker")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">Type *</label>
              <select className="input" value={form.type} onChange={set("type")}>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
                <option value="dividend">Dividend</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">Shares *</label>
              <input className="input" type="number" min="0.00000001" step="any" placeholder="e.g. 10" value={form.shares} onChange={set("shares")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">Price per share *</label>
              <input className="input" type="number" min="0.00000001" step="any" placeholder="e.g. 185.50" value={form.price} onChange={set("price")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">Date *</label>
              <input className="input" type="date" value={form.date} onChange={set("date")} required />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">Currency</label>
              <input className="input" placeholder="USD" value={form.currency} onChange={set("currency")} />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted mb-1 block">Notes</label>
            <input className="input" placeholder="Optional" value={form.notes} onChange={set("notes")} />
          </div>
          {mut.error && (
            <p role="alert" className="text-loss text-xs">
              {formatValidationDetail(mut.error.response?.data?.detail, {
                fallback: uiLanguage() === "cs" ? "Transakci se nepodařilo přidat" : "Failed to add transaction",
              })}
            </p>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" className="btn-primary flex-1" disabled={mut.isPending}>
              {mut.isPending ? "Saving…" : "Add"}
            </button>
          </div>
        </form>
    </Modal>
  );
}

export default function Transactions() {
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
  const txns = typeFilter === "all" ? fetched : fetched.filter((t) => t.type === typeFilter);
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
      toast.success("Transaction deleted");
      // If the deleted row was the only one on this page, step back one page.
      if (fetched.length === 1 && offset > 0) {
        updateParams({ offset: String(Math.max(0, offset - limit)) });
      }
    },
    onError: (err) =>
      toast.error(err.response?.data?.detail || "Failed to delete transaction"),
  });

  const handleDelete = async (t) => {
    const ok = await confirm({
      title: "Delete transaction?",
      message: `${t.type === "dividend" ? "Dividend" : `${t.type} ${t.shares} ${t.ticker}`} on ${t.date} will be permanently removed.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (ok) delMut.mutate(t.id);
  };

  const hasFilter = filter.trim().length > 0;
  const noteButton = (t, extra = "") => (
    <button
      onClick={() => setNoteTarget(t)}
      className={`inline-flex h-11 w-11 items-center justify-center rounded-md transition-colors md:h-8 md:w-8 ${extra} ${notesMap[t.id] ? "text-brand hover:text-brand/80" : "text-muted hover:text-ink"}`}
      title={notesMap[t.id] ? "Edit note" : "Add note"}
      aria-label={`${notesMap[t.id] ? "Edit" : "Add"} note for ${t.ticker} on ${t.date}`}
    >
      <StickyNote size={14} />
    </button>
  );
  const deleteButton = (t) => (
    <button
      onClick={() => handleDelete(t)}
      aria-label={`Delete ${t.type} ${t.ticker} on ${t.date}`}
      className="inline-flex h-11 w-11 items-center justify-center rounded-md text-muted hover:text-loss transition-colors md:h-8 md:w-8"
    >
      <Trash2 size={14} />
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold">Transactions</h1>
        <div className="flex gap-2 flex-wrap items-center">
          <SegmentedControl
            aria-label="Filter by type"
            options={TYPE_OPTIONS}
            value={typeFilter}
            onChange={setTypeFilter}
          />
          <input
            aria-label="Filter transactions by ticker"
            className="input w-48"
            placeholder="Filter by ticker…"
            value={filter}
            onChange={(e) => updateParams({ q: e.target.value }, true)}
          />
          <button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2">
            <Plus size={15} />
            Add
          </button>
        </div>
      </div>

      <AsyncSection
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        loading={<div className="card animate-pulse h-40 flex items-center justify-center text-muted">Loading…</div>}
        isEmpty={fetched.length === 0}
        empty={(
          <div className="card text-muted text-sm text-center py-12">
            {hasFilter
              ? `No transactions match “${filter}”.`
              : "No transactions yet. Import a CSV or add one manually."}
          </div>
        )}
      >
        <div className="card p-0 overflow-hidden">
          {txns.length === 0 && (
            <p className="text-muted text-sm text-center py-12">
              No {TYPE_LABELS[typeFilter]?.toLowerCase()} transactions on this page.
            </p>
          )}
          <ul className="md:hidden divide-y divide-surface-border">
            {txns.map((t) => (
              <li key={t.id} className="flex items-start justify-between gap-3 px-4 py-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-sm">
                      <TickerLink ticker={t.ticker}>{t.ticker}</TickerLink>
                    </span>
                    <TypeBadge type={t.type} />
                  </div>
                  <p className="text-sm text-muted tabular-nums">
                    {formatTableDate(t.date)} · {formatQuantity(t.shares, currency)} × {formatMoney(t.price, t.currency)}
                  </p>
                  {t.notes && <p className="text-xs text-muted truncate">{t.notes}</p>}
                </div>
                <div className="shrink-0 text-right">
                  <p className="tabular-nums text-sm font-medium">{formatMoney(t.shares * t.price, t.currency)}</p>
                  <div className="flex justify-end">
                    {noteButton(t)}
                    {deleteButton(t)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-surface-border">
                <tr>
                  {["Date", "Ticker", "Type", "Shares", "Price", "Total", "Currency", "Notes", ""].map((h, i) => (
                    <th key={h || i} scope="col" className={`${[3, 4, 5, 8].includes(i) ? "text-right" : "text-left"} px-4 py-3 whitespace-nowrap text-xs font-medium text-muted uppercase tracking-wider`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {txns.map((t) => (
                  <tr key={t.id} className="hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-sm text-ink whitespace-nowrap tabular-nums">{formatTableDate(t.date)}</td>
                    <td className="px-4 py-3 font-mono font-bold text-sm">
                      <TickerLink ticker={t.ticker}>{t.ticker}</TickerLink>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <TypeBadge type={t.type} />
                    </td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right">{formatQuantity(t.shares, currency)}</td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right">{formatMoney(t.price, t.currency)}</td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right font-medium">
                      {formatMoney(t.shares * t.price, t.currency)}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted">{t.currency}</td>
                    {/* One Notes column: the imported note text, then the
                        button for the user's own trade note. */}
                    <td className="px-4 py-3 text-sm text-muted">
                      <div className="flex items-center gap-1">
                        {noteButton(t, "shrink-0")}
                        <span className="max-w-xs truncate">{t.notes || ""}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">{deleteButton(t)}</td>
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
              ariaLabel="Transactions pages"
            />
          </div>
        </div>
      </AsyncSection>

      {open && <AddModal onClose={() => setOpen(false)} />}
      {noteTarget && <TradeNoteModal transaction={noteTarget} onClose={() => setNoteTarget(null)} />}
    </div>
  );
}
