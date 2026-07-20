import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSummary, fetchOptionsSummary, fetchT212Status, fetchIBKRStatus, fetchPolymarketStatus, fetchPolymarketSummary } from "../api";
import { useCurrency, usePortfolio, usePlatform } from "../App";
import { TrendingUp, TrendingDown, BarChart3, Target, Settings, Plus, X, Hexagon } from "lucide-react";
import { useNavigate } from "react-router-dom";

const AVAILABLE_CONNECTORS = [
  {
    key: "ibkr",
    name: "Interactive Brokers",
    subtitle: "Options & futures trading via Flex Web Service",
    icon: Target,
    ready: true,
  },
  {
    key: "polymarket",
    name: "Polymarket",
    subtitle: "Prediction market positions & P&L",
    icon: Hexagon,
    ready: true,
  },
];

export default function PlatformLanding() {
  const { currency } = useCurrency();
  const { current: portfolio } = usePortfolio();
  const { setPlatform } = usePlatform();
  const navigate = useNavigate();
  const [showAddModal, setShowAddModal] = useState(false);

  const { data: t212Status } = useQuery({
    queryKey: ["t212-status", portfolio?.id],
    queryFn: fetchT212Status,
    enabled: portfolio?.id != null,
  });

  const { data: ibkrStatus } = useQuery({
    queryKey: ["ibkr-status", portfolio?.id],
    queryFn: fetchIBKRStatus,
    enabled: portfolio?.id != null,
  });

  const { data: polyStatus } = useQuery({
    queryKey: ["polymarket-status", portfolio?.id],
    queryFn: fetchPolymarketStatus,
    enabled: portfolio?.id != null,
  });

  const { data: polymarketSummary } = useQuery({
    queryKey: ["polymarket-summary"],
    queryFn: fetchPolymarketSummary,
    enabled: polyStatus?.connected === true,
  });

  const { data: equitySummary } = useQuery({
    queryKey: ["summary", currency],
    queryFn: () => fetchSummary(currency),
    enabled: t212Status?.connected === true,
  });

  const { data: optionsSummary } = useQuery({
    queryKey: ["options-summary"],
    queryFn: fetchOptionsSummary,
    enabled: ibkrStatus?.connected === true,
  });

  const fmt = (n) => {
    if (n == null) return "—";
    const sign = n < 0 ? "-" : n > 0 ? "+" : "";
    const str = Math.abs(n).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return currency === "CZK" ? `${sign}${str} Kc` : `${sign}$${str}`;
  };

  const platforms = [];

  if (t212Status?.connected) {
    platforms.push({
      key: "t212",
      name: "Trading 212",
      subtitle: "Equities & ETFs",
      icon: BarChart3,
      value: equitySummary?.total_value,
      pnl: equitySummary?.total_pnl,
      metric: equitySummary?.holdings_count != null ? `${equitySummary.holdings_count} holdings` : null,
    });
  }

  if (ibkrStatus?.connected) {
    platforms.push({
      key: "ibkr",
      name: "Interactive Brokers",
      subtitle: "Options Trading",
      icon: Target,
      value: null,
      pnl: optionsSummary?.total_pnl,
      metric: optionsSummary?.total_trades != null ? `${optionsSummary.total_trades} trades | WR ${optionsSummary.win_rate?.toFixed(0)}%` : null,
    });
  }

  if (polyStatus?.connected) {
    platforms.push({
      key: "polymarket",
      name: "Polymarket",
      subtitle: "Prediction Markets",
      icon: Hexagon,
      value: polymarketSummary?.total_value,
      pnl: polymarketSummary?.total_pnl,
      metric: polymarketSummary?.open_positions != null ? `${polymarketSummary.open_positions} open positions` : null,
    });
  }

  const noneConnected = !t212Status?.connected && !ibkrStatus?.connected && !polyStatus?.connected;

  function selectPlatform(key) {
    setPlatform(key);
    navigate("/");
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8 pt-8">
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold">{portfolio?.name ?? "Portfolio"}</h1>
        <p className="text-sm text-muted">Select a platform to view</p>
      </div>

      {noneConnected && (
        <div className="text-center py-12 space-y-4">
          <p className="text-muted">No platforms connected yet.</p>
          <button
            onClick={() => { setPlatform("t212"); navigate("/settings"); }}
            className="inline-flex items-center gap-2 bg-brand text-white font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand-hover transition-colors"
          >
            <Settings size={16} />
            Go to Settings
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {platforms.map((p) => {
          const Icon = p.icon;
          const pnlPositive = p.pnl != null && p.pnl >= 0;
          return (
            <button
              key={p.key}
              onClick={() => selectPlatform(p.key)}
              className="group text-left bg-surface-card border border-surface-border rounded-xl p-6 hover:border-brand hover:shadow-md transition-all"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-brand/10 flex items-center justify-center">
                    <Icon size={20} className="text-brand" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-ink group-hover:text-brand transition-colors">
                      {p.name}
                    </h3>
                    <p className="text-xs text-muted">{p.subtitle}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                {p.value != null && (
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-muted">Value</span>
                    <span className="font-bold text-ink tabular-nums">{fmt(p.value)}</span>
                  </div>
                )}
                {p.pnl != null && (
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-muted">P&L</span>
                    <span className={`font-bold tabular-nums flex items-center gap-1 ${pnlPositive ? "text-gain" : "text-loss"}`}>
                      {pnlPositive ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                      {fmt(p.pnl)}
                    </span>
                  </div>
                )}
                {p.metric && (
                  <div className="pt-1 border-t border-surface-border">
                    <span className="text-xs text-muted">{p.metric}</span>
                  </div>
                )}
              </div>
            </button>
          );
        })}

        {/* Add connector card */}
        <button
          onClick={() => setShowAddModal(true)}
          className="group flex flex-col items-center justify-center gap-3 border-2 border-dashed border-surface-border rounded-xl p-6 hover:border-brand hover:bg-brand/5 transition-all min-h-[140px]"
        >
          <div className="w-10 h-10 rounded-lg bg-surface-hover group-hover:bg-brand/10 flex items-center justify-center transition-colors">
            <Plus size={20} className="text-muted group-hover:text-brand transition-colors" />
          </div>
          <span className="text-sm font-medium text-muted group-hover:text-brand transition-colors">
            Add connector
          </span>
        </button>
      </div>

      {/* Add connector modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface-card border border-surface-border rounded-xl shadow-xl w-full max-w-md p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Add connector</h2>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-muted hover:text-ink transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <p className="text-sm text-muted">
              Choose a platform to connect to <span className="font-medium text-ink">{portfolio?.name}</span>
            </p>

            <div className="space-y-2">
              {AVAILABLE_CONNECTORS.map((c) => {
                const Icon = c.icon;
                const alreadyConnected =
                  (c.key === "ibkr" && ibkrStatus?.connected) ||
                  (c.key === "polymarket" && polyStatus?.connected) ||
                  (c.key === "t212" && t212Status?.connected);

                return (
                  <button
                    key={c.key}
                    disabled={!c.ready || alreadyConnected}
                    onClick={() => {
                      setShowAddModal(false);
                      if (c.key === "ibkr") {
                        setPlatform("ibkr");
                        navigate("/settings");
                      } else if (c.key === "polymarket") {
                        setPlatform("polymarket");
                        navigate("/settings");
                      }
                    }}
                    className={`w-full flex items-center gap-3 p-4 rounded-lg border text-left transition-all ${
                      !c.ready
                        ? "border-surface-border bg-surface-hover opacity-60 cursor-not-allowed"
                        : alreadyConnected
                        ? "border-gain/30 bg-gain/10 cursor-not-allowed"
                        : "border-surface-border bg-surface-card hover:border-brand hover:shadow-sm cursor-pointer"
                    }`}
                  >
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                      alreadyConnected ? "bg-gain/10" : "bg-brand/10"
                    }`}>
                      <Icon size={18} className={alreadyConnected ? "text-gain" : "text-brand"} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-ink">{c.name}</span>
                        {!c.ready && (
                          <span className="text-[10px] font-medium bg-surface-hover text-muted px-1.5 py-0.5 rounded">
                            Coming soon
                          </span>
                        )}
                        {alreadyConnected && (
                          <span className="text-[10px] font-medium bg-gain/10 text-gain px-1.5 py-0.5 rounded">
                            Connected
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted mt-0.5">{c.subtitle}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
