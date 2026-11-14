import { Link } from "react-router-dom";

import { msg, useT } from "../../i18n/I18nProvider";
import Select from "../ui/Select";

export const SETTINGS_SECTIONS = [
  { value: "connections", label: msg("Connections") },
  { value: "preferences", label: msg("Preferences") },
  { value: "notifications", label: msg("Notifications") },
  { value: "data", label: msg("Data & Privacy") },
];

function sectionHref(searchParams, section) {
  const next = new URLSearchParams(searchParams);
  next.set("section", section);
  return `?${next.toString()}`;
}

export default function SettingsSectionNav({ value, searchParams, onSelect }) {
  const t = useT();
  return (
    <>
      <nav aria-label={t("Settings sections")} className="hidden w-48 shrink-0 lg:block">
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
                {t(section.label)}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <label className="block lg:hidden">
        <span className="mb-1.5 block text-sm font-medium">{t("Settings section")}</span>
        <Select
          aria-label={t("Settings section")}
          className="text-sm"
          onChange={(next) => onSelect(next, true)}
          value={value}
          options={SETTINGS_SECTIONS.map((section) => ({ value: section.value, label: t(section.label) }))}
        />
      </label>
    </>
  );
}
