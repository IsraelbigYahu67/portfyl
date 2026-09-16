import { useRef } from "react";

function toIdPart(value) {
  return String(value).trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

export function UrlTabs({ ariaLabel, idPrefix = "url-tabs", items, value, onChange, className = "" }) {
  const refs = useRef(new Map());
  const enabledItems = items.filter((item) => !item.disabled);

  const selectAndFocus = (item) => {
    if (!item || item.disabled) return;
    onChange(item.value);
    refs.current.get(item.value)?.focus();
  };

  const handleKeyDown = (event, currentValue) => {
    const currentIndex = enabledItems.findIndex((item) => item.value === currentValue);
    if (currentIndex < 0 || enabledItems.length === 0) return;

    let nextItem;
    if (event.key === "ArrowRight") {
      nextItem = enabledItems[(currentIndex + 1) % enabledItems.length];
    } else if (event.key === "ArrowLeft") {
      nextItem = enabledItems[(currentIndex - 1 + enabledItems.length) % enabledItems.length];
    } else if (event.key === "Home") {
      nextItem = enabledItems[0];
    } else if (event.key === "End") {
      nextItem = enabledItems[enabledItems.length - 1];
    } else {
      return;
    }

    event.preventDefault();
    selectAndFocus(nextItem);
  };

  return (
    <div
      aria-label={ariaLabel}
      className={`flex min-w-0 gap-1 overflow-x-auto ${className}`.trim()}
      role="tablist"
    >
      {items.map((item) => {
        const selected = item.value === value;
        const idPart = toIdPart(item.value);
        return (
          <button
            key={item.value}
            ref={(node) => {
              if (node) refs.current.set(item.value, node);
              else refs.current.delete(item.value);
            }}
            id={`${idPrefix}-${idPart}-tab`}
            type="button"
            role="tab"
            aria-controls={item.panelId}
            aria-selected={selected}
            disabled={item.disabled}
            tabIndex={selected && !item.disabled ? 0 : -1}
            onClick={() => selectAndFocus(item)}
            onKeyDown={(event) => handleKeyDown(event, item.value)}
            className={`shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
              selected
                ? "bg-[var(--accent)] text-white"
                : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
