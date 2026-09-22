import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  connectT212,
  disconnectT212,
  fetchT212HistoryStatus,
  fetchT212Positions,
  fetchT212Status,
  setT212AutoSync,
  syncT212,
} from "../api";
import { usePortfolio } from "../App";

const ACTIVE_HISTORY_STATES = new Set(["pending", "fetching"]);
const LEDGER_QUERY_KEYS = [
  "transactions", "holdings", "holdings-all", "summary", "portfolios",
  "heatmap", "performance", "movers", "earnings", "dividends", "insider-buys",
  "sector-breakdown", "cash", "cash-balance", "cash-history", "cash-reconciliation",
];

export function historyPollInterval(query) {
  const state = query.state.data?.run?.state;
  if (state === "waiting_rate_limit") return 30000;
  return ACTIVE_HISTORY_STATES.has(state) ? 5000 : false;
}

function invalidateKeys(queryClient, keys) {
  keys.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
}

/** Shared Trading 212 server state, scoped to the active portfolio. */
export function useT212Sync({ currency = "USD", includePositions = false, includeHistory = true } = {}) {
  const queryClient = useQueryClient();
  const portfolioId = usePortfolio().current?.id;
  const connectingRef = useRef(false);
  const [connecting, setConnecting] = useState(false);
  const status = useQuery({
    queryKey: ["t212-status", portfolioId],
    queryFn: fetchT212Status,
    enabled: portfolioId != null,
  });
  const connected = status.data?.connected === true;
  const history = useQuery({
    queryKey: ["t212-history-status", portfolioId],
    queryFn: fetchT212HistoryStatus,
    enabled: connected && includeHistory,
    refetchInterval: historyPollInterval,
  });
  const positions = useQuery({
    queryKey: ["t212-positions", portfolioId, currency],
    queryFn: () => fetchT212Positions(currency),
    enabled: connected && includePositions,
  });

  // Credentials must stay out of React Query's mutation cache, which retains
  // mutation variables after the request finishes.
  const connect = {
    isPending: connecting,
    mutate: async ({ apiKey, apiSecret }, callbacks = {}) => {
      if (connectingRef.current) return;
      connectingRef.current = true;
      setConnecting(true);
      try {
        const result = await connectT212(apiKey, apiSecret);
        queryClient.removeQueries({ queryKey: ["t212-positions", portfolioId] });
        queryClient.removeQueries({ queryKey: ["t212-history-status", portfolioId] });
        invalidateKeys(queryClient, ["t212-status", ...LEDGER_QUERY_KEYS]);
        callbacks.onSuccess?.(result);
        return result;
      } catch (error) {
        callbacks.onError?.(error);
        return undefined;
      } finally {
        connectingRef.current = false;
        setConnecting(false);
      }
    },
  };
  const disconnect = useMutation({
    mutationFn: disconnectT212,
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["t212-positions", portfolioId] });
      queryClient.removeQueries({ queryKey: ["t212-history-status", portfolioId] });
      invalidateKeys(queryClient, ["t212-status", ...LEDGER_QUERY_KEYS]);
    },
  });
  const sync = useMutation({
    mutationFn: syncT212,
    onSuccess: (result) => {
      invalidateKeys(queryClient, ["t212-status", "t212-history-status"]);
      if (result.positions_updated) invalidateKeys(queryClient, ["t212-positions"]);
      if (result.cash_updated) invalidateKeys(queryClient, ["cash-reconciliation", "summary", "sector-breakdown"]);
      if (result.total_imported > 0) invalidateKeys(queryClient, LEDGER_QUERY_KEYS);
    },
  });
  const autoSync = useMutation({
    mutationFn: setT212AutoSync,
    onSuccess: () => invalidateKeys(queryClient, ["t212-status"]),
  });

  const run = history.data?.run ?? null;
  const phase = sync.isPending ? "syncing" : !connected ? "disconnected" : run?.state ?? "connected";
  return { status, history, positions, connected, run, phase, connect, disconnect, sync, autoSync };
}
