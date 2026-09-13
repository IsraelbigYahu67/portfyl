import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Onboarding from "./Onboarding";
import { TRACKER_HOME } from "../lib/routes";


const mocks = vi.hoisted(() => ({
  createPortfolio: vi.fn(),
  createDemoPortfolio: vi.fn(),
  setCurrentId: vi.fn(),
  refetchPortfolios: vi.fn(),
}));

vi.mock("../api", () => ({
  createPortfolio: mocks.createPortfolio,
  createDemoPortfolio: mocks.createDemoPortfolio,
}));

vi.mock("../App", () => ({
  usePortfolio: () => ({
    setCurrentId: mocks.setCurrentId,
    refetchPortfolios: mocks.refetchPortfolios,
  }),
}));


function mount() {
  return render(
    <MemoryRouter initialEntries={["/onboarding"]}>
      <Routes>
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path={TRACKER_HOME} element={<div>Dashboard destination</div>} />
        <Route path="/import" element={<div>Import destination</div>} />
        <Route path="/settings" element={<div>Settings destination</div>} />
      </Routes>
    </MemoryRouter>
  );
}


describe("Onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createPortfolio.mockResolvedValue({ id: "portfolio-id" });
    mocks.createDemoPortfolio.mockResolvedValue({ id: "demo-id" });
    mocks.refetchPortfolios.mockResolvedValue({});
  });

  it("creates and selects a blank portfolio before opening CSV import", async () => {
    mount();

    fireEvent.click(screen.getByRole("button", { name: /import a csv/i }));

    await waitFor(() => expect(mocks.createPortfolio).toHaveBeenCalledWith({ name: "My portfolio" }));
    expect(mocks.setCurrentId).toHaveBeenCalledWith("portfolio-id");
    expect(await screen.findByText("Import destination")).toBeInTheDocument();
  });

  it("creates a clearly labelled demo and opens its dashboard", async () => {
    mount();

    fireEvent.click(screen.getByRole("button", { name: /explore sample portfolio/i }));

    await waitFor(() => expect(mocks.createDemoPortfolio).toHaveBeenCalledTimes(1));
    expect(mocks.setCurrentId).toHaveBeenCalledWith("demo-id");
    expect(await screen.findByText("Dashboard destination")).toBeInTheDocument();
  });

  it("creates a portfolio before sending the user to broker settings", async () => {
    mount();

    fireEvent.click(screen.getByRole("button", { name: /connect a broker/i }));

    await waitFor(() => expect(mocks.createPortfolio).toHaveBeenCalledWith({ name: "My portfolio" }));
    expect(mocks.setCurrentId).toHaveBeenCalledWith("portfolio-id");
    expect(await screen.findByText("Settings destination")).toBeInTheDocument();
  });

  it("shows an actionable API error without navigating", async () => {
    mocks.createDemoPortfolio.mockRejectedValueOnce({
      response: { data: { detail: "Demo limit reached" } },
    });
    mount();

    fireEvent.click(screen.getByRole("button", { name: /explore sample portfolio/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Demo limit reached");
  });
});
