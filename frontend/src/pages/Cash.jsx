import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Wallet, Plus, Trash2 } from "lucide-react";
import { Card, SectionHeader, SkeletonRows, EmptyState } from "../components/ui";
import { formatMoney } from "../lib/format";
import { fetchCash, createCash, deleteCash, fetchCashBalance } from "../api";
import { useCurrency } from "../App";

const CASH_TYPES = ["deposit", "withdrawal", "fee", "interest"];

export default function Cash() {
  // useCurrency() reads CurrencyContext (provided by App's CurrencyProvider);
  // outside that provider (e.g. in tests) the context is null, so fall back to USD.
  const currency = useCurrency()?.currency || "USD";
  const qc = useQueryClient();

  const rows = useQuery({ queryKey: ["cash"], queryFn: fetchCash });
  const balance = useQuery({
    queryKey: ["cash-balance", currency],
    queryFn: () => fetchCashBalance(currency),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cash"] });
    qc.invalidateQueries({ queryKey: ["cash-balance"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
  };

  const add = useMutation({ mutationFn: createCash, onSuccess: invalidate });
  const del = useMutation({ mutationFn: deleteCash, onSuccess: invalidate });

  const [form, setForm] = useState({ type: "deposit", amount: "", currency: "USD", date: "", note: "" });

  const submit = (e) => {
    e.preventDefault();
    add.mutate({ ...form, amount: Number(form.amount) });
    setForm((f) => ({ ...f, amount: "", note: "" }));
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Cash</h1>

      <Card>
        <SectionHeader icon={Wallet}>Balance</SectionHeader>
        {balance.isLoading ? (
          <SkeletonRows rows={2} cols={2} />
        ) : (
          <div className="flex items-baseline gap-3">
            <span className="font-mono text-2xl font-bold text-ink tnum">
              {formatMoney(balance.data?.total, currency)}
            </span>
            {balance.data?.total_accrued > 0 && (
              <span className="font-mono text-xs text-gain">
                +{formatMoney(balance.data.total_accrued, currency)} interest
              </span>
            )}
          </div>
        )}
      </Card>

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
          <p className="text-red-600 text-xs mt-2">
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
                  <td className="py-2 text-slate-500">{r.date}</td>
                  <td className="py-2 capitalize">{r.type}</td>
                  <td className="py-2 font-mono tnum text-right">{formatMoney(r.amount, r.currency)}</td>
                  <td className="py-2 text-slate-400">{r.note}</td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => del.mutate(r.id)}
                      aria-label={`Delete ${r.type} on ${r.date}`}
                      className="text-slate-400 hover:text-loss transition-colors"
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
    </div>
  );
}
