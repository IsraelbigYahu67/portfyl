import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import Import from "./Import";
import { legacyColorClassesIn } from "../test/legacyClasses";


const mocks = vi.hoisted(() => ({
  previewImportCSV: vi.fn(),
  commitImportCSV: vi.fn(),
  fetchImportUndo: vi.fn(),
  undoLastImport: vi.fn(),
  clearAllTransactions: vi.fn(),
  confirm: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  refetchPortfolios: vi.fn(),
  setCurrentId: vi.fn(),
  recordPortfolioDataImported: vi.fn(() => true),
  createPortfolio: vi.fn(),
  deletePortfolio: vi.fn(),
}));

vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({
    recordPortfolioDataImported: mocks.recordPortfolioDataImported,
  }),
}));

vi.mock("../api", () => ({
  previewImportCSV: mocks.previewImportCSV,
  commitImportCSV: mocks.commitImportCSV,
  fetchImportUndo: mocks.fetchImportUndo,
  undoLastImport: mocks.undoLastImport,
  clearAllTransactions: mocks.clearAllTransactions,
  createPortfolio: mocks.createPortfolio,
  deletePortfolio: mocks.deletePortfolio,
}));

vi.mock("../components/ui/ConfirmDialog", () => ({
  useConfirm: () => mocks.confirm,
}));

vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.success, error: mocks.error }),
}));
vi.mock("../App", () => ({
  usePortfolio: () => ({
    current: { id: "portfolio-id", activation_state: "active" },
    pendingImportPortfolio: null,
    refetchPortfolios: mocks.refetchPortfolios,
    setCurrentId: mocks.setCurrentId,
  }),
}));


function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}</output>;
}

function mount(props = {}, entry = "/import") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}><Import {...props} /><LocationProbe /></MemoryRouter>
    </QueryClientProvider>
  );
}


function chooseCsv(container) {
  const file = new File([
    "date,ticker,type,shares,price,currency\n2026-01-02,AAPL,buy,1,100,USD\n",
  ], "portfolio.csv", { type: "text/csv" });
  fireEvent.change(container.querySelector('input[type="file"]'), {
    target: { files: [file] },
  });
  return file;
}


