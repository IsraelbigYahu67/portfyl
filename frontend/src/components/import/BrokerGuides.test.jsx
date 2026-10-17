import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import BrokerGuides from "./BrokerGuides";

function mount() {
  return render(<MemoryRouter><BrokerGuides /></MemoryRouter>);
}

test("lists every phase-1 broker, all collapsed", () => {
  mount();
  for (const name of ["Interactive Brokers", "Degiro", "XTB", "Charles Schwab", "Fidelity", "eToro"]) {
    const button = screen.getByRole("button", { name: new RegExp(name, "i") });
    expect(button).toHaveAttribute("aria-expanded", "false");
  }
});

test("expands the IBKR guide with required Flex sections", () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: /Interactive Brokers/i }));
  expect(screen.getByRole("button", { name: /Interactive Brokers/i })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText(/Cash Transactions/)).toBeInTheDocument();
  expect(screen.getByText(/Corporate Actions/)).toBeInTheDocument();
});

test("opens one guide at a time and toggles closed", () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: /Degiro/i }));
  expect(screen.getByText("Inbox → Account Statement")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /XTB/i }));
  expect(screen.queryByText("Inbox → Account Statement")).not.toBeInTheDocument();
  expect(screen.getByText(/Cash operations/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /XTB/i }));
  expect(screen.queryByText(/Cash operations/i)).not.toBeInTheDocument();
});

test("points eToro to the API key in Settings instead of a file", () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: /eToro/i }));
  expect(screen.getByText(/API Key Management/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Settings → Connections/i })).toHaveAttribute("href", "/settings?section=connections");
});
