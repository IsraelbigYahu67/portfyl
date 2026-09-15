import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Screener from "./Screener";
import * as localApi from "../editions/localApi";

vi.mock("../components/StockDetail", () => ({
  useStockDetail: () => ({ openStock: vi.fn() }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Screener />
    </QueryClientProvider>
  );
}

describe("Screener page (job-based)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("creates a job on Run Scan and shows queued/running progress, then results via Pagination", async () => {
    vi.spyOn(localApi, "createScreenerJob").mockResolvedValue({
      job_id: "jx", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null,
    });
    vi.spyOn(localApi, "fetchScreenerJob").mockResolvedValue({
      job_id: "jx", status: "completed",
      progress: { completed: 3, total: 3, percent: 100 },
      result: { items: [{ ticker: "AAA", name: "Aaa Inc", price: 10, market_cap: 1e9 }], total: 1, offset: 0, limit: 50 },
      error: null,
    });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /run scan/i }));

    await waitFor(() => expect(screen.getByText("AAA")).toBeInTheDocument(), { timeout: 3000 });
    expect(localApi.createScreenerJob).toHaveBeenCalled();
  });

  it("shows the cancelled state and retries the last filter set", async () => {
    vi.spyOn(localApi, "createScreenerJob").mockResolvedValue({
      job_id: "jy", status: "running", progress: { completed: 1, total: 10, percent: 10 }, result: null, error: null,
    });
    vi.spyOn(localApi, "fetchScreenerJob").mockResolvedValue({
      job_id: "jy", status: "running", progress: { completed: 1, total: 10, percent: 10 }, result: null, error: null,
    });
    vi.spyOn(localApi, "cancelScreenerJob").mockResolvedValue({ job_id: "jy", status: "cancelled" });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /run scan/i }));

    const cancelButton = await screen.findByRole("button", { name: /cancel/i });
    fireEvent.click(cancelButton);
    await waitFor(() => expect(localApi.cancelScreenerJob).toHaveBeenCalledWith("jy"));
    expect(await screen.findByText(/scan cancelled\. retry/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(localApi.createScreenerJob).toHaveBeenCalledTimes(2));
  });

  it("requests the selected result-page size", async () => {
    vi.spyOn(localApi, "createScreenerJob").mockResolvedValue({
      job_id: "jp", status: "queued", progress: { completed: 0, total: 60, percent: 0 }, result: null, error: null,
    });
    vi.spyOn(localApi, "fetchScreenerJob").mockImplementation((_jobId, page) => Promise.resolve({
      job_id: "jp", status: "completed",
      progress: { completed: 60, total: 60, percent: 100 },
      result: { items: [{ ticker: "AAA", name: "Aaa Inc", price: 10, market_cap: 1e9 }], total: 60, ...page },
      error: null,
    }));

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /run scan/i }));
    await screen.findByText("AAA", {}, { timeout: 3000 });

    fireEvent.change(screen.getByLabelText(/rows per page/i), { target: { value: "25" } });
    await waitFor(() => expect(localApi.fetchScreenerJob).toHaveBeenLastCalledWith("jp", { offset: 0, limit: 25 }));
  });
});
