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
  downloadWorkspaceExport: vi.fn(),
  deleteWorkspaceNow: vi.fn(),
  cancelWorkspaceDeletion: vi.fn(),
  reauthenticateWithPassword: vi.fn(),
  reauthenticateWithGoogle: vi.fn(),
  prepareGoogleSignIn: vi.fn(),
  isGoogleSignInEnabled: vi.fn(),
  accountDeleted: vi.fn(),
  reloadAccount: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchDeletionStatus: mocks.fetchDeletionStatus,
  downloadWorkspaceExport: mocks.downloadWorkspaceExport,
  deleteWorkspaceNow: mocks.deleteWorkspaceNow,
  cancelWorkspaceDeletion: mocks.cancelWorkspaceDeletion,
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
  fireEvent.click(screen.getByRole("button", { name: /i understand, continue/i }));
}


describe("DataPrivacySettings", () => {
  beforeEach(() => {
    mocks.fetchDeletionStatus.mockReset().mockResolvedValue({ scheduled: false });
    mocks.accountDeleted.mockReset();
    mocks.reloadAccount.mockReset().mockResolvedValue({});
    mocks.downloadWorkspaceExport.mockReset().mockResolvedValue({
      blob: new Blob(["{}"], { type: "application/json" }),
      filename: "portfyl-workspace-export.json",
    });
    mocks.deleteWorkspaceNow.mockReset().mockResolvedValue({ deleted: true, account_deleted: true });
    mocks.cancelWorkspaceDeletion.mockReset().mockResolvedValue(undefined);
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

    const ready = screen.getByRole("button", { name: /i understand, continue/i });
    expect(ready).toBeEnabled();
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

  it("uses shared pill buttons and a destructive ghost for deleting the workspace", async () => {
    mount();
    expect(await screen.findByRole("button", { name: /download json export/i })).toHaveClass("btn-ghost");
    expect(await screen.findByRole("button", { name: /delete workspace/i })).toHaveClass("btn-ghost", "text-loss");
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new NativeURL("./DataPrivacySettings.jsx", import.meta.url))).toEqual([]);
  });
});
