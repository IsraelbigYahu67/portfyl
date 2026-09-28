import { useCallback, useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchT212HistoryStatus, fetchT212Positions, fetchT212Status, retryT212History, syncT212 } from "../api";

export const T212_HISTORY_ACTIVE_STATES = new Set(["pending", "fetching", "waiting_rate_limit", "finalizing"]);

const SNAPSHOT_CONSUMER_QUERY_KEYS = [
  "cash",
  "cash-balance",
  "cash-reconciliation",
  "holdings",
  "summary",
  "portfolios",
];

const LEDGER_CONSUMER_QUERY_KEYS = [
  "cash",
  "cash-balance",
  "cash-history",
  "cash-reconciliation",
  "transactions",
  "holdings",
  "summary",
  "portfolios",
  "heatmap",
  "performance",
  "movers",
  "earnings",
  "dividends",
  "insider-buys",
];

function historyPollInterval(query) {
  const state = query.state.data?.run?.state;
  if (state === "waiting_rate_limit") return 15000;
  return state && T212_HISTORY_ACTIVE_STATES.has(state) ? 5000 : false;
}

export function useT212Sync({ portfolioId, currency = "USD", enabled = true, includePositions = true }) {
  const queryClient = useQueryClient();
  const invalidatedCompletedRuns = useRef(new Set());
  const canLoad = enabled && portfolioId != null;
  const statusQuery = useQuery({
    queryKey: ["t212-status", portfolioId],
    queryFn: fetchT212Status,
    enabled: canLoad,
  });
  const connected = statusQuery.data?.connected === true;

  const historyQuery = useQuery({
    queryKey: ["t212-history-status", portfolioId],
    queryFn: fetchT212HistoryStatus,
    enabled: canLoad && connected,
    refetchInterval: historyPollInterval,
  });

  const positionsQuery = useQuery({
    queryKey: ["t212-positions", portfolioId, currency],
    queryFn: () => fetchT212Positions(currency),
    enabled: canLoad && connected && includePositions,
  });

  const invalidateKeys = useCallback(
    (keys) => Promise.all(
      keys.map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
    ),
    [queryClient],
  );

  const syncMutation = useMutation({
    mutationFn: syncT212,
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ["t212-status", portfolioId] }),
      queryClient.invalidateQueries({ queryKey: ["t212-history-status", portfolioId] }),
      queryClient.invalidateQueries({ queryKey: ["t212-positions", portfolioId] }),
      invalidateKeys(SNAPSHOT_CONSUMER_QUERY_KEYS),
    ]),
  });

  const retryMutation = useMutation({
    mutationFn: retryT212History,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["t212-history-status", portfolioId] }),
  });

  const historyRun = historyQuery.data?.run ?? null;
  useEffect(() => {
    const runId = historyRun?.id;
    if (!runId || historyRun.state !== "completed" || invalidatedCompletedRuns.current.has(runId)) {
      return;
    }
    invalidatedCompletedRuns.current.add(runId);
    void invalidateKeys(LEDGER_CONSUMER_QUERY_KEYS);
  }, [historyRun?.id, historyRun?.state, invalidateKeys]);

  let phase = "ready";
  if (!canLoad) phase = "idle";
  else if (syncMutation.isPending) phase = "syncing";
  else if (statusQuery.isLoading) phase = "loading";
  else if (statusQuery.isError) phase = "error";
  else if (!connected) phase = "disconnected";
  else if (historyRun && T212_HISTORY_ACTIVE_STATES.has(historyRun.state)) phase = historyRun.state;
  else if (historyRun && ["needs_review", "failed", "cancelled"].includes(historyRun.state)) phase = historyRun.state;
  else if (positionsQuery.data?.status === "stale") phase = "snapshot_stale";
  else if (positionsQuery.data?.status === "unavailable") phase = "snapshot_unavailable";
  else if (historyRun?.state === "completed") phase = "complete";

  return {
    connected,
    statusQuery,
    historyQuery,
    positionsQuery,
    historyRun,
    sync: syncMutation.mutate,
    syncAsync: syncMutation.mutateAsync,
    syncMutation,
    retryHistory: retryMutation.mutate,
    retryPending: retryMutation.isPending,
    phase,
    historyActive: Boolean(historyRun && T212_HISTORY_ACTIVE_STATES.has(historyRun.state)),
  };
}
