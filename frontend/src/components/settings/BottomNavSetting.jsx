import { useState } from "react";
import { Check, RotateCcw } from "lucide-react";

import BottomNavBar, { MORE_KEY } from "../layout/BottomNavBar";
import { useNavGroups } from "../layout/NavGroupsContext";
import { bottomNavChoices, resolveBottomNavItems } from "../layout/navigation";
import { BOTTOM_NAV_MAX, BOTTOM_NAV_MIN, useBottomNavPaths } from "../../lib/bottomNavPrefs";

// Settings > Preferences: pick which pages sit in the phone bottom bar. The
// preview is the very same bar the phone shows (the real one is hidden from
// `lg` up), so adding / removing a page and tapping between pages animate here
// exactly as they do on the phone.
export default function BottomNavSetting() {
  const groups = useNavGroups();
  const { paths, setPaths, reset, isDefault } = useBottomNavPaths();
  const choices = bottomNavChoices(groups);
  const items = resolveBottomNavItems(groups, paths, { min: BOTTOM_NAV_MIN });
  const selected = new Set(items.map(({ to }) => to));
  const [previewKey, setPreviewKey] = useState(() => items[0]?.to ?? MORE_KEY);
  // A page that was just removed hands the highlight to "More", like the real bar.
  const activeKey = previewKey === MORE_KEY || selected.has(previewKey) ? previewKey : MORE_KEY;

  const toggle = (to) => {
    const next = new Set(selected);
    if (next.has(to)) next.delete(to);
    else next.add(to);
    // Stored in navigation order so the bar reads the same everywhere.
    setPaths(choices.filter((choice) => next.has(choice.to)).map((choice) => choice.to));
  };

  return (
    <div>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Phone navigation bar</h3>
          <p className="mt-0.5 text-xs text-muted">
            Pick the pages in the bar at the bottom of your phone. Everything else stays under More.
          </p>
        </div>
        <button
          type="button"
          onClick={reset}
          disabled={isDefault}
          className="btn-ghost inline-flex shrink-0 items-center gap-1.5 min-h-11 md:min-h-0 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-40"
        >
          <RotateCcw size={13} aria-hidden="true" />
          Reset
        </button>
      </div>

      {/* Same bar as on the phone; tapping an item here slides the highlight. */}
      <div
        aria-hidden="true"
        data-testid="bottom-nav-preview"
        className="app-bottomnav mx-auto mb-3 max-w-md overflow-hidden rounded-2xl border border-hairline"
      >
        <BottomNavBar preview items={items} activeKey={activeKey} onSelect={setPreviewKey} />
      </div>

      <div role="group" aria-label="Pages in the phone navigation bar" className="flex flex-wrap gap-2">
        {choices.map(({ to, label, icon: Icon }) => {
          const on = selected.has(to);
          const blocked = on ? selected.size <= BOTTOM_NAV_MIN : selected.size >= BOTTOM_NAV_MAX;
          return (
            <button
              key={to}
              type="button"
              aria-label={`Bottom bar: ${label}`}
              aria-pressed={on}
              disabled={blocked}
              title={
                blocked
                  ? on
                    ? `Keep at least ${BOTTOM_NAV_MIN} pages in the bar`
                    : `The bar holds up to ${BOTTOM_NAV_MAX} pages. Remove one first.`
                  : undefined
              }
              onClick={() => toggle(to)}
              className={`flex items-center gap-2 rounded-full border px-4 py-2 min-h-11 md:min-h-0 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                on ? "border-brand text-ink bg-[var(--sidebar-active)]" : "border-surface-border text-muted hover:text-ink"
              }`}
            >
              {on ? <Check size={14} aria-hidden="true" className="text-brand" /> : <Icon size={14} aria-hidden="true" />}
              {label}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-muted tabular-nums">
        {selected.size} of {BOTTOM_NAV_MAX} pages. More is always there.
      </p>
    </div>
  );
}
