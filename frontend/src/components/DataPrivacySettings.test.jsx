import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DataPrivacySettings from "./DataPrivacySettings";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";


const mocks = vi.hoisted(() => ({
  fetchDeletionStatus: vi.fn(),
  downloadWorkspaceExport: vi.fn(),
  scheduleWorkspaceDeletion: vi.fn(),
  cancelWorkspaceDeletion: vi.fn(),
  reauthenticateWithPassword: vi.fn(),
  reauthenticateWithGoogle: vi.fn(),
  prepareGoogleSignIn: vi.fn(),
  isGoogleSignInEnabled: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchDeletionStatus: mocks.fetchDeletionStatus,
  downloadWorkspaceExport: mocks.downloadWorkspaceExport,
  scheduleWorkspaceDeletion: mocks.scheduleWorkspaceDeletion,
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


describe("DataPrivacySettings", () => {
  beforeEach(() => {
    mocks.fetchDeletionStatus.mockReset().mockResolvedValue({
      scheduled: false,
      grace_days: 30,
    });
    mocks.downloadWorkspaceExport.mockReset().mockResolvedValue({
      blob: new Blob(["{}"], { type: "application/json" }),
      filename: "portfyl-workspace-export.json",
    });
    mocks.scheduleWorkspaceDeletion.mockReset().mockResolvedValue({
      scheduled: true,
      grace_days: 30,
      execute_after: "2026-10-07T12:00:00+00:00",
    });
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
    fireEvent.click(await screen.findByRole("button", { name: /delete workspace/i }));

    const submit = screen.getByRole("button", { name: /schedule deletion/i });
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
    expect(mocks.scheduleWorkspaceDeletion).toHaveBeenCalledWith({
      reauth_id_token: "fresh-id-token",
      confirmation: "Alice workspace",
    });
    expect(mocks.scheduleWorkspaceDeletion.mock.calls[0][0]).not.toHaveProperty("password");
    expect(await screen.findByText(/scheduled for/i)).toBeInTheDocument();
  });

  it("traps focus, closes on Escape, and restores focus to the opener", async () => {
    mount();
    const opener = await screen.findByRole("button", { name: /delete workspace/i });
    opener.focus();
    fireEvent.click(opener);

    const confirmation = screen.getByLabelText(/type alice workspace/i);
    const password = screen.getByLabelText(/^password$/i);
    const close = screen.getByRole("button", { name: /close deletion dialog/i });
    expect(confirmation).toHaveFocus();
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(/waits 30 days/i);

    password.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("offers no Google confirmation unless the build enables Google sign-in", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /delete workspace/i }));

    expect(screen.queryByRole("button", { name: /confirm with google/i })).not.toBeInTheDocument();
    expect(mocks.prepareGoogleSignIn).not.toHaveBeenCalled();
  });

  it("schedules deletion with a fresh Google token and no password", async () => {
    mocks.isGoogleSignInEnabled.mockReturnValue(true);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /delete workspace/i }));
    expect(mocks.prepareGoogleSignIn).toHaveBeenCalledTimes(1);

    const google = screen.getByRole("button", { name: /confirm with google/i });
    expect(google).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), {
      target: { value: "Alice workspace" },
    });
    expect(google).toBeEnabled();
    expect(screen.getByRole("button", { name: /schedule deletion/i })).toBeDisabled();
    fireEvent.click(google);

    await waitFor(() => expect(mocks.reauthenticateWithGoogle).toHaveBeenCalledWith("alice@example.com"));
    expect(mocks.reauthenticateWithPassword).not.toHaveBeenCalled();
    expect(mocks.scheduleWorkspaceDeletion).toHaveBeenCalledWith({
      reauth_id_token: "fresh-google-token",
      confirmation: "Alice workspace",
    });
    expect(await screen.findByText(/scheduled for/i)).toBeInTheDocument();
  });

  it("keeps the dialog open without an error when the Google popup is dismissed", async () => {
    mocks.isGoogleSignInEnabled.mockReturnValue(true);
    mocks.reauthenticateWithGoogle.mockResolvedValueOnce(null);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /delete workspace/i }));
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), {
      target: { value: "Alice workspace" },
    });
    const google = screen.getByRole("button", { name: /confirm with google/i });
    fireEvent.click(google);

    await waitFor(() => expect(mocks.reauthenticateWithGoogle).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(google).toBeEnabled());
    expect(mocks.scheduleWorkspaceDeletion).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("asks for a fresh confirmation when the backend finds the proof stale", async () => {
    mocks.isGoogleSignInEnabled.mockReturnValue(true);
    mocks.scheduleWorkspaceDeletion.mockRejectedValueOnce({
      response: { status: 403, data: { code: "recent_reauthentication_required" } },
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /delete workspace/i }));
    fireEvent.change(screen.getByLabelText(/type alice workspace/i), {
      target: { value: "Alice workspace" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm with google/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Confirm your identity again and retry.");
  });

  it("shows a pending deadline and allows cancellation", async () => {
    mocks.fetchDeletionStatus.mockResolvedValueOnce({
      scheduled: true,
      grace_days: 30,
      execute_after: "2026-10-07T12:00:00+00:00",
    });
    mount();

    expect(await screen.findByText(/scheduled for/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /cancel deletion/i }));

    await waitFor(() => expect(mocks.cancelWorkspaceDeletion).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: /delete workspace/i })).toBeInTheDocument();
  });
});
