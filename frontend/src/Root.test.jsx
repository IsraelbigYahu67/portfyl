import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Root from "./Root";
import { HAS_PUBLIC_HOME, TRACKER_HOME, contentPageFor } from "./lib/routes";
import { FIXTURE_PAGES, fixtureCs, fixtureEn } from "./test/contentFixtures";

vi.mock("./TrackerBootstrap", () => ({ default: () => <div>Protected tracker</div> }));
// Cloud's Root lazy-loads Welcome; load it during collection (untimed) so the
// first test doesn't spend its findBy window on the cold module graph.
if (HAS_PUBLIC_HOME) await import("./pages/Welcome");
if (HAS_PUBLIC_HOME) await import("./pages/Legal");
if (HAS_PUBLIC_HOME) await import("./pages/content/ContentRoute");
beforeEach(() => { localStorage.clear(); window.history.replaceState({}, '', '/'); });
afterEach(() => { vi.unstubAllGlobals(); });

function setLocation({ pathname = "/", hostname = "localhost", replace = vi.fn() } = {}) {
  window.history.replaceState({}, "", pathname);
  vi.stubGlobal("location", { ...window.location, hostname, pathname, replace });
}

it("serves the public home only in cloud, outside the tracker", async () => {
  render(<MemoryRouter initialEntries={["/"]}><Root /></MemoryRouter>);
  if (HAS_PUBLIC_HOME) {
    expect(await screen.findByRole("heading", { level: 1, name: /Všechny akcie a ETF/ })).toBeInTheDocument();
    expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
  } else {
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  }
});

it.each([
  ["/en/", /All your stocks and ETFs/],
  ["/en", /All your stocks and ETFs/],
  ["/de/", /Alle Aktien und ETFs/],
])("serves the %s landing in its own language in cloud, regardless of saved preference", async (pathname, heading) => {
  localStorage.setItem("portfyl_landing_language", "cs");
  setLocation({ pathname, hostname: "portfyl.com" });
  render(<MemoryRouter initialEntries={[pathname]}><Root /></MemoryRouter>);
  if (HAS_PUBLIC_HOME) {
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  } else {
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  }
});

it.each(["/fr/", "/en/demo", "/cs/"])("does not treat %s as a landing page", async (pathname) => {
  setLocation({ pathname, hostname: "portfyl.com" });
  render(<MemoryRouter initialEntries={[pathname]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
});

it("never serves the landing on the tracker host", async () => {
  setLocation({ pathname: "/en/", hostname: "app.portfyl.com" });
  render(<MemoryRouter initialEntries={["/en/"]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
});

it("keeps the private tracker reachable at its edition-specific home", async () => {
  window.history.replaceState({}, '', TRACKER_HOME);
  render(<MemoryRouter initialEntries={[TRACKER_HOME]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
});

// The public /demo is retired. The server answers it with a 301 to the home
// page; this is the client-side safety net (in-app navigation, hosts without
// the backend).
it.each(["/demo", "/demo/", "/demo/allocation"])("sends the retired %s to the home page in cloud, on a non-tracker host", async (pathname) => {
  const replace = vi.fn();
  setLocation({ pathname, hostname: "portfyl.com", replace });
  render(<MemoryRouter initialEntries={[pathname]}><Root /></MemoryRouter>);
  if (HAS_PUBLIC_HOME) {
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(replace).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("Loading Portfyl");
    expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
    expect(screen.queryByText("Public demo")).not.toBeInTheDocument();
  } else {
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  }
});

it("does not treat /demolition as a retired route -- it enters the protected tracker", async () => {
  const replace = vi.fn();
  setLocation({ pathname: "/demolition", hostname: "portfyl.com", replace });
  render(<MemoryRouter initialEntries={["/demolition"]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
});

it("leaves /demo to the tracker on the tracker host, like any unknown path", async () => {
  const replace = vi.fn();
  setLocation({ pathname: "/demo", hostname: "app.portfyl.com", replace });
  render(<MemoryRouter initialEntries={["/demo"]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
});

it.each([
  ["/terms", "portfyl.com", "Portfyl Terms of Service"],
  ["/privacy/", "app.portfyl.com", "Portfyl Privacy and Cookie Policy"],
  ["/security", "portfyl.com", "Portfyl Security"],
  ["/security/", "app.portfyl.com", "Portfyl Security"],
])("serves %s publicly on %s in both editions, without the tracker", async (pathname, hostname, title) => {
  // jsdom's navigator.language is en-US, so the English text is served.
  setLocation({ pathname, hostname });
  render(<MemoryRouter initialEntries={[pathname]}><Root /></MemoryRouter>);
  // Role queries are slow in jsdom, and this runs right after the heavy
  // landing renders; under a full parallel run the default 1 s window flaked.
  expect(await screen.findByRole("heading", { level: 1, name: title }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
});

// Content pages: the real registry is empty, so a fixture registry is passed in.
describe("content pages", () => {
  const renderContent = (pathname, { hostname = "portfyl.com", contentPages = FIXTURE_PAGES } = {}) => {
    setLocation({ pathname, hostname });
    return render(<MemoryRouter initialEntries={[pathname]}><Root contentPages={contentPages} /></MemoryRouter>);
  };

  it("finds a registered page by path, with or without the trailing slash, and nothing else", () => {
    expect(contentPageFor(fixtureCs.path, FIXTURE_PAGES)).toBe(fixtureCs);
    expect(contentPageFor(fixtureCs.path.slice(0, -1), FIXTURE_PAGES)).toBe(fixtureCs);
    expect(contentPageFor("/en/fixture-portfolio-tracker", FIXTURE_PAGES)).toBe(fixtureEn);
    for (const path of ["/", "/en/", "/fixture-sledovani-portfolia/extra/", "/fixture-sledovani/", "/dashboard", "/en/fixture-sledovani-portfolia/"]) {
      expect(contentPageFor(path, FIXTURE_PAGES), path).toBeNull();
    }
    // Registered pages are public only in cloud: the real registry is not consulted in local.
    expect(contentPageFor("/fixture-sledovani-portfolia/")).toBeNull();
  });

  it.skipIf(!HAS_PUBLIC_HOME).each([fixtureCs.path, fixtureCs.path.slice(0, -1)])("serves a registered page at %s in the shared layout, without the tracker", async (pathname) => {
    renderContent(pathname);
    expect(await screen.findByRole("heading", { level: 1, name: fixtureCs.title }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText("Fixture body paragraph about tracking a portfolio.")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Nejde o investiční poradenství.");
    expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
  });

  it.skipIf(!HAS_PUBLIC_HOME)("serves the English sibling in English and links the language versions to each other", async () => {
    renderContent(fixtureEn.path);
    expect(await screen.findByRole("heading", { level: 1, name: fixtureEn.title }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Not investment advice.");
    const language = screen.getAllByRole("group", { name: "Page language" })[0];
    expect(language.querySelector('a[hreflang="cs"]')).toHaveAttribute("href", fixtureCs.path);
    expect(language.querySelector('a[hreflang="de"]')).toHaveAttribute("href", "/de/");
  });

  it("never serves a registered page on the tracker host", async () => {
    renderContent(fixtureCs.path, { hostname: "app.portfyl.com" });
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  });

  it("leaves an unregistered path to the tracker", async () => {
    renderContent("/fixture-neexistuje/");
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  });
});
