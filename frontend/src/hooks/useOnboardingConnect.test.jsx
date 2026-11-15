import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { StrictMode } from "react";

import { fetchEditionOnboardingPlan } from "@edition-manifest";
import {
  activatePortfolio,
  confirmCheckout,
  connectEtoro,
  connectIBKR,
  connectT212,
  createPendingImportPortfolio,
  fetchEtoroStatus,
  fetchIBKRStatus,
  fetchT212Status,
  startCheckout,
  syncEtoro,
  syncIBKR,
  syncT212,
  updateTestPlan,
} from "../api";
import { findSupportedBroker } from "../lib/onboardingBrokers";
import { clearConnectStep, connectStepBroker } from "../lib/onboardingConnect";
import { clearIntendedBroker, intendedBroker } from "../lib/signupIntent";

import { useOnboardingConnect } from "./useOnboardingConnect";

vi.mock("@edition-manifest", () => ({ fetchEditionOnboardingPlan: vi.fn() }));
vi.mock("../api", () => ({
  activatePortfolio: vi.fn(),
  confirmCheckout: vi.fn(),
  connectEtoro: vi.fn(),
  connectIBKR: vi.fn(),
  connectT212: vi.fn(),
  createPendingImportPortfolio: vi.fn(),
  fetchEtoroStatus: vi.fn(),
  fetchIBKRStatus: vi.fn(),
  fetchT212Status: vi.fn(),
  startCheckout: vi.fn(),
  syncEtoro: vi.fn(),
  syncIBKR: vi.fn(),
  syncT212: vi.fn(),
  updateTestPlan: vi.fn(),
}));

const QUIET = { suppressEntitlementPrompt: true };
const T212 = findSupportedBroker("trading212");
const IBKR = findSupportedBroker("ibkr");
const ETORO = findSupportedBroker("etoro");

const paid = { brokerSync: true, billingEnabled: false, canManageBilling: false, investorMonthlyCents: null };
const free = { brokerSync: false, billingEnabled: false, canManageBilling: false, investorMonthlyCents: null };
const freeBilling = { brokerSync: false, billingEnabled: true, canManageBilling: true, investorMonthlyCents: 599 };

function renderConnect(initialProps = {}, { strict = false } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const props = {
    broker: T212,
    pendingPortfolio: null,
    setCurrentId: vi.fn(),
    checkoutReturn: null,
    onCheckoutReturnHandled: vi.fn(),
    onFinished: vi.fn(),
    ...initialProps,
  };
  const wrapper = ({ children }) => {
    const tree = <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    return strict ? <StrictMode>{tree}</StrictMode> : tree;
  };
  const view = renderHook((hookProps) => useOnboardingConnect(hookProps), { initialProps: props, wrapper });
  return { ...view, props, client };
}

const httpError = (status, data) => ({ response: { status, data } });

