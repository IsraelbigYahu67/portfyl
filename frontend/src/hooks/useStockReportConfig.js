import { useState, useCallback } from "react";

const STORAGE_KEY = "sb_stock_report_sections";

export const ALL_SECTIONS = [
  { id: "quickStats", label: "Quick Stats" },
  { id: "weekRange", label: "52-Week Range" },
  { id: "financials", label: "Financials" },
  { id: "ratiosAnalyst", label: "Ratios & Analyst" },
  { id: "insiderVolume", label: "Insider Volume" },
  { id: "insiderTx", label: "Insider Transactions" },
  { id: "valuation", label: "Valuation Models" },
  { id: "ownership", label: "Ownership" },
];

const DEFAULT_ORDER = ALL_SECTIONS.map((s) => s.id);

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function save(config) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

export default function useStockReportConfig() {
  const [config, setConfig] = useState(() => {
    const stored = load();
    return {
      order: stored?.order ?? DEFAULT_ORDER,
      hidden: new Set(stored?.hidden ?? []),
    };
  });

  const persist = useCallback((next) => {
    setConfig(next);
    save({ order: next.order, hidden: [...next.hidden] });
  }, []);

  const toggle = useCallback(
    (id) => {
      const next = { ...config, hidden: new Set(config.hidden) };
      if (next.hidden.has(id)) next.hidden.delete(id);
      else next.hidden.add(id);
      persist(next);
    },
    [config, persist],
  );

  const moveUp = useCallback(
    (id) => {
      const idx = config.order.indexOf(id);
      if (idx <= 0) return;
      const next = [...config.order];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      persist({ ...config, hidden: new Set(config.hidden), order: next });
    },
    [config, persist],
  );

  const moveDown = useCallback(
    (id) => {
      const idx = config.order.indexOf(id);
      if (idx < 0 || idx >= config.order.length - 1) return;
      const next = [...config.order];
      [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      persist({ ...config, hidden: new Set(config.hidden), order: next });
    },
    [config, persist],
  );

  const reset = useCallback(() => {
    persist({ order: DEFAULT_ORDER, hidden: new Set() });
  }, [persist]);

  const isVisible = useCallback(
    (id) => !config.hidden.has(id),
    [config.hidden],
  );

  return { config, toggle, moveUp, moveDown, reset, isVisible };
}
