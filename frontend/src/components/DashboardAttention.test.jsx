import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import DashboardAttention from "./DashboardAttention";

function renderAttention(props) {
  return render(
    <MemoryRouter>
      <DashboardAttention {...props} />
    </MemoryRouter>
  );
}

describe("DashboardAttention", () => {
  it("renders named alert links and an all-clear state", () => {
    const { rerender } = render(
      <MemoryRouter>
        <DashboardAttention
          alerts={[{ id: "x", severity: "warning", title: "Concentration", detail: "AAPL is 30%", to: "/allocation" }]}
        />
      </MemoryRouter>
    );
    expect(screen.getByRole("link", { name: /concentration/i })).toHaveAttribute("href", "/allocation");
    expect(screen.getByText("Warning")).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <DashboardAttention alerts={[]} />
      </MemoryRouter>
    );
    expect(screen.getByText(/nothing needs attention/i)).toBeInTheDocument();
  });

  it("shows an error with retry when the attention sources fail", () => {
    const onRetry = () => {};
    renderAttention({ alerts: [], error: new Error("Movers unavailable"), onRetry });
    expect(screen.getByRole("alert")).toHaveTextContent("Movers unavailable");
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
