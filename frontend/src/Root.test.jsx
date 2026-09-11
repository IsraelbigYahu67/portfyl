import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Root from "./Root";
import { HAS_PUBLIC_HOME, TRACKER_HOME } from "./lib/routes";

vi.mock("./App", () => ({ default: () => <div>Protected tracker</div> }));
beforeEach(() => localStorage.clear());

it("serves the public home only in cloud, outside the tracker", async () => {
  render(<MemoryRouter initialEntries={["/"]}><Root /></MemoryRouter>);
  if (HAS_PUBLIC_HOME) {
    expect(screen.getByRole("button", { name: /Pokračovat česky/ })).toBeInTheDocument();
    expect(screen.queryByText("Protected tracker")).not.toBeInTheDocument();
  } else {
    expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
  }
});

it("keeps the private tracker reachable at its edition-specific home", async () => {
  render(<MemoryRouter initialEntries={[TRACKER_HOME]}><Root /></MemoryRouter>);
  expect(await screen.findByText("Protected tracker")).toBeInTheDocument();
});
