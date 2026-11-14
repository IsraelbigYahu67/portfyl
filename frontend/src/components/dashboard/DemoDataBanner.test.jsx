import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import DemoDataBanner from "./DemoDataBanner";

afterEach(() => localStorage.clear());

const renderBanner = (portfolio) => render(
  <MemoryRouter>
    <DemoDataBanner portfolio={portfolio} />
  </MemoryRouter>,
);

describe("DemoDataBanner", () => {
  it("links to the import of the remembered broker", () => {
    localStorage.setItem("portfyl_intended_broker", "xtb");
    renderBanner({ brokers: ["demo"] });
    expect(screen.getByText("You're looking at sample data.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import your own portfolio" })).toHaveAttribute("href", "/import?broker=xtb");
  });

  it("links to the plain import when no broker is remembered", () => {
    renderBanner({ brokers: ["demo"] });
    expect(screen.getByRole("link", { name: "Import your own portfolio" })).toHaveAttribute("href", "/import");
  });

  it("ignores an unsupported remembered broker", () => {
    localStorage.setItem("portfyl_intended_broker", "not-a-broker");
    renderBanner({ brokers: ["demo"] });
    expect(screen.getByRole("link", { name: "Import your own portfolio" })).toHaveAttribute("href", "/import");
  });

  it("renders nothing for a real portfolio", () => {
    const { container } = renderBanner({ brokers: ["xtb"] });
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing without a portfolio", () => {
    expect(renderBanner(undefined).container).toBeEmptyDOMElement();
    expect(renderBanner({}).container).toBeEmptyDOMElement();
  });
});
