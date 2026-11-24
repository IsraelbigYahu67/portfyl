import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DataPrivacySettings from "./DataPrivacySettings";
import { legacyColorClassesIn } from "../test/legacyClasses";

// The suite stubs the global URL for blob downloads; keep the real one for path lookups.
const NativeURL = URL;
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";


const mocks = vi.hoisted(() => ({
  fetchDeletionStatus: vi.fn(),
  fetchBillingStatus: vi.fn(),
  downloadWorkspaceExport: vi.fn(),
  deleteWorkspaceNow: vi.fn(),
  cancelWorkspaceDeletion: vi.fn(),
  openBillingPortal: vi.fn(),
  reauthenticateWithPassword: vi.fn(),
  reauthenticateWithGoogle: vi.fn(),
  prepareGoogleSignIn: vi.fn(),
  isGoogleSignInEnabled: vi.fn(),
  accountDeleted: vi.fn(),
  reloadAccount: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchDeletionStatus: mocks.fetchDeletionStatus,
  fetchBillingStatus: mocks.fetchBillingStatus,
  downloadWorkspaceExport: mocks.downloadWorkspaceExport,
  deleteWorkspaceNow: mocks.deleteWorkspaceNow,
  cancelWorkspaceDeletion: mocks.cancelWorkspaceDeletion,
  openBillingPortal: mocks.openBillingPortal,
}));

vi.mock("../auth/firebase", () => ({
  reauthenticateWithPassword: mocks.reauthenticateWithPassword,
  reauthenticateWithGoogle: mocks.reauthenticateWithGoogle,
  prepareGoogleSignIn: mocks.prepareGoogleSignIn,
  isGoogleSignInEnabled: mocks.isGoogleSignInEnabled,
  mapFirebaseAuthError: (err) => err?.code,
}));

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { email: "alice@example.com" },
    currentWorkspace: { id: "workspace-uuid", name: "Alice workspace" },
    accountDeleted: mocks.accountDeleted,
    reloadAccount: mocks.reloadAccount,
  }),
}));


function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AnalyticsProvider initialConsent="pending" adapterFactory={() => createMemoryAdapter()}>
        <DataPrivacySettings />
      </AnalyticsProvider>
    </QueryClientProvider>
  );
}


// Opens the dialog and sits through the 10 second warning. Only the timeout
// timers are faked, and only for the wait, so React Query and waitFor keep
// running on real ones.
async function openDialogPastWarning() {
  const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  try {
    fireEvent.click(opener);
    for (let i = 0; i < 10; i += 1) act(() => { vi.advanceTimersByTime(1000); });
  } finally {
    vi.useRealTimers();
  }
  const proceed = await screen.findByRole("button", { name: /i understand, continue/i });
  await waitFor(() => expect(proceed).toBeEnabled());
  fireEvent.click(proceed);
}


// Opens the dialog and waits out the countdown, without pressing continue.
async function openWarningAndWait() {
  const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  try {
    fireEvent.click(opener);
    for (let i = 0; i < 10; i += 1) act(() => { vi.advanceTimersByTime(1000); });
  } finally {
    vi.useRealTimers();
  }
}


// Types the confirmation and password, then presses the destructive button.
function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText(/type alice workspace/i), { target: { value: "Alice workspace" } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button", { name: /delete permanently now/i }));
}


