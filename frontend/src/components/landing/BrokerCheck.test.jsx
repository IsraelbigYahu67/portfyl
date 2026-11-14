import { renderToString } from "react-dom/server";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AnalyticsProvider from "../../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../../analytics/analyticsClient";
import BrokerCheck from "./BrokerCheck";
import { COPY } from "../../pages/welcomeCopy";
import { registerUrl } from "../../lib/signupIntent";

const copy = COPY.cs.brokerCheck;

function renderCheck(props = {}) {
  return render(<BrokerCheck copy={copy} language="cs" onDemo={() => {}} {...props} />);
}

function type(value) {
  fireEvent.change(screen.getByRole("searchbox"), { target: { value } });
}

it("tells a visitor their broker is supported and links to registration with the broker and language", () => {
  renderCheck({ signupOpen: true });
  type("xtb");
  expect(screen.getByText(copy.supported.replace("{name}", "XTB"))).toBeInTheDocument();
  const signup = screen.getByRole("link", { name: copy.signup });
  expect(signup).toHaveAttribute("href", registerUrl({ source: "landing_broker_check", broker: "xtb", lang: "cs" }));
  expect(screen.getByRole("link", { name: copy.demo })).toHaveAttribute("href", "/demo");
});

it("offers the demo and the beta note, but no register link, while signup is closed", () => {
  renderCheck({ signupOpen: false });
  type("xtb");
  expect(screen.getByText(copy.supported.replace("{name}", "XTB"))).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: copy.signup })).not.toBeInTheDocument();
  expect(screen.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["/demo"]);
  expect(screen.getByRole("link", { name: copy.demo })).toBeInTheDocument();
  expect(screen.getByText(copy.betaNote)).toBeInTheDocument();
});

it("keeps signup closed by default (private beta)", () => {
  renderCheck();
  type("XTB");
  expect(screen.getByText(copy.betaNote)).toBeInTheDocument();
});

it("says an unsupported broker is not readable yet and points to the demo", () => {
  renderCheck({ signupOpen: true });
  type("Revolut");
  expect(screen.getByText(copy.unsupported.replace("{name}", "Revolut"))).toBeInTheDocument();
  expect(screen.getByRole("link", { name: copy.demo })).toHaveAttribute("href", "/demo");
  expect(screen.queryByRole("link", { name: copy.signup })).not.toBeInTheDocument();
});

it("treats a name that matches nothing as unsupported and renders it as plain text", () => {
  renderCheck();
  type("  <b>Foo</b>   Bar ");
  expect(screen.getByText(copy.unsupported.replace("{name}", "<b>Foo</b> Bar"))).toBeInTheDocument();
  expect(document.querySelector(".broker-check-result b")).toBeNull();
});

it("shows nothing for an empty or blank query", () => {
  renderCheck();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  type("   ");
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

it("offers chips for several matches and a click selects one", () => {
  renderCheck({ signupOpen: true });
  type("e");
  expect(screen.queryByRole("link", { name: copy.signup })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Degiro/ }));
  expect(screen.getByRole("searchbox")).toHaveValue("Degiro");
  expect(screen.getByText(copy.supported.replace("{name}", "Degiro"))).toBeInTheDocument();
  expect(screen.getByRole("link", { name: copy.signup })).toHaveAttribute(
    "href", registerUrl({ source: "landing_broker_check", broker: "degiro", lang: "cs" }),
  );
});

it("calls onDemo when the demo link is clicked", () => {
  const onDemo = vi.fn();
  renderCheck({ onDemo });
  type("Revolut");
  fireEvent.click(screen.getByRole("link", { name: copy.demo }));
  expect(onDemo).toHaveBeenCalledTimes(1);
});

test("renders the same HTML on the server", () => {
  const html = renderToString(<BrokerCheck copy={copy} language="cs" />);
  expect(html).toContain(copy.title);
  expect(html).not.toContain("broker-check-result");
  expect(html).not.toContain("/demo");
  expect(renderToString(<BrokerCheck copy={copy} language="cs" />)).toBe(html);
});

describe("broker_check_used analytics", () => {
  function renderTracked(language = "cs") {
    const adapter = createMemoryAdapter();
    render(
      <AnalyticsProvider initialConsent="accepted" adapterFactory={() => adapter}>
        <BrokerCheck copy={copy} language={language} onDemo={() => {}} />
      </AnalyticsProvider>,
    );
    const used = () => adapter.events.filter(([name]) => name === "broker_check_used");
    return { used };
  }

  it("emits one event for x, xt, xtb typed in turn", async () => {
    const { used } = renderTracked();
    for (const value of ["x", "xt", "xtb"]) type(value);
    await waitFor(() => expect(used()).toHaveLength(1));
    expect(used()[0][1]).toEqual({ result: "supported", language: "cs" });
  });

  it("emits nothing for an empty query and one unsupported event per distinct unsupported run", async () => {
    const { used } = renderTracked("de");
    expect(used()).toHaveLength(0);
    for (const value of ["Rev", "Revo", "Revolut"]) type(value);
    await waitFor(() => expect(used()).toHaveLength(1));
    expect(used()[0][1]).toEqual({ result: "unsupported", language: "de" });
  });

  it("does not send the typed name", async () => {
    const { used } = renderTracked();
    type("Revolut");
    await waitFor(() => expect(used()).toHaveLength(1));
    expect(JSON.stringify(used())).not.toMatch(/revolut/i);
  });
});
