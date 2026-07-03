import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchTransactions, createTransaction, deleteTransaction, fetchAllTradeNotes } from "../api";
import { Plus, Trash2, X, StickyNote } from "lucide-react";
import { TickerLink } from "../components/StockDetail";
import TradeNoteModal from "../components/TradeNoteModal";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";

const TYPE_COLORS = { buy: "text-emerald-600", sell: "text-red-600", dividend: "text-yellow-600" };

function AddModal({ onClose }) {
  const qc = useQueryClient();
  const toast = useToast();
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
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-lg">Add Transaction</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-800"><X size={18} /></button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Ticker *</label>
              <input className="input uppercase" placeholder="AAPL" value={form.ticker} onChange={set("ticker")} required />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Type *</label>
              <select className="input" value={form.type} onChange={set("type")}>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
                <option value="dividend">Dividend</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Shares *</label>
              <input className="input" type="number" step="any" placeholder="10" value={form.shares} onChange={set("shares")} required />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Price per share *</label>
              <input className="input" type="number" step="any" placeholder="185.50" value={form.price} onChange={set("price")} required />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Date *</label>
              <input className="input" type="date" value={form.date} onChange={set("date")} required />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Currency</label>
              <input className="input" placeholder="USD" value={form.currency} onChange={set("currency")} />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Notes</label>
            <input className="input" placeholder="Optional" value={form.notes} onChange={set("notes")} />
          </div>
          {mut.error && (
            <p className="text-red-600 text-xs">{mut.error.response?.data?.detail || "Failed to add transaction"}</p>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" className="btn-primary flex-1" disabled={mut.isPending}>
              {mut.isPending ? "Saving…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Transactions() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [noteTarget, setNoteTarget] = useState(null);

  const { data: txns = [], isLoading } = useQuery({ queryKey: ["transactions"], queryFn: fetchTransactions });
  const { data: allNotes = [] } = useQuery({ queryKey: ["trade-notes-all"], queryFn: fetchAllTradeNotes });
  const notesMap = Object.fromEntries(allNotes.map((n) => [n.transaction_id, n]));

  const delMut = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: () => {
      ["transactions", "holdings", "summary", "heatmap", "performance"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
      toast.success("Transaction deleted");
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

  const filtered = filter
    ? txns.filter((t) =>
        t.ticker.toLowerCase().includes(filter.toLowerCase()) ||
        t.type.includes(filter.toLowerCase())
      )
    : txns;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold">Transactions</h1>
        <div className="flex gap-2">
          <input
            className="input w-48"
            placeholder="Filter by ticker…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2">
            <Plus size={15} />
            Add
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="card animate-pulse h-40 flex items-center justify-center text-slate-500">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="card text-slate-500 text-sm text-center py-12">
          No transactions yet. Import a CSV or add one manually.
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-surface-border">
                <tr>
                  {["Date", "Ticker", "Type", "Shares", "Price", "Total", "Currency", "Notes", "Note", ""].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {filtered.map((t) => (
                  <tr key={t.id} className="hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-sm text-slate-700">{t.date}</td>
                    <td className="px-4 py-3 font-mono font-bold text-sm">
                      <TickerLink ticker={t.ticker}>{t.ticker}</TickerLink>
                    </td>
                    <td className={`px-4 py-3 text-sm font-medium capitalize ${TYPE_COLORS[t.type] || "text-slate-700"}`}>
                      {t.type}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right">{t.shares.toLocaleString()}</td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right">${t.price.toFixed(2)}</td>
                    <td className="px-4 py-3 tabular-nums text-sm text-right font-medium">
                      ${(t.shares * t.price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-500">{t.currency}</td>
                    <td className="px-4 py-3 text-sm text-slate-500 max-w-xs truncate">{t.notes || "—"}</td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => setNoteTarget(t)}
                        className={`transition-colors ${notesMap[t.id] ? "text-brand hover:text-brand/80" : "text-slate-300 hover:text-slate-500"}`}
                        title={notesMap[t.id] ? "Edit note" : "Add note"}
                      >
                        <StickyNote size={14} />
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDelete(t)}
                        aria-label={`Delete ${t.type} ${t.ticker} on ${t.date}`}
                        className="text-slate-400 hover:text-red-600 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {open && <AddModal onClose={() => setOpen(false)} />}
      {noteTarget && <TradeNoteModal transaction={noteTarget} onClose={() => setNoteTarget(null)} />}
    </div>
  );
}
