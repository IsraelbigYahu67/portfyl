import { api, createPendingImportPortfolio } from "./api";

describe("createPendingImportPortfolio", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the UI's own name for the new portfolio", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { id: "p1" } });

    await expect(createPendingImportPortfolio("Moje portfolio")).resolves.toEqual({ id: "p1" });

    expect(post).toHaveBeenCalledWith("/portfolios/pending-import", { name: "Moje portfolio" });
  });

  it("sends no body without a name, so the server keeps its default", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { id: "p1" } });

    await createPendingImportPortfolio();

    expect(post).toHaveBeenCalledWith("/portfolios/pending-import", undefined);
  });
});
