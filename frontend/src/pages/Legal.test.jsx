import { fireEvent, render, screen, within } from "@testing-library/react";
import Legal from "./Legal";
import { LANGUAGE_KEY } from "./welcomeCopy";

vi.mock("../analytics/AnalyticsProvider", () => ({ useAnalytics: () => ({ reopenAnalyticsPreferences: vi.fn() }) }));

beforeEach(() => { localStorage.clear(); window.history.replaceState({}, "", "/terms"); });

const PAGES = [
  ["terms", "cs", "Obchodní podmínky a podmínky užívání služby Portfyl"],
  ["terms", "en", "Portfyl Terms of Service"],
  ["privacy", "cs", "Zásady ochrany osobních údajů a cookies – Portfyl"],
  ["privacy", "en", "Portfyl Privacy and Cookie Policy"],
];

it.each(PAGES)("renders %s in %s from docs/legal without raw Markdown", (page, lang, title) => {
  window.history.replaceState({}, "", `/${page}?lang=${lang}`);
  render(<Legal page={page} />);
  expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  const main = screen.getByRole("main");
  expect(main.textContent).not.toMatch(/\[\[|\*\*|`|\]\(/);
  // Every [[...]] marker is shown as clearly pending, never as raw syntax.
  expect(main.querySelectorAll("mark.legal-pending").length).toBeGreaterThan(0);
  expect(screen.getByRole("note")).toBeInTheDocument();
  expect(document.title).toBe(`${title} — Portfyl`);
  expect(document.documentElement.lang).toBe(lang);
});

it("links both documents from the header and footer in the current language", () => {
  window.history.replaceState({}, "", "/privacy?lang=en");
  render(<Legal page="privacy" />);
  const [header] = screen.getAllByRole("navigation", { name: "Legal documents" });
  expect(within(header).getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms?lang=en");
  expect(within(header).getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("aria-current", "page");
  expect(within(screen.getByRole("contentinfo")).getByRole("link", { name: "Terms of Service" })).toBeInTheDocument();
});

it("picks the language from ?lang, then the landing choice, and switches in place", () => {
  localStorage.setItem(LANGUAGE_KEY, "de");
  render(<Legal page="terms" />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Portfyl Terms of Service");
  fireEvent.click(screen.getByRole("button", { name: "Čeština" }));
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Obchodní podmínky");
  expect(window.location.search).toBe("?lang=cs");
});
