import { Link } from "react-router-dom";

export const SETTINGS_SECTIONS = [
  { value: "connections", label: "Connections" },
  { value: "preferences", label: "Preferences" },
  { value: "notifications", label: "Notifications" },
  { value: "data", label: "Data & Privacy" },
];

function sectionHref(searchParams, section) {
  const next = new URLSearchParams(searchParams);
  next.set("section", section);
  return `?${next.toString()}`;
}

export default function SettingsSectionNav({ value, searchParams, onSelect }) {
  return (
    <>
      <nav aria-label="Settings sections" className="hidden w-48 shrink-0 lg:block">
        <ul className="space-y-1">
          {SETTINGS_SECTIONS.map((section) => (
            <li key={section.value}>
              <Link
                aria-current={value === section.value ? "page" : undefined}
                className={`block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  value === section.value
                    ? "bg-surface-hover text-brand"
                    : "text-muted hover:bg-surface-hover hover:text-ink"
                }`}
                onClick={() => onSelect(section.value, false)}
                to={sectionHref(searchParams, section.value)}
              >
                {section.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <label className="block lg:hidden">
        <span className="mb-1.5 block text-sm font-medium">Settings section</span>
        <select
          aria-label="Settings section"
          className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
          onChange={(event) => onSelect(event.target.value, true)}
          value={value}
        >
          {SETTINGS_SECTIONS.map((section) => (
            <option key={section.value} value={section.value}>{section.label}</option>
          ))}
        </select>
      </label>
    </>
  );
}