describe("useOnboardingConnect", () => {
  let assign;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    clearConnectStep();
    clearIntendedBroker();
    assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    fetchEditionOnboardingPlan.mockResolvedValue(paid);
    createPendingImportPortfolio.mockResolvedValue({ id: "p1" });
    activatePortfolio.mockResolvedValue({ activation_state: "active" });
    connectT212.mockResolvedValue({});
    connectIBKR.mockResolvedValue({});
    connectEtoro.mockResolvedValue({});
    syncT212.mockResolvedValue({ snapshot: { positions: 0 }, history: { status: "queued" } });
    syncIBKR.mockResolvedValue({ ledger: { imported: 3 } });
    syncEtoro.mockResolvedValue({ imported: 2 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stays idle without a broker", async () => {
    const { result } = renderConnect({ broker: null });
    expect(result.current.phase).toBe("loading");
    await Promise.resolve();
    expect(fetchEditionOnboardingPlan).not.toHaveBeenCalled();
  });

  it("shows the form for a plan with broker_sync", async () => {
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("form"));
    expect(result.current.plan).toEqual(paid);
  });

  it("gates a plan without broker_sync before any credential request", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue(free);
    const { result } = renderConnect();

    await waitFor(() => expect(result.current.phase).toBe("gated"));
    expect(connectT212).not.toHaveBeenCalled();
    expect(fetchT212Status).not.toHaveBeenCalled();
  });

  it("switches to Investor in test mode and shows the form", async () => {
    fetchEditionOnboardingPlan.mockResolvedValueOnce(free).mockResolvedValue(paid);
    updateTestPlan.mockResolvedValue({ plan: "investor" });
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("gated"));

    await act(() => result.current.upgrade());

    expect(updateTestPlan).toHaveBeenCalledTimes(1);
    expect(updateTestPlan).toHaveBeenCalledWith("investor");
    await waitFor(() => expect(result.current.phase).toBe("form"));
  });

  it("shows a message when the test plan cannot be switched", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue(free);
    updateTestPlan.mockRejectedValue(new Error("boom"));
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("gated"));

    await act(() => result.current.upgrade());

    expect(result.current.error).toBe("The plan could not be changed. Please try again.");
    expect(result.current.phase).toBe("gated");
  });

  it("starts checkout and remembers the step", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue(freeBilling);
    startCheckout.mockResolvedValue({ url: "https://checkout.example/c1" });
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("gated"));

    await act(() => result.current.upgrade());

    expect(startCheckout).toHaveBeenCalledWith("investor");
    expect(assign).toHaveBeenCalledWith("https://checkout.example/c1");
    expect(connectStepBroker()).toBe("trading212");
    expect(intendedBroker()).toBe("trading212");
  });

  it("maps workspace_owner_required to the owner message", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue(freeBilling);
    startCheckout.mockRejectedValue(httpError(403, { detail: { code: "workspace_owner_required" } }));
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("gated"));

    await act(() => result.current.upgrade());

    expect(result.current.error).toBe("Only the workspace owner can change the plan or manage billing.");
    expect(assign).not.toHaveBeenCalled();
  });

  it("re-checks the plan when a subscription already exists", async () => {
    fetchEditionOnboardingPlan.mockResolvedValueOnce(freeBilling).mockResolvedValue({ ...freeBilling, brokerSync: true });
    startCheckout.mockRejectedValue(httpError(409, { detail: { code: "subscription_exists" } }));
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("gated"));

    await act(() => result.current.upgrade());

    await waitFor(() => expect(result.current.phase).toBe("form"));
  });

  it("shows a generic message when the payment page cannot be opened", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue(freeBilling);
    startCheckout.mockRejectedValue(new Error("boom"));
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("gated"));

    await act(() => result.current.upgrade());

    expect(result.current.error).toBe("The payment page could not be opened. Please try again.");
  });

  it("confirms a successful checkout and shows the form", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue({ ...paid, billingEnabled: true, canManageBilling: true });
    confirmCheckout.mockResolvedValue({ checkout_status: "complete" });
    const { result, props } = renderConnect({ checkoutReturn: { outcome: "success", sessionId: "cs_1" } });

    await waitFor(() => expect(result.current.phase).toBe("form"));
    expect(confirmCheckout).toHaveBeenCalledWith("cs_1");
    expect(props.onCheckoutReturnHandled).toHaveBeenCalledTimes(1);
    expect(result.current.notice).toBeNull();
  });

  it("handles a checkout return once under StrictMode", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue({ ...paid, billingEnabled: true, canManageBilling: true });
    confirmCheckout.mockResolvedValue({ checkout_status: "complete" });
    const { result, props } = renderConnect({ checkoutReturn: { outcome: "success", sessionId: "cs_1" } }, { strict: true });

    await waitFor(() => expect(result.current.phase).toBe("form"));
    expect(confirmCheckout).toHaveBeenCalledTimes(1);
    expect(props.onCheckoutReturnHandled).toHaveBeenCalledTimes(1);
  });

  it("shows processing when the checkout is not complete yet", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue({ ...freeBilling });
    confirmCheckout.mockResolvedValue({ checkout_status: "open" });
    const { result } = renderConnect({ checkoutReturn: { outcome: "success", sessionId: "cs_1" } });

    await waitFor(() => expect(result.current.phase).toBe("gated"));
    expect(result.current.notice).toBe("processing");
  });

  it("shows processing when confirming the checkout fails", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue({ ...freeBilling });
    confirmCheckout.mockRejectedValue(new Error("boom"));
    const { result } = renderConnect({ checkoutReturn: { outcome: "success", sessionId: "cs_1" } });

    await waitFor(() => expect(result.current.phase).toBe("gated"));
    expect(result.current.notice).toBe("processing");
  });

  it("shows the cancellation note and keeps the gate", async () => {
    fetchEditionOnboardingPlan.mockResolvedValue(freeBilling);
    const { result } = renderConnect({ checkoutReturn: { outcome: "canceled", sessionId: null } });

    await waitFor(() => expect(result.current.phase).toBe("gated"));
    expect(result.current.notice).toBe("canceled");
    expect(confirmCheckout).not.toHaveBeenCalled();
  });

  it("connects into the pending portfolio, syncs and finishes", async () => {
    const { result, props } = renderConnect({ broker: IBKR });
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ flexToken: " tok ", queryId: " 123 " }));

    expect(createPendingImportPortfolio).toHaveBeenCalledTimes(1);
    expect(props.setCurrentId).toHaveBeenCalledWith("p1");
    expect(connectIBKR).toHaveBeenCalledWith("tok", "123", QUIET);
    expect(syncIBKR).toHaveBeenCalledWith(QUIET);
    expect(activatePortfolio).toHaveBeenCalledWith("p1");
    expect(props.onFinished).toHaveBeenCalledWith({ imported: true });
    expect(result.current.locked).toBe(true);
  });

  it("uses an existing empty pending portfolio instead of creating one", async () => {
    fetchT212Status.mockResolvedValue({ connected: false });
    const { result, props } = renderConnect({ pendingPortfolio: { id: "pending-1" } });
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ apiKey: "k", apiSecret: "s" }));

    expect(createPendingImportPortfolio).not.toHaveBeenCalled();
    expect(connectT212).toHaveBeenCalledWith("k", "s", QUIET);
    expect(activatePortfolio).toHaveBeenCalledWith("pending-1");
    expect(props.onFinished).toHaveBeenCalledWith({ imported: false });
  });

  it("finishes T212 right after the 202 snapshot", async () => {
    const { result, props } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ apiKey: "k", apiSecret: "s" }));

    expect(syncT212).toHaveBeenCalledWith(QUIET);
    expect(activatePortfolio).toHaveBeenCalledWith("p1");
    expect(props.onFinished).toHaveBeenCalledWith({ imported: false });
  });

  it("treats 409 on activate as success", async () => {
    activatePortfolio.mockRejectedValue(httpError(409, { detail: "Only an empty pending portfolio can be activated" }));
    const { result, props } = renderConnect({ broker: IBKR });
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ flexToken: "tok", queryId: "123" }));

    expect(props.onFinished).toHaveBeenCalledWith({ imported: true });
    expect(result.current.phase).not.toBe("sync-failed");
  });

  it("resumes a connected pending portfolio without connecting again", async () => {
    fetchT212Status.mockResolvedValue({ connected: true, last_synced_at: null });
    const { result, props } = renderConnect({ pendingPortfolio: { id: "pending-1" } });

    await waitFor(() => expect(props.onFinished).toHaveBeenCalledTimes(1));
    expect(connectT212).not.toHaveBeenCalled();
    expect(syncT212).toHaveBeenCalledTimes(1);
    expect(activatePortfolio).toHaveBeenCalledWith("pending-1");
    expect(result.current.locked).toBe(true);
  });

  it("does not sync again when the connected portfolio already synced", async () => {
    fetchT212Status.mockResolvedValue({ connected: true, last_synced_at: "2026-11-15T10:00:00Z" });
    const { props } = renderConnect({ pendingPortfolio: { id: "pending-1" } });

    await waitFor(() => expect(props.onFinished).toHaveBeenCalledWith({ imported: false }));
    expect(syncT212).not.toHaveBeenCalled();
    expect(connectT212).not.toHaveBeenCalled();
    expect(activatePortfolio).toHaveBeenCalledWith("pending-1");
  });

  it("resumes once under StrictMode", async () => {
    fetchT212Status.mockResolvedValue({ connected: true, last_synced_at: null });
    const { props } = renderConnect({ pendingPortfolio: { id: "pending-1" } }, { strict: true });

    await waitFor(() => expect(props.onFinished).toHaveBeenCalledTimes(1));
    expect(syncT212).toHaveBeenCalledTimes(1);
  });

  it("turns a plan_upgrade_required connect into the gated state", async () => {
    connectT212.mockRejectedValue(httpError(403, { code: "plan_upgrade_required" }));
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("form"));
    fetchEditionOnboardingPlan.mockResolvedValue(free);

    await act(() => result.current.submit({ apiKey: "k", apiSecret: "s" }));

    expect(result.current.phase).toBe("gated");
    expect(result.current.error).toBeNull();
    expect(result.current.plan).toEqual(free);
  });

  it("shows eToro unavailable on 503", async () => {
    connectEtoro.mockRejectedValue(httpError(503, { detail: "eToro is not configured" }));
    const { result } = renderConnect({ broker: ETORO });
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ userKey: "ek" }));

    expect(result.current.phase).toBe("unavailable");
    expect(result.current.error).toBeNull();
  });

  it("shows eToro unavailable when the server has no app key", async () => {
    fetchEtoroStatus.mockResolvedValue({ connected: false, configured: false });
    const { result } = renderConnect({ broker: ETORO, pendingPortfolio: { id: "pending-1" } });

    await waitFor(() => expect(result.current.phase).toBe("unavailable"));
    expect(fetchEditionOnboardingPlan).not.toHaveBeenCalled();
  });

  it("keeps the user on the form with the server's message when connect fails", async () => {
    connectT212.mockRejectedValue(httpError(400, { detail: "Invalid API key" }));
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ apiKey: "k", apiSecret: "s" }));

    expect(result.current.phase).toBe("form");
    expect(result.current.error).toBe("Invalid API key");
    expect(result.current.locked).toBe(false);
  });

  it("does not create a second pending portfolio on a retry", async () => {
    connectT212.mockRejectedValueOnce(httpError(400, { detail: "Invalid API key" }));
    const { result } = renderConnect();
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ apiKey: "k", apiSecret: "bad" }));
    await act(() => result.current.submit({ apiKey: "k", apiSecret: "good" }));

    expect(createPendingImportPortfolio).toHaveBeenCalledTimes(1);
    expect(activatePortfolio).toHaveBeenCalledWith("p1");
  });

  it("offers a retry when the sync fails after connecting", async () => {
    syncIBKR.mockRejectedValueOnce(httpError(502, { detail: "IBKR is down" }));
    const { result, props } = renderConnect({ broker: IBKR });
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(() => result.current.submit({ flexToken: "tok", queryId: "123" }));

    expect(result.current.phase).toBe("sync-failed");
    expect(result.current.error).toBe("IBKR is down");
    expect(activatePortfolio).not.toHaveBeenCalled();

    // The page's list has caught up: the pending portfolio is now connected.
    fetchIBKRStatus.mockResolvedValue({ connected: true, last_synced_at: null });
    await act(() => result.current.recheck());

    await waitFor(() => expect(props.onFinished).toHaveBeenCalledTimes(1));
    expect(connectIBKR).toHaveBeenCalledTimes(1);
    expect(syncIBKR).toHaveBeenCalledTimes(2);
  });

  it("reports a plan load failure and retries", async () => {
    fetchEditionOnboardingPlan.mockRejectedValueOnce(new Error("offline")).mockResolvedValue(paid);
    const { result } = renderConnect();

    await waitFor(() => expect(result.current.phase).toBe("load-error"));
    expect(result.current.error).toBe("We couldn't check your plan. Please try again.");

    await act(() => result.current.recheck());
    await waitFor(() => expect(result.current.phase).toBe("form"));
    expect(result.current.error).toBeNull();
  });

  it("retries a checkout return whose plan read failed", async () => {
    const billing = { ...paid, billingEnabled: true, canManageBilling: true };
    fetchEditionOnboardingPlan.mockRejectedValueOnce(new Error("offline")).mockResolvedValue(billing);
    confirmCheckout.mockResolvedValue({ checkout_status: "complete" });
    const { result } = renderConnect({ checkoutReturn: { outcome: "success", sessionId: "cs_1" } });

    await waitFor(() => expect(result.current.phase).toBe("load-error"));
    expect(confirmCheckout).not.toHaveBeenCalled();

    await act(() => result.current.recheck());
    await waitFor(() => expect(result.current.phase).not.toBe("load-error"));
    expect(confirmCheckout).toHaveBeenCalledTimes(1);
    expect(confirmCheckout).toHaveBeenCalledWith("cs_1");
    await waitFor(() => expect(result.current.phase).toBe("form"));
  });

  it("drops a late answer after the broker changed", async () => {
    let releaseFirst;
    fetchEditionOnboardingPlan
      .mockImplementationOnce(() => new Promise((resolve) => { releaseFirst = resolve; }))
      .mockResolvedValue(paid);
    const { result, rerender, props } = renderConnect();

    rerender({ ...props, broker: IBKR });
    await waitFor(() => expect(result.current.phase).toBe("form"));

    await act(async () => {
      releaseFirst(free);
      await Promise.resolve();
    });
    expect(result.current.phase).toBe("form");
    expect(result.current.plan).toEqual(paid);
  });
});
