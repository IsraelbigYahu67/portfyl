import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { importCSV, clearAllTransactions } from "../api";
import { Upload, FileText, CheckCircle, AlertCircle, Download, Info, Trash2 } from "lucide-react";
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
  const a = document.createElement("a");
  a.href = url;
  a.download = "sample_portfolio.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function FormatBadge({ label, color }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

export default function Import() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [replace, setReplace] = useState(false);

  // An import/clear rewrites the whole transaction set, so every derived query
  // is stale — invalidate all of them. (The previous hardcoded list omitted
  // keys like holdings-all, sector-breakdown, dividends/forecast and analytics,
  // leaving those pages showing pre-import data.) Unlike the Dashboard refresh
  // button, this fires rarely and genuinely affects every page.
  const invalidateAll = () => qc.invalidateQueries();

  const mut = useMutation({
    mutationFn: ({ file, replace }) => importCSV(file, replace),
    onSuccess: (data) => {
      setResult(data);
      invalidateAll();
    },
    onError: (err) => {
      setResult({ error: err.response?.data?.detail || "Import failed" });
    },
  });

  const clearMut = useMutation({
    mutationFn: clearAllTransactions,
    onSuccess: () => {
      invalidateAll();
      setFile(null);
      setResult(null);
      toast.success("Portfolio cleared");
    },
    onError: (err) =>
      toast.error(err.response?.data?.detail || "Failed to clear portfolio"),
  });

  const handleClear = async () => {
    const ok = await confirm({
      title: "Clear portfolio?",
      message: "All transactions in this portfolio will be permanently deleted. This cannot be undone.",
      confirmLabel: "Delete all",
      danger: true,
    });
    if (ok) clearMut.mutate();
  };

  const onDrop = useCallback((accepted) => {
    if (accepted[0]) {
      setFile(accepted[0]);
      setResult(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "text/csv": [".csv"] },
    multiple: false,
  });

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold">Import CSV</h1>
        <div className="flex gap-2">
          <button
            onClick={handleClear}
            className="btn-ghost flex items-center gap-2 text-sm text-red-600 border-red-200 hover:bg-red-50"
            disabled={clearMut.isPending}
          >
            <Trash2 size={14} />
            {clearMut.isPending ? "Clearing…" : "Clear portfolio"}
          </button>
          <button onClick={downloadSample} className="btn-ghost flex items-center gap-2 text-sm">
            <Download size={14} />
            Download sample
          </button>
        </div>
      </div>

      {/* Supported formats */}
      <div className="card space-y-5">
        <h2 className="font-semibold text-sm text-muted uppercase tracking-wider">
          Supported formats
        </h2>

        {/* Trading 212 */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <FormatBadge label="Trading 212" color="bg-blue-100 text-blue-700" />
            <span className="text-xs text-muted">— auto-detected, drop your export directly</span>
          </div>
          <div className="bg-surface-hover rounded-lg p-3 overflow-x-auto">
            <code className="text-xs text-blue-600 font-mono whitespace-pre">
              {`Action,Time (UTC),ISIN,Ticker,Name,No. of shares,Price / share,Currency (Price / share),…
Market buy,2024-01-15 09:30:00,US0378331005,AAPL,Apple Inc.,10,185.50,USD,…
Market sell,2024-06-01 14:00:00,US0378331005,AAPL,Apple Inc.,3,220.00,USD,…
Dividend (Ordinary),2024-09-15 00:00:00,US5949181045,MSFT,Microsoft,5,0.75,USD,…`}
            </code>
          </div>
          <div className="flex items-start gap-1.5 text-xs text-muted">
            <Info size={12} className="mt-0.5 shrink-0 text-blue-400" />
            <span>
              Imports the full history — trades, deposits, withdrawals, cash and lending
              interest, dividends, ADR fees, stock splits, card debits, cashback and currency
              conversions. <span className="font-medium text-ink">A Trading 212
              import always replaces all existing data for this portfolio</span>, so the cash
              balance reconciles with your broker.
            </span>
          </div>
        </div>

        <div className="border-t border-surface-border" />

        {/* Native */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <FormatBadge label="Native" color="bg-green-100 text-green-700" />
            <span className="text-xs text-muted">— simple format for manual entry or other brokers</span>
          </div>
          <div className="bg-surface-hover rounded-lg p-3 overflow-x-auto">
            <code className="text-xs text-gain font-mono whitespace-pre">
              {`date,ticker,type,shares,price,currency
2024-01-15,AAPL,buy,10,185.50,USD
2024-02-20,MSFT,sell,5,420.00,USD
2024-06-01,AAPL,dividend,10,0.24,USD`}
            </code>
          </div>
          <ul className="text-xs text-muted space-y-1">
            <li><span className="text-ink font-mono">type</span> — <span className="text-gain">buy</span>, <span className="text-loss">sell</span>, or <span className="text-yellow-600">dividend</span></li>
            <li><span className="text-ink font-mono">price</span> — price per share (dividend: amount per share)</li>
            <li><span className="text-ink font-mono">currency</span> — optional, defaults to USD</li>
          </ul>
        </div>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`card border-2 border-dashed cursor-pointer transition-colors flex flex-col items-center justify-center py-12 gap-3 ${
          isDragActive ? "border-brand bg-brand/5" : "border-surface-border hover:border-gray-500"
        }`}
      >
        <input {...getInputProps()} />
        <Upload size={32} className={isDragActive ? "text-brand" : "text-muted"} />
        {file ? (
          <div className="text-center">
            <div className="flex items-center gap-2 text-sm font-medium">
              <FileText size={16} className="text-brand" />
              {file.name}
            </div>
            <p className="text-xs text-muted mt-1">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm font-medium">Drop your CSV here or click to browse</p>
            <p className="text-xs text-muted mt-1">
              Accepts Trading 212 exports or native format
            </p>
          </div>
        )}
      </div>

      {file && !result && (
        <div className="space-y-3">
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={replace}
              onChange={(e) => setReplace(e.target.checked)}
              className="mt-0.5 accent-red-500 w-4 h-4 shrink-0"
            />
            <div>
              <span className="text-sm font-medium group-hover:text-ink transition-colors">
                Replace existing portfolio
              </span>
              <p className="text-xs text-muted mt-0.5">
                Deletes all current transactions before importing. Use this to start fresh with
                your own data. (Trading 212 exports always replace, regardless of this setting.)
              </p>
            </div>
          </label>
          <button
            onClick={() => mut.mutate({ file, replace })}
            className={`w-full font-semibold px-4 py-2 rounded-lg transition-colors ${
              replace
                ? "bg-red-600 hover:bg-red-700 text-white"
                : "btn-primary"
            }`}
            disabled={mut.isPending}
          >
            {mut.isPending
              ? "Importing…"
              : replace
              ? `Replace portfolio with ${file.name}`
              : `Import ${file.name}`}
          </button>
        </div>
      )}

      {result && (
        <div
          className={`card border ${
            result.error ? "border-red-500/40 bg-loss/10" : "border-green-500/40 bg-gain/10"
          }`}
        >
          {result.error ? (
            <div className="flex items-start gap-3">
              <AlertCircle size={18} className="text-loss shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-loss">Import failed</p>
                <p className="text-sm text-loss mt-1">{result.error}</p>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-3">
              <CheckCircle size={18} className="text-gain shrink-0 mt-0.5" />
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-gain">
                    {result.processed_events != null
                      ? `${result.processed_events} event${result.processed_events !== 1 ? "s" : ""} processed (${result.imported} ledger rows)`
                      : `${result.imported} transaction${result.imported !== 1 ? "s" : ""} imported`}
                  </p>
                  {result.format && (
                    <FormatBadge
                      label={result.format}
                      color={
                        result.format === "Trading 212"
                          ? "bg-blue-100 text-blue-700"
                          : "bg-green-100 text-green-700"
                      }
                    />
                  )}
                </div>
                {result.skipped > 0 && (
                  <p className="text-xs text-muted">
                    {result.skipped} non-trade row{result.skipped !== 1 ? "s" : ""} skipped
                    (deposits, withdrawals, cash interest, etc.)
                  </p>
                )}
                {result.errors?.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs text-yellow-600 font-medium">
                      {result.errors.length} row{result.errors.length !== 1 ? "s" : ""} had errors:
                    </p>
                    <ul className="mt-1 space-y-0.5">
                      {result.errors.map((e, i) => (
                        <li key={i} className="text-xs text-muted">• {e}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
          <button
            onClick={() => { setFile(null); setResult(null); }}
            className="mt-3 text-xs text-muted hover:text-ink transition-colors"
          >
            Import another file →
          </button>
        </div>
      )}
    </div>
  );
}
