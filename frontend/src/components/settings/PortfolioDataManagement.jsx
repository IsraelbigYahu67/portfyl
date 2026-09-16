import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";

import { clearAllTransactions } from "../../api";
import { usePortfolio } from "../../App";
import { getApiErrorMessage } from "../../lib/apiError";
import { useConfirm } from "../ui/ConfirmDialog";
import { useToast } from "../ui/Toast";

export const PORTFOLIO_DATA_QUERY_KEYS = [
  "transactions-page",
  "transactions",
  "holdings",
  "summary",
  "performance",
  "dividends",
  "dividends-forecast",
  "dividend-growth",
  "tax-report",
  "risk-metrics",
  "benchmark-comparison",
  "correlation",
  "portfolios",
  "import-undo",
];

export default function PortfolioDataManagement() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const { current } = usePortfolio();
  const [notice, setNotice] = useState(null);

  const clearMutation = useMutation({
    mutationFn: clearAllTransactions,
    onSuccess: () => {
      PORTFOLIO_DATA_QUERY_KEYS.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
      const message = `${current?.name || "Portfolio"} was cleared.`;
      setNotice({ type: "success", message });
      toast.success(message);
    },
    onError: (error) => {
      const message = getApiErrorMessage(error, "Could not clear this portfolio");
      setNotice({ type: "error", message });
      toast.error(message);
    },
  });

  const requestClear = async () => {
    const accepted = await confirm({
      title: `Clear ${current?.name || "portfolio"}?`,
      message: "All transactions, holdings derived from them, and import recovery data in this portfolio will be permanently removed. The portfolio, broker connection, and workspace will remain.",
      confirmLabel: "Clear portfolio",
      danger: true,
    });
    if (accepted) clearMutation.mutate();
  };

  if (!current) return null;

  return (
    <section aria-labelledby="portfolio-data-management-heading" className="space-y-4 rounded-xl border border-surface-border bg-surface-card p-6">
      <div>
        <h3 id="portfolio-data-management-heading" className="text-lg font-semibold">Portfolio data</h3>
        <p className="mt-1 text-sm text-muted">Clear imported and manually entered transactions from <span className="font-medium text-ink">{current.name}</span> without deleting the portfolio, broker credentials, or workspace.</p>
      </div>

      {notice && <p role={notice.type === "error" ? "alert" : "status"} className={notice.type === "error" ? "text-sm text-loss" : "text-sm text-gain"}>{notice.message}</p>}

      <button type="button" onClick={requestClear} disabled={clearMutation.isPending} className="flex items-center gap-2 rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-40">
        {clearMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
        {clearMutation.isPending ? "Clearing…" : "Clear portfolio"}
      </button>
    </section>
  );
}
