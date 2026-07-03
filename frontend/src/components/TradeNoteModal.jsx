import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchTradeNote, upsertTradeNote, deleteTradeNote } from "../api";
import { X, Loader2, TrendingUp, TrendingDown, Minus, Trash2 } from "lucide-react";

const SENTIMENTS = [
  { value: "bullish", label: "Bullish", icon: TrendingUp, color: "text-emerald-600 bg-emerald-50 border-emerald-200" },
  { value: "neutral", label: "Neutral", icon: Minus, color: "text-slate-600 bg-slate-50 border-slate-200" },
  { value: "bearish", label: "Bearish", icon: TrendingDown, color: "text-red-600 bg-red-50 border-red-200" },
];

export default function TradeNoteModal({ transaction, onClose }) {
  const queryClient = useQueryClient();
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [sentiment, setSentiment] = useState(null);

  const { data: note, isLoading } = useQuery({
    queryKey: ["trade-note", transaction.id],
    queryFn: () => fetchTradeNote(transaction.id),
  });

  useEffect(() => {
    if (note) {
      setContent(note.content || "");
      setTags(note.tags || "");
      setSentiment(note.sentiment || null);
    }
  }, [note]);

  const saveMut = useMutation({
    mutationFn: () => upsertTradeNote(transaction.id, { content, tags: tags || null, sentiment }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trade-note", transaction.id] });
      queryClient.invalidateQueries({ queryKey: ["trade-notes-all"] });
      onClose();
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteTradeNote(transaction.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trade-note", transaction.id] });
      queryClient.invalidateQueries({ queryKey: ["trade-notes-all"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="card w-full max-w-lg space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-bold text-lg">Trade Note</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {transaction.type.toUpperCase()} {transaction.shares} {transaction.ticker} @ ${transaction.price.toFixed(2)} &middot; {transaction.date}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-800"><X size={18} /></button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="animate-spin text-slate-400" />
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="text-xs text-slate-500 mb-1.5 block">Your notes</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Why did you make this trade? What was your thesis?"
                rows={4}
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-brand resize-none"
              />
            </div>

            <div>
              <label className="text-xs text-slate-500 mb-1.5 block">Sentiment</label>
              <div className="flex gap-2">
                {SENTIMENTS.map(({ value, label, icon: Icon, color }) => (
                  <button
                    key={value}
                    onClick={() => setSentiment(sentiment === value ? null : value)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                      sentiment === value ? color : "text-slate-400 bg-white border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <Icon size={13} />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-slate-500 mb-1.5 block">Tags (comma-separated)</label>
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="dip-buy, earnings, swing"
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-brand"
              />
            </div>

            <div className="flex gap-2 pt-1">
              {note?.content && (
                <button
                  onClick={() => window.confirm("Delete this note?") && deleteMut.mutate()}
                  disabled={deleteMut.isPending}
                  className="flex items-center gap-1.5 text-red-500 hover:text-red-700 text-sm px-3 py-2"
                >
                  <Trash2 size={14} />
                  Delete
                </button>
              )}
              <div className="flex-1" />
              <button onClick={onClose} className="btn-ghost px-4">Cancel</button>
              <button
                onClick={() => saveMut.mutate()}
                disabled={saveMut.isPending || !content.trim()}
                className="btn-primary px-5"
              >
                {saveMut.isPending ? "Saving..." : "Save Note"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
