import { useState, useEffect, useCallback } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import {
  GripVertical, X, Plus, RotateCcw, ChevronUp, ChevronDown,
  Activity, TrendingUp, PieChart, Coins, LayoutGrid, UserCheck,
} from "lucide-react";
import "react-grid-layout/css/styles.css";
import { useIsPhone } from "../hooks/useMediaQuery";
import { MergedTitleContext } from "./ui/SectionHeader";

const ResponsiveGridLayout = WidthProvider(Responsive);

// Layout v3 / order v4 keys: insider activity moved up to sit full-width
// between composition and the top-holdings row, so orders and grid
// coordinates saved for the previous arrangement start fresh instead of
// keeping insider activity beside composition. The standalone insiderBuys
// widget has since been folded into the concentration row (it replaced Top
// 10 Holdings); normalizeWidgetOrder drops its stale stored id.
const STORAGE_KEY = "sb_dashboard_layout_v3";
// Order-first persistence: the widget sequence is the source of truth, and
// desktop drag/resize coordinates are an optional decoration on top of it.
const ORDER_KEY = "sb_dashboard_widget_order_v4";
const HIDDEN_KEY = "sb_dashboard_widgets_hidden";
// Phones: only the core widgets start open, everything else is a collapsed row
// so the page is a few screens, not a dozen. What the user opens is remembered.
const PHONE_OPEN_KEY = "sb_dashboard_phone_open_v1";
const PHONE_CORE = ["movers"];

// `icon` is the tile shown on a phone's collapsible row (the same icon the
// widget's own small heading used to carry). `mergeTitle` drops that small
// heading inside the opened card; the two-card widgets (movers, dividends) keep
// theirs because each heading tells its card from the other.
const ALL_WIDGETS = [
  { id: "attention", label: "Attention signals", icon: Activity, mergeTitle: true, minW: 3, minH: 3 },
  { id: "performance", label: "Performance", icon: TrendingUp, mergeTitle: true, minW: 3, minH: 4 },
  { id: "composition", label: "Portfolio composition", icon: PieChart, mergeTitle: true, minW: 3, minH: 4 },
  { id: "concentration", label: "Insider buys & heatmap", icon: LayoutGrid, minW: 3, minH: 4 },
  { id: "movers", label: "Movers & earnings", icon: Activity, minW: 4, minH: 4 },
  { id: "dividends", label: "Dividends", icon: Coins, minW: 3, minH: 4 },
];

const KNOWN_IDS = ALL_WIDGETS.map((w) => w.id);

// Phones only: the concentration row is split into one collapsible row per
// card, because a heatmap and an insider table are two different things to
// open. The page supplies them as extra children (heatmap + insiderBuys, or
// topHoldings when insider data is not on the plan); desktop keeps the pair.
const PHONE_SPLIT = [
  { id: "heatmap", label: "Heatmap", icon: LayoutGrid, mergeTitle: true },
  { id: "insiderBuys", label: "Insider buys", icon: UserCheck, mergeTitle: true },
  { id: "topHoldings", label: "Top 10 holdings", icon: PieChart, mergeTitle: true },
];
const PHONE_WIDGETS = [...ALL_WIDGETS, ...PHONE_SPLIT];
const PHONE_KNOWN_IDS = PHONE_WIDGETS.map((w) => w.id);

// The widget rows a phone shows, in order: the heatmap first (it sits right
// under the net worth / profit / passive income block), then the core widget,
// then the rest in the saved sequence.
export function phoneWidgetOrder(visible, children) {
  const split = PHONE_SPLIT.filter((w) => children[w.id] != null).map((w) => w.id);
  const expanded = visible.flatMap((id) => (id === "concentration" && split.length > 1 ? split : [id]));
  const rank = (id) => (id === "heatmap" ? 0 : PHONE_CORE.includes(id) ? 1 : 2);
  return expanded
    .map((id, index) => ({ id, index }))
    .sort((a, b) => rank(a.id) - rank(b.id) || a.index - b.index)
    .map((entry) => entry.id);
}

