import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Briefcase, Check, ChevronDown, Pencil, Plus, Trash2, X } from "lucide-react";
import { usePortfolio } from "../App";
import { createPortfolio, deletePortfolio, updatePortfolio } from "../api";
import { useConfirm } from "./ui/ConfirmDialog";
import { useToast } from "./ui/Toast";

function NameModal({ title, initial = "", confirmLabel, busy, onCancel, onSubmit }) {
  const [name, setName] = useState(initial);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const submit = (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  };

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-lg">{title}</h2>
          <button type="button" onClick={onCancel} className="text-muted hover:text-ink">
            <X size={18} />
          </button>
        </div>
        <input
          ref={inputRef}
          className="input"
          placeholder="Portfolio name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={64}
          required
        />
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onCancel} className="btn-ghost flex-1">
            Cancel
          </button>
          <button type="submit" className="btn-primary flex-1" disabled={busy || !name.trim()}>
            {busy ? "Saving…" : confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function PortfolioSwitcher() {
  const { activePortfolios, portfolios: allPortfolios, current, setCurrentId, refetchPortfolios } = usePortfolio();
  const portfolios = activePortfolios || allPortfolios || [];
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState(null); // "create" | "rename"
  const [renameTarget, setRenameTarget] = useState(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const createMut = useMutation({
    mutationFn: (name) => createPortfolio({ name }),
    onSuccess: (created, name) => {
      setMode(null);
      refetchPortfolios().then(() => {
        if (created?.id) setCurrentId(created.id);
      });
      toast.success(`Portfolio "${created?.name || name}" created`);
    },
  });

  const renameMut = useMutation({
    mutationFn: ({ id, name }) => updatePortfolio(id, { name }),
    onSuccess: (_data, { name }) => {
      setMode(null);
      setRenameTarget(null);
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      toast.success(`Renamed to "${name}"`);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id) => deletePortfolio(id),
    onSuccess: (_data, deletedId) => {
      // If we deleted the active one, fall back to whatever's left.
      if (deletedId === current?.id) {
        const remaining = portfolios.filter((p) => p.id !== deletedId);
        const next = remaining.find((p) => p.is_default) || remaining[0];
        if (next) setCurrentId(next.id);
      }
      refetchPortfolios();
      toast.success("Portfolio deleted");
    },
  });

  const handleDelete = async (p) => {
    if (portfolios.length <= 1) return;
    const ok = await confirm({
      title: `Delete "${p.name}"?`,
      message: `This permanently removes all ${p.transaction_count ?? 0} transactions and any broker connection in it.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (ok) deleteMut.mutate(p.id);
  };

  const onSelect = (id) => {
    if (id !== current?.id) {
      setCurrentId(id);
    }
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Switch portfolio (current: ${current?.name ?? "none"})`}
        className="w-full flex items-center gap-2 bg-surface border border-surface-border rounded-lg px-3 py-2 text-left hover:border-slate-300 transition-colors"
      >
        <Briefcase size={14} className="text-brand shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-xs text-muted leading-none mb-0.5">Portfolio</div>
          <div className="text-sm font-medium truncate">
            {current?.name ?? "—"}
          </div>
        </div>
        <ChevronDown size={14} className={`text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute z-40 left-0 right-0 mt-1 bg-surface-card border border-surface-border rounded-lg shadow-lg py-1 max-h-80 overflow-y-auto">
          {portfolios.map((p) => {
            const active = p.id === current?.id;
            return (
              <div
                key={p.id}
                className={`flex items-center gap-2 px-2.5 py-1.5 text-sm group hover:bg-surface-hover ${
                  active ? "text-brand" : "text-ink"
                }`}
              >
                <button
                  onClick={() => onSelect(p.id)}
                  className="flex-1 flex items-center gap-2 min-w-0 text-left"
                >
                  <span className="w-3.5 shrink-0">
                    {active && <Check size={14} />}
                  </span>
                  <span className="truncate">{p.name}</span>
                  {p.is_default && (
                    <span className="text-xs uppercase tracking-wider text-muted ml-1">
                      default
                    </span>
                  )}
                  <span className="ml-auto text-xs text-muted tabular-nums">
                    {p.transaction_count ?? 0}
                  </span>
                </button>
                <button
                  title="Rename"
                  aria-label={`Rename ${p.name}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setRenameTarget(p);
                    setMode("rename");
                    setOpen(false);
                  }}
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-muted hover:text-ink"
                >
                  <Pencil size={12} />
                </button>
                <button
                  title={portfolios.length <= 1 ? "Cannot delete the last portfolio" : "Delete"}
                  aria-label={`Delete ${p.name}`}
                  disabled={portfolios.length <= 1}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(p);
                  }}
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-muted hover:text-red-600 disabled:opacity-20 disabled:cursor-not-allowed"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}

          <div className="border-t border-surface-border mt-1 pt-1">
            <button
              onClick={() => {
                setMode("create");
                setOpen(false);
              }}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 text-sm text-muted hover:bg-surface-hover"
            >
              <Plus size={14} />
              New portfolio
            </button>
          </div>
        </div>
      )}

      {mode === "create" && (
        <NameModal
          title="New portfolio"
          confirmLabel="Create"
          busy={createMut.isPending}
          onCancel={() => setMode(null)}
          onSubmit={(name) => createMut.mutate(name)}
        />
      )}

      {mode === "rename" && renameTarget && (
        <NameModal
          title={`Rename "${renameTarget.name}"`}
          initial={renameTarget.name}
          confirmLabel="Save"
          busy={renameMut.isPending}
          onCancel={() => {
            setMode(null);
            setRenameTarget(null);
          }}
          onSubmit={(name) => renameMut.mutate({ id: renameTarget.id, name })}
        />
      )}

      {(createMut.isError || renameMut.isError || deleteMut.isError) && (
        <p className="text-xs text-red-500 mt-1 px-1">
          {createMut.error?.response?.data?.detail ||
            renameMut.error?.response?.data?.detail ||
            deleteMut.error?.response?.data?.detail ||
            "Action failed"}
        </p>
      )}
    </div>
  );
}
