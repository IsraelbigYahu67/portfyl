import { useCallback, useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle,
  Download,
  FileText,
  Info,
  RotateCcw,
  Upload,
} from "lucide-react";

import {
  commitImportCSV,
  fetchImportUndo,
  previewImportCSV,
  undoLastImport,
} from "../api";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { usePortfolio } from "../App";
import { TRACKER_HOME } from "../lib/routes";
import { useRegisteredActivation } from "../analytics/useRegisteredActivation";


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


const IMPORT_STEPS = ["Select source", "Preview changes", "Confirm import", "Result / Undo"];

export default function Import({ focused = false }) {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const navigate = useNavigate();
  const { current, pendingImportPortfolio, refetchPortfolios, setCurrentId } = usePortfolio();
  const { recordPortfolioDataImported } = useRegisteredActivation();
  const [file, setFile] = useState(null);
  const [replace, setReplace] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [undoError, setUndoError] = useState(null);
  const [stage, setStage] = useState("select");
  const stageIndex = { select: 0, preview: 1, confirm: 2, result: 3 }[stage];
  const onboardingPending = current?.activation_state === "pending_import" || pendingImportPortfolio?.id === current?.id;

  const invalidatePortfolio = (includePortfolios = true) => queryClient.invalidateQueries({
    predicate: (query) => includePortfolios || query.queryKey[0] !== "portfolios",
  });

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
      setStage("preview");
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
      setStage("result");
      queryClient.setQueryData(["import-undo"], data.undo);
      invalidatePortfolio(false);
      recordPortfolioDataImported("csv");
    },
    onError: (err) => {
      if (err?.response?.status === 409) {
        setPreview(null);
        setStage("select");
        setError("The portfolio changed. Preview the file again.");
      } else {
        setStage("confirm");
        setError(apiError(err));
      }
    },
  });

  const undoMutation = useMutation({
    mutationFn: undoLastImport,
    onSuccess: () => {
      queryClient.setQueryData(["import-undo"], { available: false, reason: null });
      invalidatePortfolio();
      setResult(null);
      setStage("select");
      setUndoError(null);
      toast.success("Last import undone");
    },
    onError: (err) => {
      const message = apiError(err);
      setUndoError(message);
      toast.error(message);
    },
  });

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
    setStage("select");
  }, []);

  useEffect(() => {
    if (!result) return;
    refetchPortfolios();
  }, [result, refetchPortfolios]);

  const cancelPreview = () => {
    setPreview(null);
    setError(null);
    setStage("select");
  };

  const viewPortfolio = async () => {
    const refreshed = await refetchPortfolios();
    const rows = refreshed?.data || [];
    const activated = rows.find((portfolio) => portfolio.id === current?.id) || current;
    if (activated?.id) setCurrentId(activated.id);
    navigate(TRACKER_HOME);
  };

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
          {(focused || onboardingPending) && <button type="button" onClick={() => navigate("/onboarding")} className="btn-ghost text-sm">Leave import</button>}
          <button onClick={downloadSample} className="btn-ghost flex items-center gap-2 text-sm">
            <Download size={14} /> Download sample
          </button>
        </div>
      </div>

      <ol aria-label="Import progress" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {IMPORT_STEPS.map((label, index) => (
          <li key={label} aria-current={index === stageIndex ? "step" : undefined} className={`rounded-lg border px-3 py-2 text-xs font-medium ${index === stageIndex ? "border-brand bg-brand/10 text-brand" : index < stageIndex ? "border-gain/30 text-gain" : "border-surface-border text-muted"}`}>
            <span className="mr-1 tabular-nums">{index + 1}.</span>{label}
          </li>
        ))}
      </ol>

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
      {undoError && <p role="alert" className="text-sm text-loss">Undo was not applied: {undoError}</p>}

      {stage === "select" && <>
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
                setStage("select");
                setError(null);
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
      </>}

      {preview && stage === "preview" && (
        <section className={`card border space-y-4 ${preview.mode === "replace" ? "border-red-500/40" : "border-brand/30"}`} aria-label="Import preview">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">Review changes</h2>
              <FormatBadge format={preview.format} />
            </div>
            <button onClick={cancelPreview} className="text-xs text-muted hover:text-ink">Cancel preview</button>
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
            type="button"
            onClick={() => { setStage("confirm"); setError(null); }}
            className="btn-primary w-full"
          >
            Continue to confirm
          </button>
        </section>
      )}

      {preview && stage === "confirm" && (
        <section className={`card space-y-4 border ${preview.mode === "replace" ? "border-red-500/40" : "border-brand/30"}`} aria-label="Confirm import">
          <div>
            <h2 className="font-semibold">Confirm import</h2>
            <p className="mt-1 text-sm text-muted">{preview.mode === "replace" ? "Replace" : "Append"} mode · {plural(preview.counts.added, "transaction")} added · {plural(preview.counts.removed, "transaction")} removed · {plural(duplicateCount, "duplicate")} skipped · {preview.counts.projected} total after import.</p>
          </div>
          <div className="flex gap-3">
            <button type="button" onClick={() => setStage("preview")} className="btn-ghost flex-1" disabled={commitMutation.isPending}>Back to preview</button>
            <button type="button" onClick={() => commitMutation.mutate()} className={`flex-1 rounded-lg px-4 py-2 font-semibold ${preview.mode === "replace" ? "bg-red-600 text-white hover:bg-red-700" : "btn-primary"}`} disabled={commitMutation.isPending}>
              {commitMutation.isPending ? "Importing…" : preview.mode === "replace" ? `Replace portfolio with ${plural(preview.counts.projected, "transaction")}` : `Import ${plural(preview.counts.added, "transaction")}`}
            </button>
          </div>
        </section>
      )}

      {error && (
        <div role="alert" className="card border border-red-500/40 bg-loss/10 flex items-start gap-3">
          <AlertCircle size={18} className="text-loss mt-0.5 shrink-0" />
          <div><p className="font-semibold text-loss">Import not applied</p><p className="text-sm text-loss mt-1">{error}</p></div>
        </div>
      )}

      {result && stage === "result" && (
        <div className="card border border-green-500/40 bg-gain/10 flex items-start gap-3">
          <CheckCircle size={18} className="text-gain mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="font-semibold text-gain">{plural(result.imported, "transaction")} imported</p>
            {result.duplicates_skipped > 0 && <p className="text-xs text-muted mt-1">{plural(result.duplicates_skipped, "exact duplicate")} skipped.</p>}
            {result.removed > 0 && <p className="text-xs text-muted mt-1">{plural(result.removed, "previous transaction")} removed.</p>}
            {result.undo?.available && <p className="mt-1 text-xs text-muted">Undo available until {new Date(result.undo.expires_at).toLocaleString()}.</p>}
            <button type="button" onClick={viewPortfolio} className="btn-primary mt-3 text-sm">View portfolio</button>
            <button onClick={() => { setFile(null); setResult(null); setStage("select"); }} className="mt-3 text-xs text-muted hover:text-ink">Import another file →</button>
            <Link to="/settings?section=data" className="ml-4 mt-3 inline-block text-xs text-muted hover:text-ink">Manage portfolio data</Link>
          </div>
        </div>
      )}
    </div>
  );
}
