import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import BrokerGuides from "./BrokerGuides";

// A guide with screenshots, to prove they render after the steps. The shipped
// map is empty until real screenshots exist.
vi.mock("../../lib/brokerGuideImages", () => ({
  BROKER_GUIDE_IMAGES: { xtb: [{ src: "/x.png", alt: "XTB export menu" }] },
}));

function mount() {
  return render(<MemoryRouter><BrokerGuides /></MemoryRouter>);
}

test("lists every phase-1 broker, all collapsed", () => {
  mount();
  for (const name of ["Trading 212", "Interactive Brokers", "Degiro", "XTB", "Charles Schwab", "Fidelity", "eToro"]) {
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

test("renders just one guide, expanded and without the accordion, when `only` is set", () => {
  render(<MemoryRouter><BrokerGuides only="xtb" /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "How to get the file from XTB" })).toBeInTheDocument();
  expect(screen.getByText(/Cash operations/i)).toBeInTheDocument();
  expect(document.querySelector("button[aria-expanded]")).toBeNull();
  expect(screen.queryByText("Degiro")).not.toBeInTheDocument();
});

test("renders nothing for an unknown `only` guide", () => {
  const { container } = render(<MemoryRouter><BrokerGuides only="nope" /></MemoryRouter>);
  expect(container).toBeEmptyDOMElement();
});

test("has a Trading 212 guide", () => {
  render(<MemoryRouter><BrokerGuides only="trading212" /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "How to get the file from Trading 212" })).toBeInTheDocument();
  expect(screen.getByText("Export history")).toBeInTheDocument();
});

test("shows a guide's screenshots lazily after its steps", () => {
  render(<MemoryRouter><BrokerGuides only="xtb" /></MemoryRouter>);
  const image = screen.getByAltText("XTB export menu");
  expect(image).toHaveAttribute("src", "/x.png");
  expect(image).toHaveAttribute("loading", "lazy");
  expect(image).toHaveClass("rounded-xl");
  expect(screen.getByRole("list").compareDocumentPosition(image) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("shows screenshots in the accordion too", () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: /XTB/i }));
  expect(screen.getByAltText("XTB export menu")).toBeInTheDocument();
});
