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

it("uses the landing header, whose section links lead back to the landing in the same language", () => {
  window.history.replaceState({}, "", "/privacy?lang=en");
  const { unmount } = render(<Legal page="privacy" />);
  const nav = within(screen.getByRole("banner")).getByRole("navigation", { name: "Main navigation" });
  expect(within(nav).getAllByRole("link").map((link) => link.getAttribute("href")))
    .toEqual(["/en/#funkce", "/en/#brokeri", "/en/#cenik", "/en/#otazky"]);
  unmount();

  window.history.replaceState({}, "", "/terms?lang=cs");
  render(<Legal page="terms" />);
  const csNav = within(screen.getByRole("banner")).getByRole("navigation", { name: "Hlavní navigace" });
  expect(within(csNav).getAllByRole("link").map((link) => link.getAttribute("href")))
    .toEqual(["/#funkce", "/#brokeri", "/#cenik", "/#otazky"]);
});

it("links both documents from the page and from the landing footer in the current language", () => {
  window.history.replaceState({}, "", "/privacy?lang=en");
  render(<Legal page="privacy" />);
  const docs = within(screen.getByRole("main")).getByRole("navigation", { name: "Legal documents" });
  expect(within(docs).getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms?lang=en");
  expect(within(docs).getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("aria-current", "page");
  const footer = within(screen.getByRole("contentinfo"));
  expect(footer.getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms?lang=en");
  expect(footer.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy?lang=en");
});

it("keeps the draft note and a contents list", () => {
  window.history.replaceState({}, "", "/terms?lang=en");
  render(<Legal page="terms" />);
  expect(screen.getByRole("note")).toHaveTextContent("Working draft.");
  expect(screen.getByText("Contents")).toBeInTheDocument();
});

it("covers the trial and the bot check in the terms and the privacy policy", () => {
  window.history.replaceState({}, "", "/terms?lang=en");
  const { unmount } = render(<Legal page="terms" />);
  expect(screen.getByRole("main").textContent).toMatch(/One trial per person/);
  unmount();
  window.history.replaceState({}, "", "/privacy?lang=cs");
  render(<Legal page="privacy" />);
  expect(screen.getByRole("main").textContent).toMatch(/Cloudflare Turnstile/);
});

it("picks the language from ?lang, then the landing choice, and switches in place", () => {
  localStorage.setItem(LANGUAGE_KEY, "de");
  render(<Legal page="terms" />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Portfyl Terms of Service");
  fireEvent.click(screen.getByRole("button", { name: "CZ – Čeština" }));
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Obchodní podmínky");
  expect(window.location.search).toBe("?lang=cs");
});
