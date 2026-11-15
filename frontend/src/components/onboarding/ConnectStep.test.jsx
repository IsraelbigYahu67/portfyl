import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { legacyColorClassesIn } from "../../test/legacyClasses";

import OnboardingView from "./OnboardingView";

const noop = () => {};

function handlers() {
  return {
    onSubmit: vi.fn(),
    onUpgrade: vi.fn(),
    onImportFree: vi.fn(),
    onBack: vi.fn(),
    onChangeBroker: vi.fn(),
    onDemo: vi.fn(),
    onRecheck: vi.fn(),
  };
}

function connectProps(overrides = {}) {
  return {
    phase: "form",
    billingEnabled: false,
    canManageBilling: false,
    investorMonthlyCents: null,
    notice: null,
    error: null,
    locked: false,
    ...handlers(),
    ...overrides,
  };
}

function renderStep(brokerKey, connect, props = {}) {
  render(
    <MemoryRouter>
      <OnboardingView
        brokerKey={brokerKey}
        connect={connect}
        onBrokerChange={noop}
        onUnsupportedChange={noop}
        onChoose={noop}
        onStartBlank={noop}
        {...props}
      />
    </MemoryRouter>
  );
}

describe("ConnectStep", () => {
  it("uses only token-based colors", async () => {
    expect(await legacyColorClassesIn(new URL("./ConnectStep.jsx", import.meta.url))).toEqual([]);
  });

  it("keeps the typed credentials when a failed connect returns to the form", () => {
    const view = (phase) => (
      <MemoryRouter>
        <OnboardingView brokerKey="trading212" connect={connectProps({ phase })} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    const { rerender } = render(view("form"));
    fireEvent.change(screen.getByLabelText("API key ID"), { target: { value: "key-1" } });
    fireEvent.change(screen.getByLabelText("Secret key"), { target: { value: "secret-1" } });

    rerender(view("connecting"));
    rerender(view("form"));

    expect(screen.getByLabelText("API key ID")).toHaveValue("key-1");
    expect(screen.getByLabelText("Secret key")).toHaveValue("secret-1");
  });

  it("shows the plan gate before any credential field", () => {
    const connect = connectProps({ phase: "gated" });
    renderStep("trading212", connect);

    expect(screen.getByRole("heading", { name: "Connect Trading 212" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Automatic sync is part of Investor" })).toBeInTheDocument();
    expect(screen.queryByLabelText("API key ID")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Use Investor for testing" }));
    expect(connect.onUpgrade).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Import your Trading 212 CSV for free" }));
    expect(connect.onImportFree).toHaveBeenCalledTimes(1);
  });

  it("formats the Investor price", () => {
    renderStep("trading212", connectProps({ phase: "gated", investorMonthlyCents: 599 }));
    expect(screen.getByText(/€5\.99/)).toBeInTheDocument();
  });

  it("requires consent before checkout when billing is on", () => {
    const connect = connectProps({ phase: "gated", billingEnabled: true, canManageBilling: true, investorMonthlyCents: 599 });
    renderStep("trading212", connect);

    const upgrade = screen.getByRole("button", { name: "Upgrade to Investor" });
    expect(upgrade).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", {
      name: "I want my subscription to start immediately. I understand that once it starts I lose my 14-day right of withdrawal for this digital service.",
    }));
    expect(upgrade).toBeEnabled();
    fireEvent.click(upgrade);
    expect(connect.onUpgrade).toHaveBeenCalledTimes(1);
  });

  it("tells a non-owner who can upgrade", () => {
    renderStep("trading212", connectProps({ phase: "gated", billingEnabled: true, canManageBilling: false }));

    expect(screen.getByText("Only the workspace owner can change the plan or manage billing.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upgrade to Investor" })).not.toBeInTheDocument();
  });

  it("offers eToro only the upgrade, another broker and the demo", () => {
    const connect = connectProps({ phase: "gated" });
    renderStep("etoro", connect);

    expect(screen.queryByRole("button", { name: /for free/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose another broker" }));
    expect(connect.onChangeBroker).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Look around with sample data (free)" }));
    expect(connect.onDemo).toHaveBeenCalledTimes(1);
  });

  it("shows each broker's guide and form", () => {
    const t212 = connectProps();
    const { unmount: unmountT212 } = render(
      <MemoryRouter>
        <OnboardingView brokerKey="trading212" connect={t212} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    expect(screen.getByRole("heading", { name: "How to connect Trading 212" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("API key ID"), { target: { value: "key" } });
    fireEvent.change(screen.getByLabelText("Secret key"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(t212.onSubmit).toHaveBeenCalledWith({ apiKey: "key", apiSecret: "secret" });
    unmountT212();

    const ibkr = connectProps();
    const { unmount: unmountIbkr } = render(
      <MemoryRouter>
        <OnboardingView brokerKey="ibkr" connect={ibkr} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    expect(screen.getByText("How to set up the IBKR Flex Query")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Flex Web Service token"), { target: { value: "tok" } });
    fireEvent.change(screen.getByLabelText("Flex Query ID"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(ibkr.onSubmit).toHaveBeenCalledWith({ flexToken: "tok", queryId: "123" });
    unmountIbkr();

    const etoro = connectProps();
    render(
      <MemoryRouter>
        <OnboardingView brokerKey="etoro" connect={etoro} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    expect(screen.getByText("How to create an eToro API key")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("eToro API key"), { target: { value: "ek" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(etoro.onSubmit).toHaveBeenCalledWith({ userKey: "ek" });
  });

  it("shows progress without Back while connecting and syncing", () => {
    renderStep("ibkr", connectProps({ phase: "syncing" }));
    expect(screen.getByRole("status")).toHaveTextContent("Importing your history from Interactive Brokers…");
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  });

  it("shows the connecting progress", () => {
    renderStep("ibkr", connectProps({ phase: "connecting" }));
    expect(screen.getByRole("status")).toHaveTextContent("Connecting to Interactive Brokers…");
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  });

  it("hides Back once the portfolio holds a connection", () => {
    renderStep("trading212", connectProps({ locked: true }));
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  });

  it("shows Back on the form and calls onBack", () => {
    const connect = connectProps();
    renderStep("trading212", connect);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(connect.onBack).toHaveBeenCalledTimes(1);
  });

  it("disables every button while the parent is busy", () => {
    renderStep("trading212", connectProps({ phase: "gated" }), { busy: "demo" });
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
  });

  it("renders unavailable, sync-failed and both notices", () => {
    const unavailable = connectProps({ phase: "unavailable" });
    const { unmount: unmountUnavailable } = render(
      <MemoryRouter>
        <OnboardingView brokerKey="etoro" connect={unavailable} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    expect(screen.getByText("Connecting eToro is temporarily unavailable. Choose another broker or look around with sample data.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose another broker" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Look around with sample data (free)" })).toBeInTheDocument();
    unmountUnavailable();

    const failed = connectProps({ phase: "sync-failed", error: "Sync failed" });
    const { unmount: unmountFailed } = render(
      <MemoryRouter>
        <OnboardingView brokerKey="ibkr" connect={failed} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Sync failed");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(failed.onRecheck).toHaveBeenCalledTimes(1);
    unmountFailed();

    const canceled = connectProps({ phase: "gated", notice: "canceled" });
    const { unmount: unmountCanceled } = render(
      <MemoryRouter>
        <OnboardingView brokerKey="trading212" connect={canceled} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    expect(screen.getByText("Checkout was cancelled. You have not been charged.")).toBeInTheDocument();
    unmountCanceled();

    const processing = connectProps({ phase: "gated", notice: "processing" });
    render(
      <MemoryRouter>
        <OnboardingView brokerKey="trading212" connect={processing} onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </MemoryRouter>
    );
    expect(screen.getByText("Your payment is being processed. Your plan will switch shortly.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(processing.onRecheck).toHaveBeenCalledTimes(1);
  });

  it("shows a loading status while the plan is checked", () => {
    renderStep("trading212", connectProps({ phase: "loading", billingEnabled: undefined }));
    expect(screen.getByRole("status")).toHaveTextContent("Checking your plan…");
  });
});
