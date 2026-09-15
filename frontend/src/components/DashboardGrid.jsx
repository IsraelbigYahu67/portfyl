import { useState, useCallback } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import { GripVertical, X, Plus, RotateCcw, ChevronUp, ChevronDown } from "lucide-react";
import "react-grid-layout/css/styles.css";

const ResponsiveGridLayout = WidthProvider(Responsive);

const STORAGE_KEY = "sb_dashboard_layout";
// Order-first persistence: the widget sequence is the source of truth, and
// desktop drag/resize coordinates are an optional decoration on top of it.
const ORDER_KEY = "sb_dashboard_widget_order_v2";
const HIDDEN_KEY = "sb_dashboard_widgets_hidden";

const ALL_WIDGETS = [
  { id: "performance", label: "Performance", minW: 3, minH: 4 },
  { id: "concentration", label: "Concentration", minW: 3, minH: 4 },
  { id: "attention", label: "Needs attention", minW: 3, minH: 3 },
  { id: "movers", label: "Top Movers", minW: 4, minH: 4 },
  { id: "insiderBuys", label: "Insider activity (1Y)", minW: 3, minH: 4 },
];

const KNOWN_IDS = ALL_WIDGETS.map((w) => w.id);

const DEFAULT_LAYOUTS = {
  lg: [
    { i: "performance", x: 0, y: 0, w: 6, h: 5 },
    { i: "concentration", x: 0, y: 5, w: 6, h: 5 },
    { i: "attention", x: 0, y: 10, w: 6, h: 4 },
    { i: "movers", x: 0, y: 14, w: 6, h: 4 },
    { i: "insiderBuys", x: 0, y: 18, w: 6, h: 5 },
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

export default function DashboardGrid({ children, editing, onEditToggle }) {
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

  const visible = order.filter((id) => !hidden.includes(id));

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

  const hiddenWidgets = ALL_WIDGETS.filter((w) => hidden.includes(w.id));

  const visibleList = order.filter((id) => !hidden.includes(id));

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
          <p className="text-[11px] text-muted lg:hidden">
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
