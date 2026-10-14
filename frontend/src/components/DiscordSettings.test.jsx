import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  fetchDiscordWebhook: vi.fn(),
  createDiscordWebhook: vi.fn(),
  updateDiscordWebhook: vi.fn(),
  deleteDiscordWebhook: vi.fn(),
  testDiscordWebhook: vi.fn(),
}));

vi.mock("../api", () => mocks);

import DiscordSettings from "./DiscordSettings";

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DiscordSettings />
    </QueryClientProvider>,
  );
}

const connected = (extra = {}) => ({
  connected: true,
  id: "hook-1",
  webhook_url_preview: "https://discord.com/api/webhooks/***/***",
  valid: true,
  notify_trades: true,
  notify_dividends: true,
  notify_milestones: true,
  created_at: null,
  ...extra,
});

beforeEach(() => {
  Object.values(mocks).forEach((fn) => fn.mockReset());
});

describe("DiscordSettings", () => {
  it("shows the backend validation message when connecting fails", async () => {
    mocks.fetchDiscordWebhook.mockResolvedValue({ connected: false });
    mocks.createDiscordWebhook.mockRejectedValue({
      response: { data: { detail: "Discord webhook URL must use https" } },
    });
    mount();

    fireEvent.change(await screen.findByPlaceholderText(/discord\.com\/api\/webhooks/), {
      target: { value: "http://10.0.0.5/x" },
    });
    fireEvent.click(screen.getByRole("button", { name: /connect/i }));

    expect(await screen.findByText("Discord webhook URL must use https")).toBeInTheDocument();
  });

  it("does not warn about a valid saved webhook", async () => {
    mocks.fetchDiscordWebhook.mockResolvedValue(connected());
    mount();

    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send test/i })).toBeEnabled();
  });

  it("asks for a new URL when the saved webhook is not valid", async () => {
    mocks.fetchDiscordWebhook.mockResolvedValue(connected({ valid: false }));
    mocks.createDiscordWebhook.mockResolvedValue({ status: "ok" });
    mount();

    expect(await screen.findByRole("alert")).toHaveTextContent(/not a valid Discord webhook URL/i);
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send test/i })).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText(/discord\.com\/api\/webhooks/), {
      target: { value: "https://discord.com/api/webhooks/1/token" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() =>
      expect(mocks.createDiscordWebhook).toHaveBeenCalledWith({
        webhook_url: "https://discord.com/api/webhooks/1/token",
      }),
    );
  });
});
