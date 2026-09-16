import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DataPrivacySettings from "./DataPrivacySettings";


const mocks = vi.hoisted(() => ({
  fetchDeletionStatus: vi.fn(),
  downloadWorkspaceExport: vi.fn(),
  scheduleWorkspaceDeletion: vi.fn(),
  cancelWorkspaceDeletion: vi.fn(),
  reauthenticateWithPassword: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchDeletionStatus: mocks.fetchDeletionStatus,
  downloadWorkspaceExport: mocks.downloadWorkspaceExport,
  scheduleWorkspaceDeletion: mocks.scheduleWorkspaceDeletion,
  cancelWorkspaceDeletion: mocks.cancelWorkspaceDeletion,
}));

vi.mock("../auth/firebase", () => ({
  reauthenticateWithPassword: mocks.reauthenticateWithPassword,
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
      <DataPrivacySettings />
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
