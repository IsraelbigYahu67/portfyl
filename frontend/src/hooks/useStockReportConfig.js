import { useState, useCallback } from "react";
import { msg } from "../i18n/I18nProvider";

const STORAGE_KEY = "sb_stock_report_sections";
const TAB_STORAGE_KEY = "sb_stock_report_tabs";

export const STOCK_TAB_SECTIONS = {
  overview: ["quickStats"],
  financials: ["financials", "dividendGrowth", "earningsRecap"],
  valuation: ["ratiosAnalyst", "valuationHistory"],
  ownership: [
    "ownership",
    "insiderVolume",
    "insiderTx",
    "politicalTrades",
  ],
};

export const ALL_SECTIONS = [
  { id: "quickStats", label: msg("Quick Stats") },
  { id: "dividendGrowth", label: msg("Dividend History") },
  { id: "financials", label: msg("Financials") },
  { id: "earningsRecap", label: msg("Earnings") },
  { id: "ratiosAnalyst", label: msg("Ratios & Analyst") },
  { id: "valuationHistory", label: msg("Valuation History") },
  { id: "insiderVolume", label: msg("Insider Volume") },
  { id: "insiderTx", label: msg("Insider Transactions") },
  { id: "politicalTrades", label: msg("Political Trades") },
  { id: "ownership", label: msg("Ownership") },
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

export function migrateHiddenSectionsToTabs(stored) {
  const existing = localStorage.getItem(TAB_STORAGE_KEY);
  if (existing != null) {
    try {
      const parsed = JSON.parse(existing);
      return Array.isArray(parsed?.hidden) ? parsed.hidden : [];
    } catch {
      return [];
    }
  }

  const hiddenSections = new Set(stored?.hidden || []);
  const hidden = Object.entries(STOCK_TAB_SECTIONS)
    .filter(([, sections]) => sections.length > 0 && sections.every((id) => hiddenSections.has(id)))
    .map(([tab]) => tab);
  localStorage.setItem(TAB_STORAGE_KEY, JSON.stringify({ version: 1, hidden }));
  return hidden;
}

export default function useStockReportConfig() {
  const [config, setConfig] = useState(() => {
    const stored = load();
    const hiddenTabs = migrateHiddenSectionsToTabs(stored);
    // Drop section ids that no longer exist (e.g. the removed "valuation" models).
    const storedOrder = stored?.order?.filter((id) => DEFAULT_ORDER.includes(id));
    const order = storedOrder
      ? [...storedOrder, ...DEFAULT_ORDER.filter((id) => !storedOrder.includes(id))]
      : DEFAULT_ORDER;
    return {
      order,
      hidden: new Set(stored?.hidden ?? []),
      hiddenTabs: new Set(hiddenTabs),
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
