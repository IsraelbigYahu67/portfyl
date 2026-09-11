import { useQuery } from "@tanstack/react-query";
import { fetchSummary, fetchT212Status } from "../api";
import { useCurrency, usePortfolio, usePlatform } from "../App";
import { TrendingUp, TrendingDown, BarChart3, Settings } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { TRACKER_HOME } from "../lib/routes";

export default function PlatformLanding() {
  const { currency } = useCurrency();
  const { current: portfolio } = usePortfolio();
  const { setPlatform } = usePlatform();
  const navigate = useNavigate();

  const { data: t212Status } = useQuery({
    queryKey: ["t212-status", portfolio?.id],
    queryFn: fetchT212Status,
    enabled: portfolio?.id != null,
  });

  const { data: equitySummary } = useQuery({
    queryKey: ["summary", currency],
    queryFn: () => fetchSummary(currency),
    enabled: t212Status?.connected === true,
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

  const noneConnected = !t212Status?.connected;

  function selectPlatform(key) {
    setPlatform(key);
    navigate(TRACKER_HOME);
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
      </div>
    </div>
  );
}
