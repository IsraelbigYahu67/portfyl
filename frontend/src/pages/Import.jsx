import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle,
  Download,
  FileText,
  Info,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-react";

import {
  clearAllTransactions,
  commitImportCSV,
  fetchImportUndo,
  previewImportCSV,
  undoLastImport,
} from "../api";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";


const SAMPLE_NATIVE = `date,ticker,type,shares,price,currency
2023-06-01,AAPL,buy,10,180.57,USD
2023-08-15,MSFT,buy,5,316.48,USD
2024-01-20,NVDA,buy,12,61.50,USD
2024-05-15,MSFT,dividend,5,0.75,USD
2025-02-20,AAPL,sell,3,223.50,USD`;


function downloadSample() {
  const blob = new Blob([SAMPLE_NATIVE], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "sample_portfolio.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

function FormatBadge({ format }) {
  const trading212 = format === "Trading 212";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
      trading212 ? "bg-blue-100 text-blue-700" : "bg-green-100 text-green-700"
    }`}>
      {format}
    </span>
  );
}


function apiError(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.errors?.length) {
    return `${detail.message || "Import failed"}: ${detail.errors.join("; ")}`;
  }
  return detail?.message || "Import failed";
}


function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}


export default function Import() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [replace, setReplace] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const invalidatePortfolio = () => queryClient.invalidateQueries();

  const { data: undo } = useQuery({
    queryKey: ["import-undo"],
    queryFn: fetchImportUndo,
    retry: false,
  });

  const previewMutation = useMutation({
    mutationFn: () => previewImportCSV(file, replace),
    onSuccess: (data) => {
      setPreview(data);
      setResult(null);
      setError(null);
    },
    onError: (err) => {
      setPreview(null);
      setError(apiError(err));
    },
  });

  const commitMutation = useMutation({
    mutationFn: () => commitImportCSV(file, preview.preview_id, replace),
    onSuccess: (data) => {
      setResult(data);
      setPreview(null);
      setError(null);
      queryClient.setQueryData(["import-undo"], data.undo);
      invalidatePortfolio();
    },
    onError: (err) => {
      setPreview(null);
      setError(apiError(err));
    },
  });

  const undoMutation = useMutation({
    mutationFn: undoLastImport,
    onSuccess: () => {
      queryClient.setQueryData(["import-undo"], { available: false, reason: null });
      invalidatePortfolio();
      setResult(null);
      toast.success("Last import undone");
    },
    onError: (err) => toast.error(apiError(err)),
  });

  const clearMutation = useMutation({
    mutationFn: clearAllTransactions,
    onSuccess: () => {
      invalidatePortfolio();
      setFile(null);
      setPreview(null);
      setResult(null);
      setError(null);
      toast.success("Portfolio cleared");
    },
    onError: (err) => toast.error(apiError(err)),
  });

  async function handleClear() {
    const accepted = await confirm({
      title: "Clear portfolio?",
      message: "All transactions in this portfolio will be permanently deleted. This cannot be undone.",
      confirmLabel: "Delete all",
      danger: true,
    });
    if (accepted) clearMutation.mutate();
  }

  async function handleUndo() {
    const accepted = await confirm({
      title: "Undo last import?",
      message: "Portfyl will restore the portfolio exactly as it was before the last import.",
      confirmLabel: "Undo import",
    });
    if (accepted) undoMutation.mutate();
  }

  const onDrop = useCallback((accepted) => {
    if (!accepted[0]) return;
    setFile(accepted[0]);
    setPreview(null);
    setResult(null);
    setError(null);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "text/csv": [".csv"] },
    multiple: false,
  });

  const duplicateCount = preview
    ? preview.counts.duplicates_in_file
      + (preview.mode === "append" ? preview.counts.duplicates_existing : 0)
    : 0;

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold">Import CSV</h1>
          <p className="text-xs text-muted mt-1">Preview every change before it reaches your portfolio.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleClear} className="btn-ghost flex items-center gap-2 text-sm text-red-600" disabled={clearMutation.isPending}>
            <Trash2 size={14} />
            {clearMutation.isPending ? "Clearing…" : "Clear portfolio"}
          </button>
          <button onClick={downloadSample} className="btn-ghost flex items-center gap-2 text-sm">
            <Download size={14} /> Download sample
          </button>
        </div>
      </div>

      {undo?.available && (
        <section className="card border border-blue-500/30 bg-blue-500/5 flex items-start justify-between gap-4" aria-label="Import recovery">
          <div className="flex items-start gap-3">
            <RotateCcw size={18} className="text-brand mt-0.5 shrink-0" />
            <div>
              <p className="font-semibold text-sm">Your last import can be undone</p>
              <p className="text-xs text-muted mt-1">
                Available until {new Date(undo.expires_at).toLocaleString()} unless the portfolio changes.
              </p>
            </div>
          </div>
          <button onClick={handleUndo} className="btn-ghost text-sm shrink-0" disabled={undoMutation.isPending}>
            {undoMutation.isPending ? "Restoring…" : "Undo last import"}
          </button>
        </section>
      )}

      <section className="card space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <FormatBadge format="Trading 212" />
          <FormatBadge format="Native" />
          <span className="text-xs text-muted">Auto-detected · maximum 5 MiB</span>
        </div>
        <div className="flex items-start gap-2 text-xs text-muted">
          <Info size={14} className="text-brand mt-0.5 shrink-0" />
          <p>
            Trading 212 exports include the full account history and therefore replace this portfolio.
            Native CSV files can append new rows or replace the portfolio.
          </p>
        </div>
      </section>

      <div
        {...getRootProps()}
        className={`card border-2 border-dashed cursor-pointer transition-colors flex flex-col items-center justify-center py-10 gap-3 ${
          isDragActive ? "border-brand bg-brand/5" : "border-surface-border hover:border-gray-500"
        }`}
      >
        <input {...getInputProps()} />
        <Upload size={32} className={isDragActive ? "text-brand" : "text-muted"} />
        {file ? (
          <div className="text-center">
            <div className="flex items-center gap-2 text-sm font-medium">
              <FileText size={16} className="text-brand" /> {file.name}
            </div>
            <p className="text-xs text-muted mt-1">{(file.size / 1024).toFixed(1)} KiB</p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm font-medium">Drop your CSV here or click to browse</p>
            <p className="text-xs text-muted mt-1">Nothing is saved until you review and confirm.</p>
          </div>
        )}
      </div>

      {file && !preview && !result && (
        <div className="space-y-3">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={replace}
              onChange={(event) => {
                setReplace(event.target.checked);
                setPreview(null);
              }}
              className="mt-0.5 accent-red-500 w-4 h-4"
            />
            <span>
              <span className="text-sm font-medium">Replace existing portfolio</span>
              <span className="block text-xs text-muted mt-0.5">The preview will show exactly what would be removed.</span>
            </span>
          </label>
          <button onClick={() => previewMutation.mutate()} className="btn-primary w-full" disabled={previewMutation.isPending}>
            {previewMutation.isPending ? "Preparing preview…" : "Preview import"}
          </button>
        </div>
      )}

      {preview && (
        <section className={`card border space-y-4 ${preview.mode === "replace" ? "border-red-500/40" : "border-brand/30"}`} aria-label="Import preview">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">Review changes</h2>
              <FormatBadge format={preview.format} />
            </div>
            <button onClick={() => setPreview(null)} className="text-xs text-muted hover:text-ink">Change options</button>
          </div>

          {preview.mode === "replace" && (
            <div className="rounded-lg bg-loss/10 border border-red-500/30 p-3 text-sm">
              <p className="font-semibold text-loss">Trading 212 exports replace the full portfolio when detected.</p>
              <p className="text-muted mt-1">
                {plural(preview.counts.removed, "current transaction")} will be removed. You can undo for 24 hours if the portfolio stays unchanged.
              </p>
              {preview.counts.notes_removed > 0 && (
                <p className="text-muted mt-1">
                  {plural(preview.counts.notes_removed, "trade note")} will be removed with those transactions and restored by undo.
                </p>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">Current</p><p className="font-bold">{preview.counts.current}</p></div>
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">Added</p><p className="font-bold text-gain">+{preview.counts.added}</p></div>
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">Removed</p><p className="font-bold text-loss">−{preview.counts.removed}</p></div>
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">After import</p><p className="font-bold">{preview.counts.projected}</p></div>
          </div>

          <div className="text-sm space-y-1">
            <p>{plural(preview.counts.added, "transaction")} will be added.</p>
            {duplicateCount > 0 && <p className="text-muted">{plural(duplicateCount, "exact duplicate")} will be skipped.</p>}
            {preview.counts.skipped > 0 && <p className="text-muted">{plural(preview.counts.skipped, "informational row")} recognized and skipped.</p>}
          </div>

          {preview.sample.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-muted">
                  <tr><th className="text-left py-2">Date</th><th className="text-left">Ticker</th><th className="text-left">Type</th><th className="text-right">Shares</th><th className="text-right">Price</th></tr>
                </thead>
                <tbody>
                  {preview.sample.map((row, index) => (
                    <tr key={`${row.date}-${row.ticker}-${index}`} className="border-t border-surface-border">
                      <td className="py-2">{row.date}</td><td>{row.ticker || "Cash"}</td><td>{row.type}</td><td className="text-right">{row.shares}</td><td className="text-right">{row.price} {row.currency}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <button
            onClick={() => commitMutation.mutate()}
            className={`w-full font-semibold px-4 py-2 rounded-lg ${preview.mode === "replace" ? "bg-red-600 hover:bg-red-700 text-white" : "btn-primary"}`}
            disabled={commitMutation.isPending}
          >
            {commitMutation.isPending
              ? "Importing…"
              : preview.mode === "replace"
                ? `Replace portfolio with ${plural(preview.counts.projected, "transaction")}`
                : `Import ${plural(preview.counts.added, "transaction")}`}
          </button>
        </section>
      )}

      {error && (
        <div role="alert" className="card border border-red-500/40 bg-loss/10 flex items-start gap-3">
          <AlertCircle size={18} className="text-loss mt-0.5 shrink-0" />
          <div><p className="font-semibold text-loss">Import not applied</p><p className="text-sm text-loss mt-1">{error}</p></div>
        </div>
      )}

      {result && (
        <div className="card border border-green-500/40 bg-gain/10 flex items-start gap-3">
          <CheckCircle size={18} className="text-gain mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="font-semibold text-gain">{plural(result.imported, "transaction")} imported</p>
            {result.duplicates_skipped > 0 && <p className="text-xs text-muted mt-1">{plural(result.duplicates_skipped, "exact duplicate")} skipped.</p>}
            <button onClick={() => { setFile(null); setResult(null); }} className="mt-3 text-xs text-muted hover:text-ink">Import another file →</button>
          </div>
        </div>
      )}
    </div>
  );
}