describe("Import preview and undo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchImportUndo.mockResolvedValue({ available: false, reason: null });
    mocks.previewImportCSV.mockResolvedValue({
      preview_id: "preview-1",
      format: "Native",
      mode: "append",
      mandatory_replace: false,
      counts: {
        source_events: 3,
        recognized_rows: 3,
        unique_rows: 2,
        duplicates_in_file: 1,
        duplicates_existing: 1,
        current: 5,
        added: 1,
        removed: 0,
        unchanged: 5,
        projected: 6,
        skipped: 0,
      },
      sample: [{ date: "2026-01-02", ticker: "AAPL", type: "buy", shares: 1, price: 100, currency: "USD" }],
      sample_truncated: false,
    });
    mocks.commitImportCSV.mockResolvedValue({
      imported: 1,
      duplicates_skipped: 2,
      projected: 6,
      mode: "append",
      format: "Native",
      undo: { available: true, expires_at: "2026-09-08T12:00:00+00:00", imported: 1, mode: "append" },
    });
    mocks.undoLastImport.mockResolvedValue({ restored: 5, undone: true });
    mocks.refetchPortfolios.mockResolvedValue({ data: [{ id: "portfolio-id", activation_state: "active" }] });
    mocks.confirm.mockResolvedValue(true);
  });

  it("does not offer commit until the selected file has been previewed", async () => {
    const { container } = mount();
    const file = chooseCsv(container);

    expect(screen.queryByRole("button", { name: /^import 1 transaction$/i })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));

    await waitFor(() => expect(mocks.previewImportCSV).toHaveBeenCalledWith(file, false));
    expect(await screen.findByText(/1 transaction will be added/i)).toBeInTheDocument();
    expect(screen.getByText(/2 exact duplicates will be skipped/i)).toBeInTheDocument();
    expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /continue to confirm/i }));
    fireEvent.click(screen.getByRole("button", { name: /^import 1 transaction$/i }));
    await waitFor(() => expect(mocks.commitImportCSV).toHaveBeenCalledWith(file, "preview-1", false));
    expect(await screen.findByRole("link", { name: /manage portfolio data/i })).toHaveAttribute("href", "/settings?section=data");
    expect(mocks.recordPortfolioDataImported).toHaveBeenCalledWith("csv");
    expect(mocks.recordPortfolioDataImported).toHaveBeenCalledTimes(1);
  });

  it("does not expose destructive portfolio clearing", async () => {
    mount();
    expect(await screen.findByRole("heading", { name: "Import transactions" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /clear portfolio/i })).not.toBeInTheDocument();
    expect(mocks.clearAllTransactions).not.toHaveBeenCalled();
  });

  it("leaves a focused onboarding import without activating it", async () => {
    mount({ focused: true });
    fireEvent.click(screen.getByRole("button", { name: /leave import/i }));
    expect(screen.getByLabelText("location")).toHaveTextContent("/onboarding");
    expect(mocks.commitImportCSV).not.toHaveBeenCalled();
  });

  it("tailors the copy to the broker picked during onboarding and returns to it", async () => {
    mount({ focused: true }, "/import?broker=xtb");

    expect(await screen.findByRole("heading", { level: 1, name: "Import your XTB file" })).toBeInTheDocument();
    expect(screen.getByText(/drop your xtb xlsx file here/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^XTB/ })).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: /leave import/i }));
    expect(screen.getByLabelText("location")).toHaveTextContent("/onboarding");
  });

  it("shows replacement removals before destructive commit", async () => {
    mocks.previewImportCSV.mockResolvedValueOnce({
      preview_id: "replace-1",
      format: "Trading 212",
      mode: "replace",
      mandatory_replace: true,
      counts: {
        source_events: 10, recognized_rows: 10, unique_rows: 10,
        duplicates_in_file: 0, duplicates_existing: 4,
        current: 8, added: 6, removed: 4, unchanged: 4, projected: 10, skipped: 0,
      },
      sample: [],
      sample_truncated: false,
    });
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));

    expect(await screen.findByText(/4 current transactions will be removed/i)).toBeInTheDocument();
    expect(screen.getByText(/Trading 212 exports replace the full portfolio/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /continue to confirm/i }));
    expect(screen.getByRole("button", { name: /replace portfolio with 10 transactions/i })).toBeInTheDocument();
  });

  it("lists IBKR skipped reasons without the Trading 212 replace warning", async () => {
    mocks.previewImportCSV.mockResolvedValueOnce({
      preview_id: "ibkr-1",
      format: "Interactive Brokers (Flex XML)",
      mode: "append",
      mandatory_replace: false,
      counts: {
        source_events: 9, recognized_rows: 5, unique_rows: 5,
        duplicates_in_file: 0, duplicates_existing: 0,
        current: 0, added: 5, removed: 0, unchanged: 0, projected: 5, skipped: 4,
      },
      sample: [],
      sample_truncated: false,
      skipped_reasons: { "options trade (synced from Settings)": 3, "FX conversion": 1 },
    });
    const { container } = mount();
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [new File(["<FlexQueryResponse/>"], "ibkr_2024.xml", { type: "text/xml" })] },
    });
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));

    const skipped = await screen.findByRole("list", { name: "Skipped rows" });
    expect(skipped).toHaveTextContent("options trade (synced from Settings) × 3");
    expect(skipped).toHaveTextContent("FX conversion × 1");
    expect(screen.getByText(/4 rows recognized and skipped/i)).toBeInTheDocument();
    expect(screen.queryByText(/informational row/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/replace the full portfolio/i)).not.toBeInTheDocument();
  });

  it("falls back to the skipped count when the preview has no reasons", async () => {
    mocks.previewImportCSV.mockResolvedValueOnce({
      preview_id: "native-skip",
      format: "Native",
      mode: "append",
      mandatory_replace: false,
      counts: {
        source_events: 3, recognized_rows: 1, unique_rows: 1,
        duplicates_in_file: 0, duplicates_existing: 0,
        current: 0, added: 1, removed: 0, unchanged: 0, projected: 1, skipped: 2,
      },
      sample: [],
      sample_truncated: false,
    });
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));
    expect(await screen.findByText(/2 informational rows recognized and skipped/i)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Skipped rows" })).not.toBeInTheDocument();
  });

  it("does not blame Trading 212 for a requested native replace", async () => {
    mocks.previewImportCSV.mockResolvedValueOnce({
      preview_id: "native-replace",
      format: "Native",
      mode: "replace",
      mandatory_replace: false,
      counts: {
        source_events: 1, recognized_rows: 1, unique_rows: 1,
        duplicates_in_file: 0, duplicates_existing: 0,
        current: 3, added: 1, removed: 3, unchanged: 0, projected: 1, skipped: 0,
      },
      sample: [],
      sample_truncated: false,
      skipped_reasons: {},
    });
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("checkbox", { name: /replace existing portfolio/i }));
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));
    expect(await screen.findByText("This import replaces the full portfolio.")).toBeInTheDocument();
    expect(screen.queryByText(/Trading 212 exports replace/i)).not.toBeInTheDocument();
  });

  it("explains that IBKR Flex XML is accepted, one file per year", () => {
    const { container } = mount();
    expect(screen.getByText("Interactive Brokers (Flex XML)")).toBeInTheDocument();
    expect(screen.getByText(/Activity Flex XML statements \(\.xml\)/i)).toHaveTextContent(/upload one XML\s+per year/i);
    expect(screen.getByRole("link", { name: /settings → connections/i })).toHaveAttribute("href", "/settings?section=connections");
    expect(container.querySelector('input[type="file"]').getAttribute("accept")).toContain(".xml");
  });

  it("previews a Degiro export as an append with its skipped reasons", async () => {
    mocks.previewImportCSV.mockResolvedValueOnce({
      preview_id: "degiro-1",
      format: "Degiro (Transactions)",
      mode: "append",
      mandatory_replace: false,
      counts: {
        source_events: 7, recognized_rows: 4, unique_rows: 4,
        duplicates_in_file: 0, duplicates_existing: 0,
        current: 2, added: 4, removed: 0, unchanged: 2, projected: 6, skipped: 3,
      },
      sample: [],
      sample_truncated: false,
      skipped_reasons: { "trade settlement (imported from Transactions.csv)": 3 },
    });
    const { container } = mount();
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [new File(["Datum,Tijd"], "Transactions.csv", { type: "text/csv" })] },
    });
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));

    const skipped = await screen.findByRole("list", { name: "Skipped rows" });
    expect(skipped).toHaveTextContent("trade settlement (imported from Transactions.csv) × 3");
    expect(screen.getAllByText("Degiro (Transactions)").length).toBeGreaterThan(0);
    expect(screen.queryByText(/replaces the full portfolio/i)).not.toBeInTheDocument();
  });

  it("accepts XTB spreadsheets and shows the broker export guides until a file is picked", async () => {
    const { container } = mount();
    expect(container.querySelector('input[type="file"]').getAttribute("accept")).toContain(".xlsx");
    for (const name of ["Degiro", "XTB", "Charles Schwab", "Fidelity"]) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("heading", { name: "How to export from your broker" })).toBeInTheDocument();
    chooseCsv(container);
    await waitFor(() => expect(screen.queryByRole("heading", { name: "How to export from your broker" })).not.toBeInTheDocument());
  });

  describe("one broker per portfolio", () => {
    const XTB_PREVIEW = {
      preview_id: "xtb-1",
      format: "XTB (xStation)",
      broker: "xtb",
      mode: "append",
      mandatory_replace: false,
      counts: {
        source_events: 3, recognized_rows: 3, unique_rows: 3,
        duplicates_in_file: 0, duplicates_existing: 0,
        current: 0, added: 3, removed: 0, unchanged: 0, projected: 3, skipped: 0,
      },
      sample: [],
      sample_truncated: false,
      skipped_reasons: {},
    };

    function portfolios(brokers) {
      mocks.refetchPortfolios.mockResolvedValue({ data: [{ id: "portfolio-id", name: "Main", brokers }] });
    }

    async function previewXtb() {
      const { container } = mount();
      fireEvent.change(container.querySelector('input[type="file"]'), {
        target: { files: [new File(["PK"], "xtb.xlsx")] },
      });
      fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));
    }

    it("opens a new portfolio when the selected one holds another broker", async () => {
      portfolios(["trading212"]);
      mocks.previewImportCSV.mockResolvedValue(XTB_PREVIEW);
      mocks.createPortfolio.mockResolvedValue({ id: "new-id", name: "XTB" });
      await previewXtb();

      const notice = await screen.findByRole("status", { name: "New portfolio" });
      expect(notice).toHaveTextContent("“Main” already holds Trading 212 data, so XTB goes into its own portfolio “XTB”.");
      expect(mocks.createPortfolio).toHaveBeenCalledWith({ name: "XTB" });
      expect(mocks.setCurrentId).toHaveBeenCalledWith("new-id");
      expect(mocks.previewImportCSV).toHaveBeenCalledTimes(2);
      expect(mocks.previewImportCSV.mock.calls[1][1]).toBe(false);
      // Re-renders must not clean the new portfolio up again.
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(mocks.deletePortfolio).not.toHaveBeenCalled();
    });

    it("removes the new portfolio again when the preview is cancelled", async () => {
      portfolios(["trading212"]);
      mocks.previewImportCSV.mockResolvedValue(XTB_PREVIEW);
      mocks.createPortfolio.mockResolvedValue({ id: "new-id", name: "XTB" });
      mocks.deletePortfolio.mockResolvedValue({ deleted: "new-id" });
      await previewXtb();

      fireEvent.click(await screen.findByRole("button", { name: /cancel preview/i }));
      await waitFor(() => expect(mocks.deletePortfolio).toHaveBeenCalledWith("new-id"));
      expect(mocks.setCurrentId).toHaveBeenLastCalledWith("portfolio-id");
    });

    it("can import into the original portfolio instead", async () => {
      portfolios(["trading212"]);
      mocks.previewImportCSV.mockResolvedValue(XTB_PREVIEW);
      mocks.createPortfolio.mockResolvedValue({ id: "new-id", name: "XTB" });
      mocks.deletePortfolio.mockResolvedValue({ deleted: "new-id" });
      await previewXtb();

      fireEvent.click(await screen.findByRole("button", { name: /import into “main” instead/i }));
      await waitFor(() => expect(mocks.previewImportCSV).toHaveBeenCalledTimes(3));
      expect(mocks.deletePortfolio).toHaveBeenCalledWith("new-id");
      expect(mocks.createPortfolio).toHaveBeenCalledTimes(1);
      await screen.findByRole("button", { name: /continue to confirm/i });
      expect(screen.queryByRole("status", { name: "New portfolio" })).not.toBeInTheDocument();
    });

    it("explains when the plan allows no further portfolio", async () => {
      portfolios(["trading212"]);
      mocks.previewImportCSV.mockResolvedValue(XTB_PREVIEW);
      mocks.createPortfolio.mockRejectedValue({ response: { data: { detail: "Portfolio limit reached" } } });
      await previewXtb();

      expect(await screen.findByRole("status", { name: "New portfolio not available" })).toHaveTextContent("This import goes into “Main”");
      expect(mocks.previewImportCSV).toHaveBeenCalledTimes(1);
    });

    it("keeps an empty portfolio or the same broker's portfolio", async () => {
      portfolios(["xtb"]);
      mocks.previewImportCSV.mockResolvedValue(XTB_PREVIEW);
      await previewXtb();

      await screen.findByRole("button", { name: /continue to confirm/i });
      expect(mocks.createPortfolio).not.toHaveBeenCalled();
    });
  });

  it("shows the four import stages in order", () => {
    mount();
    const steps = screen.getByRole("list", { name: "Import progress" });
    expect(Array.from(steps.children).map((item) => item.textContent)).toEqual([
      "1.Select source",
      "2.Preview changes",
      "3.Confirm import",
      "4.Result / Undo",
    ]);
  });

  it("invalidates a preview when import mode changes", async () => {
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));
    await screen.findByText(/1 transaction will be added/i);
    fireEvent.click(screen.getByRole("button", { name: /cancel preview/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /replace existing portfolio/i }));
    expect(screen.queryByText(/1 transaction will be added/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview import/i })).toBeInTheDocument();
    expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
  });

  it("recovers from commit drift by requiring a fresh preview", async () => {
    mocks.commitImportCSV.mockRejectedValueOnce({ response: { status: 409, data: { detail: "stale" } } });
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));
    await screen.findByText(/1 transaction will be added/i);
    fireEvent.click(screen.getByRole("button", { name: /continue to confirm/i }));
    fireEvent.click(screen.getByRole("button", { name: /^import 1 transaction$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The portfolio changed. Preview the file again.");
    expect(screen.getByRole("button", { name: /preview import/i })).toBeInTheDocument();
    expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
  });

  it("offers the persisted undo point and refreshes it after use", async () => {
    mocks.fetchImportUndo.mockResolvedValueOnce({
      available: true,
      mode: "replace",
      imported: 10,
      expires_at: "2026-09-08T12:00:00+00:00",
    });
    mount();

    fireEvent.click(await screen.findByRole("button", { name: /undo last import/i }));

    await waitFor(() => expect(mocks.undoLastImport).toHaveBeenCalledTimes(1));
    expect(mocks.success).toHaveBeenCalledWith("Last import undone");
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./Import.jsx", import.meta.url))).toEqual([]);
  });

  it("the stepper marks the current step", () => {
    mount();
    const steps = screen.getByRole("list", { name: "Import progress" });
    const current = steps.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Select source");
  });
});
