import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Root from "./Root";
import { HAS_PUBLIC_HOME, TRACKER_HOME } from "./lib/routes";

vi.mock("./TrackerBootstrap", () => ({ default: () => <div>Protected tracker</div> }));
vi.mock("./demo/DemoBootstrap", () => ({ default: () => <div>Public demo</div> }));
// Cloud's Root lazy-loads Welcome; load it during collection (untimed) so the
// first test doesn't spend its findBy window on the cold module graph.
if (HAS_PUBLIC_HOME) await import("./pages/Welcome");
if (HAS_PUBLIC_HOME) await import("./pages/Legal");
beforeEach(() => { localStorage.clear(); window.history.replaceState({}, '', '/'); });
afterEach(() => { vi.unstubAllGlobals(); });

function setLocation({ pathname = "/", hostname = "localhost" } = {}) {
  window.history.replaceState({}, "", pathname);
  vi.stubGlobal("location", { ...window.location, hostname, pathname });
}

it("serves the public home only in cloud, outside the tracker", async () => {
  render(<MemoryRouter initialEntries={["/"]}><Root /></MemoryRouter>);
  if (HAS_PUBLIC_HOME) {
    expect(await screen.findByRole("button", { name: /Pokračovat česky/ })).toBeInTheDocument();
    expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
  } else {
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  }
});

it("keeps the private tracker reachable at its edition-specific home", async () => {
  window.history.replaceState({}, '', TRACKER_HOME);
  render(<MemoryRouter initialEntries={[TRACKER_HOME]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
});

it("routes /demo to the public demo only in cloud, on a non-tracker host", async () => {
  setLocation({ pathname: "/demo", hostname: "portfyl.com" });
  render(<MemoryRouter initialEntries={["/demo"]}><Root /></MemoryRouter>);
  if (HAS_PUBLIC_HOME) {
    expect(await screen.findByText("Public demo")).toBeInTheDocument();
    expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
  } else {
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
    expect(screen.queryByText("Public demo")).not.toBeInTheDocument();
  }
});

it("routes a demo child route (/demo/allocation) the same as /demo", async () => {
  setLocation({ pathname: "/demo/allocation", hostname: "portfyl.com" });
  render(<MemoryRouter initialEntries={["/demo/allocation"]}><Root /></MemoryRouter>);
  if (HAS_PUBLIC_HOME) {
    expect(await screen.findByText("Public demo")).toBeInTheDocument();
  } else {
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  }
});

it("does not treat /demolition as a demo route -- it enters the protected tracker", async () => {
  setLocation({ pathname: "/demolition", hostname: "portfyl.com" });
  render(<MemoryRouter initialEntries={["/demolition"]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  expect(screen.queryByText("Public demo")).not.toBeInTheDocument();
});

it("never serves the public demo on the tracker host, even at /demo", async () => {
  setLocation({ pathname: "/demo", hostname: "app.portfyl.com" });
  render(<MemoryRouter initialEntries={["/demo"]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  expect(screen.queryByText("Public demo")).not.toBeInTheDocument();
});

it.each([
  ["/terms", "portfyl.com", "Portfyl Terms of Service"],
  ["/privacy/", "app.portfyl.com", "Portfyl Privacy and Cookie Policy"],
])("serves %s publicly on %s in both editions, without the tracker", async (pathname, hostname, title) => {
  // jsdom's navigator.language is en-US, so the English text is served.
  setLocation({ pathname, hostname });
  render(<MemoryRouter initialEntries={[pathname]}><Root /></MemoryRouter>);
  expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
});