const DEFAULT_LAYOUTS = {
  lg: [
    { i: "attention", x: 0, y: 0, w: 6, h: 4 },
    { i: "performance", x: 0, y: 4, w: 6, h: 5 },
    { i: "composition", x: 0, y: 9, w: 6, h: 5 },
    { i: "concentration", x: 0, y: 14, w: 6, h: 5 },
    { i: "movers", x: 0, y: 19, w: 6, h: 5 },
    { i: "dividends", x: 0, y: 24, w: 6, h: 5 },
  ],
};

// Stored ids that no longer exist are dropped, duplicates removed, and every
// known widget appended in its default position — so a layout saved by an
// older build silently migrates instead of rendering holes.
export function normalizeWidgetOrder(stored, knownIds) {
  const valid = (Array.isArray(stored) ? stored : []).filter(
    (id, index, all) => knownIds.includes(id) && all.indexOf(id) === index
  );
  return [...valid, ...knownIds.filter((id) => !valid.includes(id))];
}

export function swapLayoutPositions(layouts, firstId, secondId) {
  return Object.fromEntries(
    Object.entries(layouts).map(([breakpoint, layout]) => {
      const first = layout.find((item) => item.i === firstId);
      const second = layout.find((item) => item.i === secondId);
      if (!first || !second) return [breakpoint, layout];
      return [
        breakpoint,
        layout.map((item) => {
          if (item.i === firstId) return { ...item, x: second.x, y: second.y };
          if (item.i === secondId) return { ...item, x: first.x, y: first.y };
          return item;
        }),
      ];
    })
  );
}

function getStoredOrder() {
  try {
    const stored = localStorage.getItem(ORDER_KEY);
    return normalizeWidgetOrder(stored ? JSON.parse(stored) : null, KNOWN_IDS);
  } catch {
    return KNOWN_IDS;
  }
}

function getHidden() {
  try {
    const stored = localStorage.getItem(HIDDEN_KEY);
    const ids = stored ? JSON.parse(stored) : [];
    return Array.isArray(ids) ? ids.filter((id) => KNOWN_IDS.includes(id)) : [];
  } catch {
    return [];
  }
}

function getStoredLayouts() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

function getPhoneOpen() {
  try {
    const stored = localStorage.getItem(PHONE_OPEN_KEY);
    const ids = stored ? JSON.parse(stored) : null;
    if (!Array.isArray(ids)) return PHONE_CORE;
    // The old combined row was opened for both of its cards: keep both open.
    const migrated = ids.includes("concentration") ? [...ids, "heatmap", "insiderBuys", "topHoldings"] : ids;
    return migrated.filter((id, i, all) => PHONE_KNOWN_IDS.includes(id) && all.indexOf(id) === i);
  } catch {
    return PHONE_CORE;
  }
}

const COLLAPSE_MS = 420;

