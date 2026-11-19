import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Root from "./Root";
import { HAS_PUBLIC_HOME, TRACKER_HOME } from "./lib/routes";

vi.mock("./TrackerBootstrap", () => ({ default: () => <div>Protected tracker</div> }));
// Cloud's Root lazy-loads Welcome; load it during collection (untimed) so the
// first test doesn't spend its findBy window on the cold module graph.
if (HAS_PUBLIC_HOME) await import("./pages/Welcome");
if (HAS_PUBLIC_HOME) await import("./pages/Legal");
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
])("serves %s publicly on %s in both editions, without the tracker", async (pathname, hostname, title) => {
  // jsdom's navigator.language is en-US, so the English text is served.
  setLocation({ pathname, hostname });
  render(<MemoryRouter initialEntries={[pathname]}><Root /></MemoryRouter>);
  // Role queries are slow in jsdom, and this runs right after the heavy
  // landing renders; under a full parallel run the default 1 s window flaked.
  expect(await screen.findByRole("heading", { level: 1, name: title }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
});
