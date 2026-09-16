import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Root from "./Root";
import { HAS_PUBLIC_HOME, TRACKER_HOME } from "./lib/routes";

vi.mock("./TrackerBootstrap", () => ({ default: () => <div>Protected tracker</div> }));
beforeEach(() => { localStorage.clear(); window.history.replaceState({}, '', '/'); });

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
