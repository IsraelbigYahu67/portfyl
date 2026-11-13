import { useCallback, useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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
import BrokerGuides from "../components/import/BrokerGuides";
import { Badge } from "../components/ui/Badge";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { usePortfolio } from "../App";
import { useBrokerPortfolio } from "../hooks/useBrokerPortfolio";
import { brokerLabel, describeSplit } from "../lib/brokerPortfolio";
import { TRACKER_HOME } from "../lib/routes";
import { findSupportedBroker } from "../lib/onboardingBrokers";
import { useRegisteredActivation } from "../analytics/useRegisteredActivation";
import { msg, rich, useT } from "../i18n/I18nProvider";
// 30 companies across all 11 sectors, real historical prices and dividends.
// A copy of the repo-root sample_portfolio.csv (samplePortfolio.test.js keeps
// the two identical); Vite will not serve the root file in dev or Vitest.
import SAMPLE_NATIVE from "../assets/sample_portfolio.csv?raw";


function downloadSample() {
  const blob = new Blob([SAMPLE_NATIVE], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "sample_portfolio.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

// File formats from backend/importers/formats/ besides T212, Native and IBKR.
const BROKER_FILE_FORMATS = ["Degiro", "XTB", "Charles Schwab", "Fidelity"];

function FormatBadge({ format }) {
  return <Badge tone={format === "Trading 212" ? "brand" : "neutral"}>{format}</Badge>;
}

// Rows the parser recognized but did not import, grouped by reason.
function SkippedReasons({ reasons, total }) {
  const t = useT();
  const entries = Object.entries(reasons ?? {}).filter(([, count]) => count > 0);
  if (entries.length === 0) {
    if (!(total > 0)) return null;
    return (
      <p className="text-muted">
        {total === 1
          ? t("{count} informational row recognized and skipped.", { count: total })
          : t("{count} informational rows recognized and skipped.", { count: total })}
      </p>
    );
  }
  const skipped = entries.reduce((sum, [, count]) => sum + count, 0);
  return (
    <div className="text-muted">
      <p>
        {skipped === 1
          ? t("{count} row recognized and skipped:", { count: skipped })
          : t("{count} rows recognized and skipped:", { count: skipped })}
      </p>
      <ul aria-label={t("Skipped rows")} className="mt-1 list-disc space-y-0.5 pl-5">
        {entries.map(([reason, count]) => (
          <li key={reason}><span className="text-ink">{reason}</span> <span className="tabular-nums">× {count}</span></li>
        ))}
      </ul>
    </div>
  );
}


// Server messages (detail.message, detail.errors) stay as the backend sends them.
function apiError(error, t) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.errors?.length) {
    return `${detail.message || t("Import failed")}: ${detail.errors.join("; ")}`;
  }
  return detail?.message || t("Import failed");
}


const IMPORT_STEPS = [msg("Select source"), msg("Preview changes"), msg("Confirm import"), msg("Result / Undo")];

export default function Import({ focused = false }) {
  const t = useT();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const navigate = useNavigate();
  // ?broker= comes from onboarding: tailor the copy to the broker the user picked.
  const [searchParams] = useSearchParams();
  const broker = findSupportedBroker(searchParams.get("broker"));
  const brokerFile = broker?.fileKind ? `${broker.name} ${broker.fileKind}` : null;
  const { current, pendingImportPortfolio, refetchPortfolios, setCurrentId } = usePortfolio();
  const { recordPortfolioDataImported } = useRegisteredActivation();
  const [file, setFile] = useState(null);
  const [replace, setReplace] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [undoError, setUndoError] = useState(null);
  const [stage, setStage] = useState("select");
  // A new portfolio opened for this file's broker (useBrokerPortfolio), until
  // the import commits; keepCurrent = the user chose the original portfolio.
  const [split, setSplit] = useState(null);
  const keepCurrentRef = useRef(false);
  const brokerPortfolio = useBrokerPortfolio();
  const splitRef = useRef(null);
  splitRef.current = split;
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
    mutationFn: async () => {
      let data = await previewImportCSV(file, replace);
      if (!keepCurrentRef.current && !splitRef.current && data.broker) {
        const session = await brokerPortfolio.open(data.broker);
        if (session?.created) {
          setSplit(session);
          splitRef.current = session;
          // The new portfolio is empty: append, nothing to replace.
          data = await previewImportCSV(file, false);
        } else if (session?.blocked) {
          data = { ...data, split_blocked: session };
        }
      }
      return data;
    },
    onSuccess: (data) => {
      setPreview(data);
      setResult(null);
      setError(null);
      setStage("preview");
    },
    onError: (err) => {
      setPreview(null);
      setError(apiError(err, t));
    },
  });

  const commitMutation = useMutation({
    mutationFn: () => commitImportCSV(file, preview.preview_id, replace),
    onSuccess: (data) => {
      setResult({ ...data, portfolio_name: splitRef.current?.created?.name ?? null });
      setSplit(null);
      splitRef.current = null;
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
        setError(t("The portfolio changed. Preview the file again."));
      } else {
        setStage("confirm");
        setError(apiError(err, t));
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
      toast.success(t("Last import undone"));
    },
    onError: (err) => {
      const message = apiError(err, t);
      setUndoError(message);
      toast.error(message);
    },
  });

  async function handleUndo() {
    const accepted = await confirm({
      title: t("Undo last import?"),
      message: t("Portfyl will restore the portfolio exactly as it was before the last import."),
      confirmLabel: t("Undo import"),
    });
    if (accepted) undoMutation.mutate();
  }

  const discardSplit = useCallback(() => {
    const session = splitRef.current;
    setSplit(null);
    splitRef.current = null;
    if (session) brokerPortfolio.discard(session).catch(() => {});
  }, [brokerPortfolio]);

  // Leaving the page before committing must not leave an empty portfolio behind.
  useEffect(() => () => {
    if (splitRef.current) brokerPortfolio.discard(splitRef.current).catch(() => {});
  }, [brokerPortfolio]);

  const onDrop = useCallback((accepted) => {
    if (!accepted[0]) return;
    discardSplit();
    keepCurrentRef.current = false;
    setFile(accepted[0]);
    setPreview(null);
    setResult(null);
    setError(null);
    setStage("select");
  }, [discardSplit]);

  useEffect(() => {
    if (!result) return;
    refetchPortfolios();
  }, [result, refetchPortfolios]);

  const cancelPreview = () => {
    discardSplit();
    setPreview(null);
    setError(null);
    setStage("select");
  };

  const importIntoOriginal = async () => {
    const session = splitRef.current;
    setSplit(null);
    splitRef.current = null;
    keepCurrentRef.current = true;
    setPreview(null);
    if (session) await brokerPortfolio.discard(session).catch(() => {});
    previewMutation.mutate();
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
    // .xml: Interactive Brokers Activity Flex statements; .xlsx: XTB.
    accept: {
      "text/csv": [".csv"],
      "application/xml": [".xml"],
      "text/xml": [".xml"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
    multiple: false,
  });

  const duplicateCount = preview
    ? preview.counts.duplicates_in_file
      + (preview.mode === "append" ? preview.counts.duplicates_existing : 0)
    : 0;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold">{broker ? (brokerFile ? t("Import your {broker} file", { broker: broker.name }) : t("Import a Portfyl CSV")) : t("Import transactions")}</h1>
          <p className="text-xs text-muted mt-1">{t("Preview every change before it reaches your portfolio.")}</p>
          {broker?.hint && <p className="text-xs text-muted mt-1">{t(broker.hint)}</p>}
        </div>
        <div className="flex gap-2">
          {(focused || onboardingPending) && <button type="button" onClick={() => navigate(broker ? `/onboarding?broker=${broker.key}` : "/onboarding")} className="btn-ghost text-sm">{t("Leave import")}</button>}
          <button onClick={downloadSample} className="btn-ghost flex items-center gap-2 text-sm">
            <Download size={14} /> {t("Download sample")}
          </button>
        </div>
      </div>

      <ol
        aria-label={t("Import progress")}
        className="grid grid-cols-2 gap-1 rounded-3xl p-1 sm:grid-cols-4 sm:rounded-full"
        style={{ background: "var(--bg-subtle, var(--surface-hover))", boxShadow: "var(--clay-inset-sm, none)" }}
      >
        {IMPORT_STEPS.map((label, index) => {
          const current = index === stageIndex;
          return (
            <li
              key={label}
              aria-current={current ? "step" : undefined}
              className={`flex min-h-[44px] items-center justify-center rounded-full px-3 py-2 text-center text-xs md:min-h-0 ${
                current ? "bg-surface-card-elevated font-semibold text-brand" : index < stageIndex ? "font-medium text-gain" : "font-medium text-muted"
              }`}
              style={current ? { boxShadow: "var(--clay-raise-sm, none)" } : undefined}
            >
              <span><span className="mr-1 tabular-nums">{index + 1}.</span>{t(label)}</span>
            </li>
          );
        })}
      </ol>

      {undo?.available && (
        <section className="card border border-brand/30 bg-brand/5 flex items-start justify-between gap-4" aria-label={t("Import recovery")}>
          <div className="flex items-start gap-3">
            <RotateCcw size={18} className="text-brand mt-0.5 shrink-0" />
            <div>
              <p className="font-semibold text-sm">{t("Your last import can be undone")}</p>
              <p className="text-xs text-muted mt-1">
                {t("Available until {time} unless the portfolio changes.", { time: new Date(undo.expires_at).toLocaleString() })}
              </p>
            </div>
          </div>
          <button onClick={handleUndo} className="btn-ghost text-sm shrink-0" disabled={undoMutation.isPending}>
            {undoMutation.isPending ? t("Restoring…") : t("Undo last import")}
          </button>
        </section>
      )}
      {undoError && <p role="alert" className="text-sm text-loss">{t("Undo was not applied: {reason}", { reason: undoError })}</p>}

      {stage === "select" && <>
      <section className="card space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <FormatBadge format="Trading 212" />
          <FormatBadge format={t("Native")} />
          <FormatBadge format="Interactive Brokers (Flex XML)" />
          {BROKER_FILE_FORMATS.map((name) => <FormatBadge key={name} format={name} />)}
          <span className="text-xs text-muted">{t("Auto-detected · maximum 5 MiB")}</span>
        </div>
        <div className="flex items-start gap-2 text-xs text-muted">
          <Info size={14} className="text-brand mt-0.5 shrink-0" />
          <p>
            {t("Trading 212 exports include the full account history and therefore replace this portfolio. Native CSV files can append new rows or replace the portfolio. Exports from Degiro, XTB, Charles Schwab and Fidelity add new rows; rows already in the portfolio are skipped.")}
          </p>
        </div>
        <div className="flex items-start gap-2 text-xs text-muted">
          <Info size={14} className="text-brand mt-0.5 shrink-0" />
          <p>
            {rich(
              t("Interactive Brokers Activity Flex XML statements (.xml) add stocks, ETFs, dividends and cash; rows already in the portfolio are skipped. A Flex statement covers at most 365 days, so for older history upload one XML per year. The Flex Query setup is in <link>Settings → Connections</link>."),
              { link: (words) => <Link to="/settings?section=connections" className="text-brand underline">{words}</Link> },
            )}
          </p>
        </div>
      </section>

      <div className={`grid gap-6 xl:items-start ${file ? "" : "xl:grid-cols-2"}`}>
      <div className="space-y-6">
      <div
        {...getRootProps()}
        className={`card border-2 border-dashed cursor-pointer transition-colors flex flex-col items-center justify-center py-10 gap-3 ${
          isDragActive ? "border-brand bg-brand/5" : "border-surface-border hover:border-brand"
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
            <p className="text-sm font-medium">
              {brokerFile
                ? t("Drop your {broker} {fileKind} file here or click to browse", { broker: broker.name, fileKind: broker.fileKind })
                : t("Drop your broker export (CSV, XML or XLSX) here or click to browse")}
            </p>
            <p className="text-xs text-muted mt-1">{t("Nothing is saved until you review and confirm.")}</p>
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
              className="mt-0.5 accent-brand w-4 h-4"
            />
            <span>
              <span className="text-sm font-medium">{t("Replace existing portfolio")}</span>
              <span className="block text-xs text-muted mt-0.5">{t("The preview will show exactly what would be removed.")}</span>
            </span>
          </label>
          <button onClick={() => previewMutation.mutate()} className="btn-primary w-full" disabled={previewMutation.isPending}>
            {previewMutation.isPending ? t("Preparing preview…") : t("Preview import")}
          </button>
        </div>
      )}

      </div>

      {!file && <BrokerGuides initialOpen={broker?.key} />}
      </div>
      </>}

      {preview && stage === "preview" && (
        <section className={`card border space-y-4 ${preview.mode === "replace" ? "border-loss/40" : "border-brand/30"}`} aria-label={t("Import preview")}>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">{t("Review changes")}</h2>
              <FormatBadge format={preview.format} />
            </div>
            <button onClick={cancelPreview} className="text-xs text-muted hover:text-ink">{t("Cancel preview")}</button>
          </div>

          {split?.created && (
            <div role="status" aria-label={t("New portfolio")} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-brand/30 bg-brand/5 p-3 text-sm">
              <div className="flex items-start gap-2">
                <Info size={16} className="text-brand mt-0.5 shrink-0" />
                <p>{describeSplit(split.previous, split.created, preview.broker, t)}</p>
              </div>
              <button type="button" onClick={importIntoOriginal} className="btn-ghost text-xs shrink-0">
                {t("Import into “{name}” instead", { name: split.previous.name })}
              </button>
            </div>
          )}
          {preview.split_blocked && (
            <div role="status" aria-label={t("New portfolio not available")} className="flex items-start gap-2 rounded-lg border border-surface-border bg-surface-hover p-3 text-sm text-muted">
              <Info size={16} className="text-brand mt-0.5 shrink-0" />
              <p>
                {t("“{previous}” already holds other data, and a separate {broker} portfolio could not be created ({reason}). This import goes into “{previous}”.", {
                  previous: preview.split_blocked.previous.name,
                  broker: brokerLabel(preview.broker),
                  reason: preview.split_blocked.blocked,
                })}
              </p>
            </div>
          )}

          {preview.mode === "replace" && (
            <div className="rounded-lg bg-loss/10 border border-loss/30 p-3 text-sm">
              <p className="font-semibold text-loss">
                {preview.format === "Trading 212"
                  ? t("Trading 212 exports replace the full portfolio when detected.")
                  : t("This import replaces the full portfolio.")}
              </p>
              <p className="text-muted mt-1">
                {preview.counts.removed === 1
                  ? t("{count} current transaction will be removed. You can undo for 24 hours if the portfolio stays unchanged.", { count: 1 })
                  : t("{count} current transactions will be removed. You can undo for 24 hours if the portfolio stays unchanged.", { count: preview.counts.removed })}
              </p>
              {preview.counts.notes_removed > 0 && (
                <p className="text-muted mt-1">
                  {preview.counts.notes_removed === 1
                    ? t("{count} trade note will be removed with those transactions and restored by undo.", { count: 1 })
                    : t("{count} trade notes will be removed with those transactions and restored by undo.", { count: preview.counts.notes_removed })}
                </p>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">{t("Current")}</p><p className="font-bold">{preview.counts.current}</p></div>
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">{t("Added")}</p><p className="font-bold text-gain">+{preview.counts.added}</p></div>
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">{t("Removed")}</p><p className="font-bold text-loss">−{preview.counts.removed}</p></div>
            <div className="bg-surface-hover rounded-lg p-3"><p className="text-xs text-muted">{t("After import")}</p><p className="font-bold">{preview.counts.projected}</p></div>
          </div>

          <div className="text-sm space-y-1">
            <p>
              {preview.counts.added === 1
                ? t("{count} transaction will be added.", { count: 1 })
                : t("{count} transactions will be added.", { count: preview.counts.added })}
            </p>
            {duplicateCount > 0 && (
              <p className="text-muted">
                {duplicateCount === 1
                  ? t("{count} exact duplicate will be skipped.", { count: 1 })
                  : t("{count} exact duplicates will be skipped.", { count: duplicateCount })}
              </p>
            )}
            <SkippedReasons reasons={preview.skipped_reasons} total={preview.counts.skipped} />
          </div>

          {preview.sample.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-muted">
                  <tr><th className="text-left py-2">{t("Date")}</th><th className="text-left">{t("Ticker")}</th><th className="text-left">{t("Type")}</th><th className="text-right">{t("Shares")}</th><th className="text-right">{t("Price")}</th></tr>
                </thead>
                <tbody>
                  {preview.sample.map((row, index) => (
                    <tr key={`${row.date}-${row.ticker}-${index}`} className="border-t border-surface-border">
                      <td className="py-2">{row.date}</td><td>{row.ticker || t("Cash")}</td><td>{row.type}</td><td className="text-right">{row.shares}</td><td className="text-right">{row.price} {row.currency}</td>
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
            {t("Continue to confirm")}
          </button>
        </section>
      )}

      {preview && stage === "confirm" && (
        <section className={`card space-y-4 border ${preview.mode === "replace" ? "border-loss/40" : "border-brand/30"}`} aria-label={t("Confirm import")}>
          <div>
            <h2 className="font-semibold">{t("Confirm import")}</h2>
            <p className="mt-1 text-sm text-muted">
              {(() => {
                const counts = {
                  added: preview.counts.added,
                  removed: preview.counts.removed,
                  duplicates: duplicateCount,
                  total: preview.counts.projected,
                };
                return preview.mode === "replace"
                  ? t("Replace mode · added {added} · removed {removed} · duplicates skipped {duplicates} · {total} in total after import.", counts)
                  : t("Append mode · added {added} · removed {removed} · duplicates skipped {duplicates} · {total} in total after import.", counts);
              })()}
            </p>
          </div>
          <div className="flex gap-3">
            <button type="button" onClick={() => setStage("preview")} className="btn-ghost flex-1" disabled={commitMutation.isPending}>{t("Back to preview")}</button>
            <button type="button" onClick={() => commitMutation.mutate()} className={`flex-1 ${preview.mode === "replace" ? "btn-primary !bg-loss hover:!opacity-90" : "btn-primary"}`} disabled={commitMutation.isPending}>
              {commitMutation.isPending
                ? t("Importing…")
                : preview.mode === "replace"
                  ? (preview.counts.projected === 1
                    ? t("Replace portfolio with {count} transaction", { count: 1 })
                    : t("Replace portfolio with {count} transactions", { count: preview.counts.projected }))
                  : (preview.counts.added === 1
                    ? t("Import {count} transaction", { count: 1 })
                    : t("Import {count} transactions", { count: preview.counts.added }))}
            </button>
          </div>
        </section>
      )}

      {error && (
        <div role="alert" className="card border border-loss/40 bg-loss/10 flex items-start gap-3">
          <AlertCircle size={18} className="text-loss mt-0.5 shrink-0" />
          <div><p className="font-semibold text-loss">{t("Import not applied")}</p><p className="text-sm text-loss mt-1">{error}</p></div>
        </div>
      )}

      {result && stage === "result" && (
        <div className="card border border-gain/40 bg-gain/10 flex items-start gap-3">
          <CheckCircle size={18} className="text-gain mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="font-semibold text-gain">
              {result.portfolio_name
                ? (result.imported === 1
                  ? t("{count} transaction imported into the new portfolio “{name}”", { count: 1, name: result.portfolio_name })
                  : t("{count} transactions imported into the new portfolio “{name}”", { count: result.imported, name: result.portfolio_name }))
                : (result.imported === 1
                  ? t("{count} transaction imported", { count: 1 })
                  : t("{count} transactions imported", { count: result.imported }))}
            </p>
            {result.duplicates_skipped > 0 && (
              <p className="text-xs text-muted mt-1">
                {result.duplicates_skipped === 1
                  ? t("{count} exact duplicate skipped.", { count: 1 })
                  : t("{count} exact duplicates skipped.", { count: result.duplicates_skipped })}
              </p>
            )}
            {result.removed > 0 && (
              <p className="text-xs text-muted mt-1">
                {result.removed === 1
                  ? t("{count} previous transaction removed.", { count: 1 })
                  : t("{count} previous transactions removed.", { count: result.removed })}
              </p>
            )}
            {result.undo?.available && <p className="mt-1 text-xs text-muted">{t("Undo available until {time}.", { time: new Date(result.undo.expires_at).toLocaleString() })}</p>}
            <button type="button" onClick={viewPortfolio} className="btn-primary mt-3 text-sm">{t("View portfolio")}</button>
            <button onClick={() => { setFile(null); setResult(null); setStage("select"); }} className="mt-3 text-xs text-muted hover:text-ink">{t("Import another file →")}</button>
            <Link to="/settings?section=data" className="ml-4 mt-3 inline-block text-xs text-muted hover:text-ink">{t("Manage portfolio data")}</Link>
          </div>
        </div>
      )}
    </div>
  );
}