// Animated expand/collapse. The row height eases between 0fr and 1fr (so it
// needs no measured pixel height), while the content fades and slides down a
// few px. The content mounts when opening starts and unmounts only after the
// close animation has finished, so a collapsed widget still costs no extra
// rendering or requests. Overflow is clipped only while moving: once fully
// open it is visible again so card shadows and hover lift are not cut off.
// A widget that starts open (remembered) renders open with no animation.
function Collapse({ open, id, children }) {
  const [phase, setPhase] = useState(open ? "open" : "closed");

  useEffect(() => {
    let frame;
    let timer;
    if (open) {
      setPhase((p) => (p === "open" ? p : "opening-start"));
      // Two frames: paint the 0fr state first so the transition has a start.
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(() => setPhase("opening"));
      });
      timer = setTimeout(() => setPhase("open"), COLLAPSE_MS + 120);
    } else {
      setPhase((p) => (p === "closed" ? p : "closing"));
      timer = setTimeout(() => setPhase("closed"), COLLAPSE_MS);
    }
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, [open]);

  // Mount synchronously on the click that opens it (not a frame later).
  const mounted = open || phase !== "closed";
  if (!mounted) return null;

  const expanded = phase === "opening" || phase === "open";
  const settled = phase === "open";
  return (
    <div
      id={id}
      className="grid transition-[grid-template-rows,opacity] ease-[cubic-bezier(0.22,1,0.36,1)]"
      style={{
        // Explicit single column: the implicit `auto` column grows to the widest
        // non-wrapping child (benchmark chips) and pushed the whole card, chart
        // included, past the edge of a phone screen.
        gridTemplateColumns: "minmax(0, 1fr)",
        gridTemplateRows: expanded ? "1fr" : "0fr",
        opacity: expanded ? 1 : 0,
        transitionDuration: `${COLLAPSE_MS}ms`,
      }}
    >
      <div className={`min-h-0 min-w-0 ${settled ? "" : "overflow-hidden"}`}>
        <div
          className="pt-3 transition-transform ease-[cubic-bezier(0.22,1,0.36,1)]"
          style={{
            transform: expanded ? "translateY(0)" : "translateY(-10px)",
            transitionDuration: `${COLLAPSE_MS}ms`,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

// One widget as a collapsible row. The title and the opened content live in a
// single card (`phone-merged` flattens the widget's own cards, see index.css),
// so an opened widget reads as one bubble rather than a title bubble with a
// second bubble underneath. The row carries the widget's icon, and (for
// single-card widgets) the card's own small heading is dropped so the title is
// never shown twice.
function PhoneWidget({ widget, open, onToggle, children }) {
  const panelId = `phone-widget-${widget.id}`;
  const Icon = widget.icon;
  return (
    <section className="card phone-merged">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex min-h-11 w-full items-center justify-between gap-3 text-left font-display font-semibold text-ink"
      >
        <span className="flex min-w-0 items-center gap-2.5">
          {Icon && (
            <span aria-hidden="true" className="grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
              <Icon size={13} />
            </span>
          )}
          <span className="min-w-0 truncate">{widget.label}</span>
        </span>
        <ChevronDown
          size={18}
          aria-hidden="true"
          className={`shrink-0 text-muted transition-transform duration-[420ms] ease-[cubic-bezier(0.34,1.4,0.64,1)] ${open ? "rotate-180" : ""}`}
        />
      </button>
      <Collapse open={open} id={panelId}>
        <MergedTitleContext.Provider value={Boolean(widget.mergeTitle)}>{children}</MergedTitleContext.Provider>
      </Collapse>
    </section>
  );
}

export default function DashboardGrid({ children, editing, onEditToggle }) {
  const isPhone = useIsPhone();
  const [phoneOpen, setPhoneOpen] = useState(getPhoneOpen);
  const togglePhoneWidget = (id) =>
    setPhoneOpen((current) => {
      const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
      try { localStorage.setItem(PHONE_OPEN_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  const [order, setOrder] = useState(getStoredOrder);
  const [hidden, setHidden] = useState(getHidden);
  const [layouts, setLayouts] = useState(() => getStoredLayouts() || DEFAULT_LAYOUTS);

  const persistOrder = useCallback((next) => {
    setOrder(next);
    localStorage.setItem(ORDER_KEY, JSON.stringify(next));
  }, []);

  const persistHidden = useCallback((next) => {
    setHidden(next);
    localStorage.setItem(HIDDEN_KEY, JSON.stringify(next));
  }, []);

  // A widget the page did not render (its capability is unavailable) is
  // skipped everywhere, but keeps its saved position for when it returns.
  const provided = (id) => children[id] != null;
  const visible = order.filter((id) => !hidden.includes(id) && provided(id));

  const onLayoutChange = useCallback(
    (layout, allLayouts) => {
      if (allLayouts) {
        setLayouts(allLayouts);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(allLayouts));
      }
      if (layout) {
        const visibleIds = [...layout]
          .sort((a, b) => a.y - b.y || a.x - b.x)
          .map((l) => l.i)
          .filter((id) => KNOWN_IDS.includes(id) && !hidden.includes(id));
        if (visibleIds.length) {
          persistOrder([...visibleIds, ...order.filter((id) => hidden.includes(id))]);
        }
      }
    },
    [hidden, order, persistOrder]
  );

  const move = (id) => (direction) => {
    const vis = order.filter((x) => !hidden.includes(x));
    const index = vis.indexOf(id);
    const target = direction === "up" ? index - 1 : index + 1;
    if (target < 0 || target >= vis.length) return;
    const nextVisible = [...vis];
    [nextVisible[index], nextVisible[target]] = [nextVisible[target], nextVisible[index]];
    setLayouts((current) => {
      const nextLayouts = swapLayoutPositions(current, id, vis[target]);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nextLayouts));
      return nextLayouts;
    });
    persistOrder([...nextVisible, ...order.filter((x) => hidden.includes(x))]);
  };

  const hide = (id) => persistHidden([...hidden, id]);

  const restore = (id) => persistHidden(hidden.filter((h) => h !== id));

  const resetLayout = () => {
    persistOrder(KNOWN_IDS);
    persistHidden([]);
    setLayouts(DEFAULT_LAYOUTS);
    localStorage.removeItem(STORAGE_KEY);
  };

  const filteredLayouts = {};
  for (const [bp, layout] of Object.entries(layouts)) {
    filteredLayouts[bp] = (layout || []).filter((l) => visible.includes(l.i));
  }

  const hiddenWidgets = ALL_WIDGETS.filter((w) => hidden.includes(w.id) && provided(w.id));

  const visibleList = visible;

  return (
    <div>
      {editing && (
        <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={resetLayout}
              className="flex items-center gap-1.5 text-xs text-muted hover:text-ink px-2.5 py-1.5 rounded-lg border border-hairline transition-colors"
            >
              <RotateCcw size={12} /> Reset
            </button>
            {hiddenWidgets.map((w) => (
              <button
                key={w.id}
                type="button"
                aria-label={`Restore ${w.label}`}
                onClick={() => restore(w.id)}
                className="flex items-center gap-1.5 text-xs text-brand hover:text-brand/80 px-2.5 py-1.5 rounded-lg border border-brand/30 hover:border-brand/50 transition-colors"
              >
                <Plus size={12} /> Restore {w.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted lg:hidden">
            Ordering follows the saved sequence on small screens.
          </p>
        </div>
      )}

      {editing ? (
        <ResponsiveGridLayout
          key={visibleList.join("|")}
          className="layout"
          layouts={filteredLayouts}
          breakpoints={{ lg: 0 }}
          cols={{ lg: 6 }}
          rowHeight={60}
          onLayoutChange={onLayoutChange}
          isDraggable={true}
          isResizable={true}
          draggableHandle=".drag-handle"
          margin={[16, 16]}
        >
          {visibleList.map((id, index) => {
            const widget = ALL_WIDGETS.find((w) => w.id === id);
            const childContent = children[id];
            return (
              <div key={id} className="relative">
                <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between bg-surface-card/90 backdrop-blur-sm rounded-t-xl px-3 py-1.5 border-b border-hairline">
                  <div className="drag-handle cursor-grab active:cursor-grabbing flex items-center gap-1.5 text-xs text-muted">
                    <GripVertical size={12} />
                    {widget?.label}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      aria-label={`Move ${widget?.label} up`}
                      disabled={index === 0}
                      onClick={() => move(id)("up")}
                      className="text-muted hover:text-ink disabled:opacity-30 disabled:hover:text-muted transition-colors"
                    >
                      <ChevronUp size={13} />
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${widget?.label} down`}
                      disabled={index === visibleList.length - 1}
                      onClick={() => move(id)("down")}
                      className="text-muted hover:text-ink disabled:opacity-30 disabled:hover:text-muted transition-colors"
                    >
                      <ChevronDown size={13} />
                    </button>
                    <button
                      type="button"
                      aria-label={`Hide ${widget?.label}`}
                      onClick={() => hide(id)}
                      className="text-muted hover:text-red-500 transition-colors"
                    >
                      <X size={13} />
                    </button>
                  </div>
                </div>
                <div className="h-full pt-8 overflow-hidden">{childContent}</div>
              </div>
            );
          })}
        </ResponsiveGridLayout>
      ) : isPhone ? (
        <div className="space-y-3">
          {phoneWidgetOrder(visibleList, children).map((id) => (
            <PhoneWidget
              key={id}
              widget={PHONE_WIDGETS.find((w) => w.id === id)}
              open={phoneOpen.includes(id)}
              onToggle={() => togglePhoneWidget(id)}
            >
              {children[id]}
            </PhoneWidget>
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          {visibleList.map((id, i) => (
            <div key={id} className="animate-fade-up" style={{ animationDelay: `${Math.min(i * 60, 360)}ms` }}>
              {children[id]}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export { ALL_WIDGETS };