describe("DataPrivacySettings", () => {
  beforeEach(() => {
    mocks.fetchDeletionStatus.mockReset().mockResolvedValue({ scheduled: false });
    mocks.fetchBillingStatus.mockReset().mockResolvedValue({ subscription: null });
    mocks.accountDeleted.mockReset();
    mocks.reloadAccount.mockReset().mockResolvedValue({});
    mocks.downloadWorkspaceExport.mockReset().mockResolvedValue({
      blob: new Blob(["{}"], { type: "application/json" }),
      filename: "portfyl-workspace-export.json",
    });
    mocks.deleteWorkspaceNow.mockReset().mockResolvedValue({ deleted: true, account_deleted: true });
    mocks.cancelWorkspaceDeletion.mockReset().mockResolvedValue(undefined);
    mocks.openBillingPortal.mockReset().mockResolvedValue({ url: "https://billing.stripe.test/p" });
    mocks.reauthenticateWithPassword.mockReset().mockResolvedValue("fresh-id-token");
    mocks.reauthenticateWithGoogle.mockReset().mockResolvedValue("fresh-google-token");
    mocks.prepareGoogleSignIn.mockReset().mockResolvedValue(undefined);
    mocks.isGoogleSignInEnabled.mockReset().mockReturnValue(false);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:workspace-export"),
      revokeObjectURL: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("embeds the analytics preferences section", async () => {
    mount();
    expect(await screen.findByRole("region", { name: "Analytics preferences" })).toBeInTheDocument();
    expect(screen.getByText("Analytics: awaiting your decision")).toBeInTheDocument();
  });

  it("shows analytics preferences in an inset well rather than a second raised card", async () => {
    mount();
    const region = await screen.findByRole("region", { name: "Analytics preferences" });
    expect(region.parentElement).toHaveAttribute("data-surface", "inset");
  });

  it("downloads the active workspace JSON attachment", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mount();

    fireEvent.click(await screen.findByRole("button", { name: /download json export/i }));

    await waitFor(() => expect(mocks.downloadWorkspaceExport).toHaveBeenCalledTimes(1));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:workspace-export");
  });

  it("requires exact workspace name and password, then sends only a fresh token", async () => {
    mount();
    await openDialogPastWarning();

    const submit = screen.getByRole("button", { name: /delete permanently now/i });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), {
      target: { value: "Alice workspace" },
    });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "correct horse battery staple" },
    });
    fireEvent.click(submit);

    await waitFor(() => expect(mocks.reauthenticateWithPassword).toHaveBeenCalledWith(
      "alice@example.com",
      "correct horse battery staple"
    ));
    expect(mocks.deleteWorkspaceNow).toHaveBeenCalledWith({
      reauth_id_token: "fresh-id-token",
      confirmation: "Alice workspace",
      lang: "en",
    });
    expect(mocks.deleteWorkspaceNow.mock.calls[0][0]).not.toHaveProperty("password");
    await waitFor(() => expect(mocks.accountDeleted).toHaveBeenCalledTimes(1));
    expect(mocks.reloadAccount).not.toHaveBeenCalled();
  });

  it("traps focus, closes on Escape, and restores focus to the opener", async () => {
    mount();
    const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
    opener.focus();
    fireEvent.click(opener);

    const cancel = screen.getByRole("button", { name: /^cancel$/i });
    const close = screen.getByRole("button", { name: /close deletion dialog/i });
    expect(cancel).toHaveFocus();
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(/immediately and cannot be undone/i);

    // Tab from the last control wraps around to the first one.
    const proceed = screen.getByRole("button", { name: /continue in/i });
    expect(proceed).toBeDisabled();
    close.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(cancel).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("dims the whole screen: the overlay sits on document.body above the top bar", async () => {
    const { container } = mount();
    fireEvent.click(await screen.findByRole("button", { name: /^delete workspace$/i }));

    const overlay = screen.getByRole("dialog").parentElement;
    // A portal keeps a transformed ancestor (animate-fade-up) from turning
    // `fixed` into "fixed to that box", which left the top bar undimmed.
    expect(overlay.parentElement).toBe(document.body);
    expect(container.contains(overlay)).toBe(false);
    // Above the sticky top bar (z-30) and the bottom bar (z-40), like Modal.
    expect(overlay).toHaveClass("z-[60]");
  });

  it("states the consequences and keeps continue disabled for ten seconds", async () => {
    mount();
    const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      fireEvent.click(opener);
      expect(screen.getByText(/erased at once/i)).toBeInTheDocument();
      expect(screen.getByText(/cannot restore anything afterwards/i)).toBeInTheDocument();
      expect(screen.queryByLabelText(/type alice workspace/i)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /continue in 10 s/i })).toBeDisabled();
      for (let i = 0; i < 9; i += 1) act(() => { vi.advanceTimersByTime(1000); });
      expect(screen.getByRole("button", { name: /continue in 1 s/i })).toBeDisabled();
      act(() => { vi.advanceTimersByTime(1000); });
    } finally {
      vi.useRealTimers();
    }

    const ready = await screen.findByRole("button", { name: /i understand, continue/i });
    await waitFor(() => expect(ready).toBeEnabled());
    fireEvent.click(ready);
    expect(await screen.findByLabelText(/type alice workspace/i)).toBeInTheDocument();
    expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();
  });

  it("starts the countdown over when the dialog is reopened", async () => {
    mount();
    await openDialogPastWarning();
    fireEvent.click(screen.getByRole("button", { name: /close deletion dialog/i }));

    fireEvent.click(await screen.findByRole("button", { name: /^delete workspace$/i }));

    expect(screen.getByRole("button", { name: /continue in 10 s/i })).toBeDisabled();
  });

  it("re-reads the account instead of signing out when the user keeps another workspace", async () => {
    mocks.deleteWorkspaceNow.mockResolvedValueOnce({ deleted: true, account_deleted: false });
    mount();
    await openDialogPastWarning();
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), { target: { value: "Alice workspace" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: /delete permanently now/i }));

    await waitFor(() => expect(mocks.reloadAccount).toHaveBeenCalledTimes(1));
    expect(mocks.accountDeleted).not.toHaveBeenCalled();
  });

  it("shows a message and keeps the dialog open when the server could not delete", async () => {
    mocks.deleteWorkspaceNow.mockRejectedValueOnce({
      response: { status: 503, data: { code: "account_deletion_unavailable" } },
    });
    mount();
    await openDialogPastWarning();
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), { target: { value: "Alice workspace" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: /delete permanently now/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/nothing was deleted/i);
    expect(mocks.accountDeleted).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("offers no Google confirmation unless the build enables Google sign-in", async () => {
    mount();
    await openDialogPastWarning();

    expect(screen.queryByRole("button", { name: /confirm with google/i })).not.toBeInTheDocument();
    expect(mocks.prepareGoogleSignIn).not.toHaveBeenCalled();
  });

  it("schedules deletion with a fresh Google token and no password", async () => {
    mocks.isGoogleSignInEnabled.mockReturnValue(true);
    mount();
    await openDialogPastWarning();
    expect(mocks.prepareGoogleSignIn).toHaveBeenCalledTimes(1);

    const google = screen.getByRole("button", { name: /confirm with google/i });
    expect(google).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), {
      target: { value: "Alice workspace" },
    });
    expect(google).toBeEnabled();
    expect(screen.getByRole("button", { name: /delete permanently now/i })).toBeDisabled();
    fireEvent.click(google);

    await waitFor(() => expect(mocks.reauthenticateWithGoogle).toHaveBeenCalledWith("alice@example.com"));
    expect(mocks.reauthenticateWithPassword).not.toHaveBeenCalled();
    expect(mocks.deleteWorkspaceNow).toHaveBeenCalledWith({
      reauth_id_token: "fresh-google-token",
      confirmation: "Alice workspace",
      lang: "en",
    });
    await waitFor(() => expect(mocks.accountDeleted).toHaveBeenCalledTimes(1));
  });

  it("keeps the dialog open without an error when the Google popup is dismissed", async () => {
    mocks.isGoogleSignInEnabled.mockReturnValue(true);
    mocks.reauthenticateWithGoogle.mockResolvedValueOnce(null);
    mount();
    await openDialogPastWarning();
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), {
      target: { value: "Alice workspace" },
    });
    const google = screen.getByRole("button", { name: /confirm with google/i });
    fireEvent.click(google);

    await waitFor(() => expect(mocks.reauthenticateWithGoogle).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(google).toBeEnabled());
    expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("asks for a fresh confirmation when the backend finds the proof stale", async () => {
    mocks.isGoogleSignInEnabled.mockReturnValue(true);
    mocks.deleteWorkspaceNow.mockRejectedValueOnce({
      response: { status: 403, data: { code: "recent_reauthentication_required" } },
    });
    mount();
    await openDialogPastWarning();
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), {
      target: { value: "Alice workspace" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm with google/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Confirm your identity again and retry.");
  });

  it("shows a leftover pending deadline and allows cancellation", async () => {
    mocks.fetchDeletionStatus.mockResolvedValueOnce({
      scheduled: true,
      execute_after: "2026-10-07T12:00:00+00:00",
    });
    mount();

    expect(await screen.findByText(/scheduled for/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /cancel deletion/i }));

    await waitFor(() => expect(mocks.cancelWorkspaceDeletion).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: /delete workspace/i })).toBeInTheDocument();
  });

  describe("with a live paid subscription", () => {
    const subscription = {
      plan: "investor",
      status: "active",
      current_period_end: "2026-12-15T12:00:00+00:00",
      cancel_at_period_end: false,
    };

    // Opens the dialog and waits out the countdown, without pressing continue.
    async function openWarningAndWait() {
      const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      try {
        fireEvent.click(opener);
        for (let i = 0; i < 10; i += 1) act(() => { vi.advanceTimersByTime(1000); });
      } finally {
        vi.useRealTimers();
      }
    }

    async function confirmWithPassword() {
      await screen.findByText(/i agree that i am deleting this workspace/i);
      fireEvent.click(await screen.findByRole("button", { name: /^delete anyway$/i }));
      fireEvent.change(await screen.findByLabelText(/type alice workspace/i), { target: { value: "Alice workspace" } });
      fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "pw" } });
      fireEvent.click(screen.getByRole("button", { name: /delete permanently now/i }));
    }

    it("asks for consent, offers a way back and keeps the destructive button locked for ten seconds", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      try {
        fireEvent.click(opener);
        // Let React Query hand over the billing status (its notifier uses timers).
        await act(async () => { await vi.advanceTimersByTimeAsync(1); });
        expect(screen.getByText(/immediately lose the remaining paid features until the end of the billing period \(.*2026.*\)/i)).toBeInTheDocument();
        expect(screen.getByText(/the rest of the period is not refunded/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /back . let my subscription run/i })).toBeEnabled();
        expect(screen.queryByRole("button", { name: /^cancel$/i })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: /continue in \d+ s/i })).toBeDisabled();
        for (let i = 0; i < 9; i += 1) act(() => { vi.advanceTimersByTime(1000); });
        expect(screen.getByRole("button", { name: /continue in 1 s/i })).toBeDisabled();
        act(() => { vi.advanceTimersByTime(1000); });
      } finally {
        vi.useRealTimers();
      }
      expect(screen.getByRole("button", { name: /^delete anyway$/i })).toBeEnabled();
      expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();
    });

    it("the back button closes the dialog without deleting", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      await openWarningAndWait();
      fireEvent.click(await screen.findByRole("button", { name: /back . let my subscription run/i }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();
    });

    it("words the consent without a date when the period end is unknown (past due)", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription: { ...subscription, status: "past_due", current_period_end: null } });
      mount();
      await openWarningAndWait();
      expect(await screen.findByText(/until the end of the billing period\. My subscription is cancelled/i)).toBeInTheDocument();
    });

    it("sends cancel_subscription with the deletion request", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      await openWarningAndWait();
      await confirmWithPassword();

      await waitFor(() => expect(mocks.deleteWorkspaceNow).toHaveBeenCalledTimes(1));
      expect(mocks.deleteWorkspaceNow).toHaveBeenCalledWith({
        reauth_id_token: "fresh-id-token",
        confirmation: "Alice workspace",
        lang: "en",
        cancel_subscription: true,
      });
      // The no-refund consent was shown, so no refund is promised.
      expect(mocks.deleteWorkspaceNow.mock.calls[0][0]).not.toHaveProperty("refund_expected");
    });

    it("shows the message when Stripe could not cancel the subscription", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mocks.deleteWorkspaceNow.mockRejectedValueOnce({
        response: { status: 503, data: { code: "subscription_cancel_failed" } },
      });
      mount();
      await openWarningAndWait();
      await confirmWithPassword();

      expect(await screen.findByRole("alert")).toHaveTextContent(/could not cancel your subscription, so nothing was deleted/i);
      expect(mocks.accountDeleted).not.toHaveBeenCalled();
    });

    it("shows the consent and the cancel-first hint when the withdrawal window is closed", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({
        subscription: { ...subscription, ordered_at: "2026-10-01T12:00:00+00:00", withdrawal_ends_at: "2026-10-15T12:00:00+00:00", withdrawal_open: false },
      });
      mount();
      await openWarningAndWait();
      expect(await screen.findByText(/the rest of the period is not refunded/i)).toBeInTheDocument();
      expect(screen.getByText(/cancel the subscription first and delete the workspace after .*2026/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^manage subscription$/i })).toBeEnabled();
      expect(screen.queryByText(/less than 14 days ago/i)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^delete anyway$/i })).toBeEnabled();
    });

    it("words the hint without a date when the period end is unknown", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription: { ...subscription, status: "past_due", current_period_end: null } });
      mount();
      await openWarningAndWait();
      expect(await screen.findByText(/delete the workspace after it has ended/i)).toBeInTheDocument();
    });

    it("opens the billing portal from the manage subscription button", async () => {
      const assign = vi.fn();
      vi.stubGlobal("location", { ...window.location, assign });
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      await openWarningAndWait();
      fireEvent.click(await screen.findByRole("button", { name: /^manage subscription$/i }));
      await waitFor(() => expect(assign).toHaveBeenCalledWith("https://billing.stripe.test/p"));
      expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();
    });

    it("shows an error when the billing portal cannot be opened", async () => {
      mocks.openBillingPortal.mockRejectedValueOnce({ response: { status: 500 } });
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      await openWarningAndWait();
      fireEvent.click(await screen.findByRole("button", { name: /^manage subscription$/i }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/payment page could not be opened/i);
    });

    it("shows the message when the refund failed and keeps the dialog open", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mocks.deleteWorkspaceNow.mockRejectedValueOnce({
        response: { status: 503, data: { code: "subscription_refund_failed" } },
      });
      mount();
      await openWarningAndWait();
      await confirmWithPassword();

      expect(await screen.findByRole("alert")).toHaveTextContent(/could not refund your payment, so nothing was deleted and your subscription is unchanged/i);
      expect(mocks.accountDeleted).not.toHaveBeenCalled();
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
  });

  describe("within the 14-day withdrawal window", () => {
    const subscription = {
      plan: "investor",
      status: "active",
      current_period_end: "2026-12-15T12:00:00+00:00",
      cancel_at_period_end: false,
      ordered_at: "2026-11-20T12:00:00+00:00",
      withdrawal_ends_at: "2026-12-04T12:00:00+00:00",
      withdrawal_open: true,
    };

    async function openWarningAndWait() {
      const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      try {
        fireEvent.click(opener);
        for (let i = 0; i < 10; i += 1) act(() => { vi.advanceTimersByTime(1000); });
      } finally {
        vi.useRealTimers();
      }
    }

    it("explains the refund, hides the no-refund consent and locks the button for ten seconds", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      const opener = await screen.findByRole("button", { name: /^delete workspace$/i });
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      try {
        fireEvent.click(opener);
        await act(async () => { await vi.advanceTimersByTimeAsync(1); });
        expect(screen.getByText(/ordered this subscription less than 14 days ago.*refund the full amount you paid/i)).toBeInTheDocument();
        expect(screen.queryByText(/the rest of the period is not refunded/i)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /^manage subscription$/i })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: /back . let my subscription run/i })).toBeEnabled();
        expect(screen.getByRole("button", { name: /continue in \d+ s/i })).toBeDisabled();
        for (let i = 0; i < 9; i += 1) act(() => { vi.advanceTimersByTime(1000); });
        expect(screen.getByRole("button", { name: /continue in 1 s/i })).toBeDisabled();
        act(() => { vi.advanceTimersByTime(1000); });
      } finally {
        vi.useRealTimers();
      }
      expect(screen.getByRole("button", { name: /^delete and get a refund$/i })).toBeEnabled();
      expect(screen.queryByRole("button", { name: /^delete anyway$/i })).not.toBeInTheDocument();
      expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();
    });

    it("sends cancel_subscription with the deletion request", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      await openWarningAndWait();
      await screen.findByText(/less than 14 days ago/i);
      fireEvent.click(await screen.findByRole("button", { name: /^delete and get a refund$/i }));
      fireEvent.change(await screen.findByLabelText(/type alice workspace/i), { target: { value: "Alice workspace" } });
      fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "pw" } });
      fireEvent.click(screen.getByRole("button", { name: /delete permanently now/i }));

      await waitFor(() => expect(mocks.deleteWorkspaceNow).toHaveBeenCalledTimes(1));
      expect(mocks.deleteWorkspaceNow).toHaveBeenCalledWith({
        reauth_id_token: "fresh-id-token",
        confirmation: "Alice workspace",
        lang: "en",
        cancel_subscription: true,
        refund_expected: true,
      });
    });

    it("the back button closes the dialog without deleting", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription });
      mount();
      await openWarningAndWait();
      fireEvent.click(await screen.findByRole("button", { name: /back . let my subscription run/i }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();
    });

    it("treats a missing withdrawal_open as closed", async () => {
      const { withdrawal_open: _open, ...withoutFlag } = subscription;
      mocks.fetchBillingStatus.mockResolvedValue({ subscription: withoutFlag });
      mount();
      await openWarningAndWait();
      expect(await screen.findByText(/the rest of the period is not refunded/i)).toBeInTheDocument();
      expect(screen.queryByText(/less than 14 days ago/i)).not.toBeInTheDocument();
    });

    it("never treats a null withdrawal_open as open", async () => {
      mocks.fetchBillingStatus.mockResolvedValue({ subscription: { ...subscription, withdrawal_open: null } });
      mount();
      await openWarningAndWait();
      expect(await screen.findByText(/the rest of the period is not refunded/i)).toBeInTheDocument();
      expect(screen.queryByText(/less than 14 days ago/i)).not.toBeInTheDocument();
    });
  });

  describe("without a live subscription", () => {
    it.each([
      ["no subscription", { subscription: null }],
      ["a cancelled subscription", { subscription: { plan: "investor", status: "canceled", current_period_end: null } }],
    ])("keeps today's dialog and payload with %s", async (_label, status) => {
      mocks.fetchBillingStatus.mockResolvedValue(status);
      mount();
      await openDialogPastWarning();
      expect(screen.queryByText(/i agree that i am deleting this workspace/i)).not.toBeInTheDocument();
      fireEvent.change(screen.getByLabelText(/type alice workspace/i), { target: { value: "Alice workspace" } });
      fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "pw" } });
      fireEvent.click(screen.getByRole("button", { name: /delete permanently now/i }));

      await waitFor(() => expect(mocks.deleteWorkspaceNow).toHaveBeenCalledTimes(1));
      expect(mocks.deleteWorkspaceNow.mock.calls[0][0]).not.toHaveProperty("cancel_subscription");
      expect(mocks.deleteWorkspaceNow.mock.calls[0][0]).not.toHaveProperty("refund_expected");
    });

    it("shows the usual buttons and no consent when billing does not exist or fails", async () => {
      mocks.fetchBillingStatus.mockRejectedValue({ response: { status: 404 } });
      mount();
      fireEvent.click(await screen.findByRole("button", { name: /^delete workspace$/i }));
      await waitFor(() => expect(mocks.fetchBillingStatus).toHaveBeenCalledTimes(1));
      expect(await screen.findByRole("button", { name: /^cancel$/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /let my subscription run/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/i agree that i am deleting this workspace/i)).not.toBeInTheDocument();
    });

    it("treats a 404 from billing as no subscription and lets the person continue", async () => {
      mocks.fetchBillingStatus.mockRejectedValue({ response: { status: 404 } });
      mount();
      await openDialogPastWarning();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      fillAndSubmit();

      await waitFor(() => expect(mocks.deleteWorkspaceNow).toHaveBeenCalledTimes(1));
      expect(mocks.deleteWorkspaceNow.mock.calls[0][0]).not.toHaveProperty("cancel_subscription");
      expect(mocks.deleteWorkspaceNow.mock.calls[0][0]).not.toHaveProperty("refund_expected");
    });

    it("does not read billing until the dialog is opened", async () => {
      mount();
      await screen.findByRole("button", { name: /^delete workspace$/i });
      expect(mocks.fetchBillingStatus).not.toHaveBeenCalled();
    });
  });

  describe("while the subscription status is not known", () => {
    it("keeps continue disabled while billing is still loading", async () => {
      let resolveBilling;
      mocks.fetchBillingStatus.mockReturnValue(new Promise((resolve) => { resolveBilling = resolve; }));
      mount();
      await openWarningAndWait();

      expect(screen.getByText(/checking your subscription/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /i understand, continue/i })).toBeDisabled();

      await act(async () => { resolveBilling({ subscription: null }); });
      await waitFor(() => expect(screen.getByRole("button", { name: /i understand, continue/i })).toBeEnabled());
      expect(screen.queryByText(/checking your subscription/i)).not.toBeInTheDocument();
    });

    it("blocks on a billing error other than 404 and offers a retry", async () => {
      mocks.fetchBillingStatus.mockRejectedValueOnce({ response: { status: 500 } });
      mount();
      await openWarningAndWait();

      expect(await screen.findByRole("alert")).toHaveTextContent(/could not check your subscription/i);
      expect(screen.getByRole("button", { name: /i understand, continue/i })).toBeDisabled();
      expect(mocks.deleteWorkspaceNow).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: /^try again$/i }));
      await waitFor(() => expect(screen.getByRole("button", { name: /i understand, continue/i })).toBeEnabled());
      expect(mocks.fetchBillingStatus).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  describe("when the server refuses on subscription grounds", () => {
    it("explains active_subscription and asks to reopen the dialog", async () => {
      mocks.deleteWorkspaceNow.mockRejectedValueOnce({
        response: { status: 409, data: { code: "active_subscription" } },
      });
      mount();
      await openDialogPastWarning();
      fillAndSubmit();

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "You have a paid subscription. Reopen this dialog so that we can show you what happens to it, then try again."
      );
      expect(mocks.accountDeleted).not.toHaveBeenCalled();
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("returns to the warning with the no-refund consent when the withdrawal window closed meanwhile", async () => {
      const open = {
        plan: "investor",
        status: "active",
        current_period_end: "2026-12-15T12:00:00+00:00",
        cancel_at_period_end: false,
        withdrawal_open: true,
      };
      mocks.fetchBillingStatus
        .mockResolvedValueOnce({ subscription: open })
        .mockResolvedValue({ subscription: { ...open, withdrawal_open: false } });
      mocks.deleteWorkspaceNow.mockRejectedValueOnce({
        response: { status: 409, data: { code: "withdrawal_window_changed" } },
      });
      mount();
      await openWarningAndWait();
      await screen.findByText(/less than 14 days ago/i);
      fireEvent.click(await screen.findByRole("button", { name: /^delete and get a refund$/i }));
      await screen.findByLabelText(/type alice workspace/i);

      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      try {
        fillAndSubmit();
        await act(async () => { await vi.advanceTimersByTimeAsync(50); });

        // Refund was promised to the server, nothing was deleted.
        expect(mocks.deleteWorkspaceNow).toHaveBeenCalledTimes(1);
        expect(mocks.deleteWorkspaceNow.mock.calls[0][0]).toMatchObject({ refund_expected: true, cancel_subscription: true });
        expect(mocks.accountDeleted).not.toHaveBeenCalled();
        // The shared billing status was read again.
        expect(mocks.fetchBillingStatus).toHaveBeenCalledTimes(2);
        // Back on the warning step with the explanation and a fresh countdown.
        expect(screen.getByRole("alert")).toHaveTextContent(/withdrawal period ended while you were deleting, so no refund applies. Nothing was deleted/i);
        expect(screen.queryByLabelText(/type alice workspace/i)).not.toBeInTheDocument();
        expect(screen.getByText(/the rest of the period is not refunded/i)).toBeInTheDocument();
        expect(screen.queryByText(/less than 14 days ago/i)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: /continue in 10 s/i })).toBeDisabled();
        for (let i = 0; i < 9; i += 1) act(() => { vi.advanceTimersByTime(1000); });
        expect(screen.getByRole("button", { name: /continue in 1 s/i })).toBeDisabled();
        act(() => { vi.advanceTimersByTime(1000); });
      } finally {
        vi.useRealTimers();
      }

      // The person has to confirm the new terms; the retry no longer claims a refund.
      fireEvent.click(await screen.findByRole("button", { name: /^delete anyway$/i }));
      await screen.findByLabelText(/type alice workspace/i);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      fillAndSubmit();
      await waitFor(() => expect(mocks.deleteWorkspaceNow).toHaveBeenCalledTimes(2));
      expect(mocks.deleteWorkspaceNow.mock.calls[1][0]).toMatchObject({ cancel_subscription: true });
      expect(mocks.deleteWorkspaceNow.mock.calls[1][0]).not.toHaveProperty("refund_expected");
    });
  });

  describe("after a refunded deletion", () => {
    async function deleteWith(result) {
      mocks.deleteWorkspaceNow.mockResolvedValueOnce(result);
      mount();
      await openDialogPastWarning();
      fillAndSubmit();
    }

    it("shows the refund amount and only hands over to sign-out when Close is pressed", async () => {
      await deleteWith({ deleted: true, account_deleted: true, refunded: true, refunded_amount_cents: 599, currency: "eur" });

      expect(await screen.findByText(/we refunded .5\.99\. The money returns to your original payment method/i)).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /workspace deleted/i })).toBeInTheDocument();
      expect(screen.getByRole("dialog")).toHaveAccessibleDescription(/we refunded .5\.99/i);
      expect(mocks.accountDeleted).not.toHaveBeenCalled();
      expect(mocks.reloadAccount).not.toHaveBeenCalled();
      expect(screen.queryByLabelText(/type alice workspace/i)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /^close$/i }));
      expect(mocks.accountDeleted).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("also hands over when the confirmation is dismissed with Escape", async () => {
      await deleteWith({ deleted: true, account_deleted: true, refunded: true, refunded_amount_cents: 1299, currency: "EUR" });
      await screen.findByText(/we refunded .12\.99/i);
      fireEvent.keyDown(document, { key: "Escape" });
      expect(mocks.accountDeleted).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("re-reads the account on Close when the user keeps another workspace", async () => {
      await deleteWith({ deleted: true, account_deleted: false, refunded: true, refunded_amount_cents: 599, currency: "eur" });
      await screen.findByText(/we refunded/i);
      expect(mocks.reloadAccount).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: /^close$/i }));
      await waitFor(() => expect(mocks.reloadAccount).toHaveBeenCalledTimes(1));
      expect(mocks.accountDeleted).not.toHaveBeenCalled();
    });

    it("words the confirmation without an amount when the amount is missing", async () => {
      await deleteWith({ deleted: true, account_deleted: true, refunded: true, refunded_amount_cents: null, currency: "eur" });
      expect(await screen.findByText(/we refunded your payment\. The money returns to your original payment method/i)).toBeInTheDocument();
      expect(screen.queryByText(/\u20ac/)).not.toBeInTheDocument();
      expect(mocks.accountDeleted).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: /^close$/i }));
      expect(mocks.accountDeleted).toHaveBeenCalledTimes(1);
    });

    it("closes at once when nothing was refunded", async () => {
      await deleteWith({ deleted: true, account_deleted: true, refunded: false, refunded_amount_cents: null, currency: null });
      await waitFor(() => expect(mocks.accountDeleted).toHaveBeenCalledTimes(1));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.queryByText(/we refunded/i)).not.toBeInTheDocument();
    });
  });

  it("uses shared pill buttons and a destructive ghost for deleting the workspace", async () => {
    mount();
    expect(await screen.findByRole("button", { name: /download json export/i })).toHaveClass("btn-ghost");
    expect(await screen.findByRole("button", { name: /delete workspace/i })).toHaveClass("btn-ghost", "text-loss");
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new NativeURL("./DataPrivacySettings.jsx", import.meta.url))).toEqual([]);
  });
});
