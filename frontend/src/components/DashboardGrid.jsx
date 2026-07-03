import { useState, useCallback } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import { GripVertical, X, Plus, RotateCcw } from "lucide-react";
import "react-grid-layout/css/styles.css";

const ResponsiveGridLayout = WidthProvider(Responsive);

const STORAGE_KEY = "sb_dashboard_layout";
const VISIBLE_KEY = "sb_dashboard_widgets";

const ALL_WIDGETS = [
  { id: "metrics", label: "Metrics", minW: 2, minH: 2 },
  { id: "performance", label: "Performance Chart", minW: 3, minH: 4 },
  { id: "heatmap", label: "Heatmap", minW: 3, minH: 4 },
  { id: "earnings", label: "Earnings Calendar", minW: 2, minH: 3 },
  { id: "holdings", label: "Top Holdings", minW: 2, minH: 3 },
  { id: "insiderBuys", label: "Insider Buys (1Y)", minW: 3, minH: 4 },
  { id: "movers", label: "Top Movers", minW: 4, minH: 4 },
];

const DEFAULT_LAYOUTS = {
  lg: [
    { i: "metrics", x: 0, y: 0, w: 6, h: 2 },
    { i: "performance", x: 0, y: 2, w: 3, h: 5 },
    { i: "heatmap", x: 3, y: 2, w: 3, h: 5 },
    { i: "earnings", x: 0, y: 7, w: 3, h: 4 },
    { i: "holdings", x: 3, y: 7, w: 3, h: 4 },
    { i: "insiderBuys", x: 0, y: 11, w: 6, h: 5 },
    { i: "movers", x: 0, y: 16, w: 6, h: 4 },
  ],
};

function getStoredLayouts() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

function getVisibleWidgets() {
  try {
    const stored = localStorage.getItem(VISIBLE_KEY);
    if (!stored) return ALL_WIDGETS.map((w) => w.id);
    const ids = JSON.parse(stored);
    const known = new Set(ids);
    for (const w of ALL_WIDGETS) {
      if (!known.has(w.id)) ids.push(w.id);
    }
    return ids;
  } catch {
    return ALL_WIDGETS.map((w) => w.id);
  }
}

export default function DashboardGrid({ children, editing, onEditToggle }) {
  const [layouts, setLayouts] = useState(() => getStoredLayouts() || DEFAULT_LAYOUTS);
  const [visible, setVisible] = useState(getVisibleWidgets);
  const [showAdd, setShowAdd] = useState(false);

  const onLayoutChange = useCallback((layout, allLayouts) => {
    setLayouts(allLayouts);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(allLayouts));
  }, []);

  const removeWidget = (id) => {
    const next = visible.filter((v) => v !== id);
    setVisible(next);
    localStorage.setItem(VISIBLE_KEY, JSON.stringify(next));
  };

  const addWidget = (id) => {
    if (visible.includes(id)) return;
    const next = [...visible, id];
    setVisible(next);
    localStorage.setItem(VISIBLE_KEY, JSON.stringify(next));
    const widget = ALL_WIDGETS.find((w) => w.id === id);
    const newLayouts = { ...layouts };
    const lgLayout = [...(newLayouts.lg || [])];
    lgLayout.push({ i: id, x: 0, y: Infinity, w: widget.minW * 2, h: widget.minH });
    newLayouts.lg = lgLayout;
    setLayouts(newLayouts);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newLayouts));
    setShowAdd(false);
  };

  const resetLayout = () => {
    setLayouts(DEFAULT_LAYOUTS);
    setVisible(ALL_WIDGETS.map((w) => w.id));
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(VISIBLE_KEY);
  };

  const filteredLayouts = {};
  for (const [bp, layout] of Object.entries(layouts)) {
    filteredLayouts[bp] = layout.filter((l) => visible.includes(l.i));
  }

  const hiddenWidgets = ALL_WIDGETS.filter((w) => !visible.includes(w.id));

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {editing && (
            <>
              <button
                onClick={resetLayout}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 px-2.5 py-1.5 rounded-lg border border-slate-200 hover:border-slate-300 transition-colors"
              >
                <RotateCcw size={12} /> Reset
              </button>
              {hiddenWidgets.length > 0 && (
                <div className="relative">
                  <button
                    onClick={() => setShowAdd(!showAdd)}
                    className="flex items-center gap-1.5 text-xs text-brand hover:text-brand/80 px-2.5 py-1.5 rounded-lg border border-brand/30 hover:border-brand/50 transition-colors"
                  >
                    <Plus size={12} /> Add Widget
                  </button>
                  {showAdd && (
                    <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-50 min-w-[160px]">
                      {hiddenWidgets.map((w) => (
                        <button
                          key={w.id}
                          onClick={() => addWidget(w.id)}
                          className="w-full text-left px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                        >
                          {w.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {editing ? (
        <ResponsiveGridLayout
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
          {visible.map((id) => {
            const widget = ALL_WIDGETS.find((w) => w.id === id);
            const childContent = children[id];
            return (
              <div key={id} className="relative">
                <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between bg-white/90 backdrop-blur-sm rounded-t-xl px-3 py-1.5 border-b border-slate-100">
                  <div className="drag-handle cursor-grab active:cursor-grabbing flex items-center gap-1.5 text-xs text-slate-400">
                    <GripVertical size={12} />
                    {widget?.label}
                  </div>
                  <button
                    onClick={() => removeWidget(id)}
                    className="text-slate-400 hover:text-red-500 transition-colors"
                  >
                    <X size={12} />
                  </button>
                </div>
                <div className="h-full pt-8 overflow-hidden">
                  {childContent}
                </div>
              </div>
            );
          })}
        </ResponsiveGridLayout>
      ) : (
        <div className="space-y-6">
          {visible.map((id) => (
            <div key={id}>{children[id]}</div>
          ))}
        </div>
      )}
    </div>
  );
}

export { ALL_WIDGETS };
