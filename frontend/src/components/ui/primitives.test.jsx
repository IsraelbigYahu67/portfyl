import { readFile } from "node:fs/promises";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { Calendar } from "lucide-react";
import { Card, SectionHeader, Skeleton, EmptyState, DeltaPill } from "./index";

describe("ui primitives", () => {
  it("Card renders children", () => {
    render(<Card>hello</Card>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
  it("SectionHeader renders its label", () => {
    render(<SectionHeader icon={Calendar}>Earnings Calendar</SectionHeader>);
    expect(screen.getByText("Earnings Calendar")).toBeInTheDocument();
  });
  it("SectionHeader label uses the data-label semantic class", () => {
    render(<SectionHeader icon={Calendar}>Earnings Calendar</SectionHeader>);
    expect(screen.getByText("Earnings Calendar")).toHaveClass("data-label");
  });
  it("SectionHeader stacks and wraps wide actions on small screens", () => {
    const { container } = render(
      <SectionHeader action={<button type="button">Wide filters</button>}>Performance</SectionHeader>,
    );
    const root = container.firstElementChild;
    const action = screen.getByRole("button", { name: "Wide filters" }).parentElement;
    expect(root).toHaveClass("flex-col", "sm:flex-row");
    expect(action).toHaveClass("flex-wrap", "min-w-0");
  });
  it("Skeleton renders a shimmer element", () => {
    const { container } = render(<Skeleton w="4rem" h="1rem" />);
    expect(container.querySelector(".shimmer")).toBeTruthy();
  });
  it("EmptyState shows title and hint", () => {
    render(<EmptyState icon={Calendar} title="No holdings yet" hint="Import to begin." />);
    expect(screen.getByText("No holdings yet")).toBeInTheDocument();
    expect(screen.getByText("Import to begin.")).toBeInTheDocument();
  });
  it("DeltaPill shows a formatted gain", () => {
    render(<DeltaPill value={58000} pct={2.41} currency="USD" />);
    expect(screen.getByText(/\$58,000\.00/)).toBeInTheDocument();
    expect(screen.getByText(/2\.41%/)).toBeInTheDocument();
  });
  it("DeltaPill renders nothing when empty", () => {
    const { container } = render(<DeltaPill value={null} pct={null} />);
    expect(container.firstChild).toBeNull();
  });
  it("DeltaPill's smallest size still renders at least 12px text via the financial-meta class", () => {
    const { container } = render(<DeltaPill value={58000} pct={2.41} currency="USD" size="sm" />);
    expect(container.firstChild).toHaveClass("financial-meta");
  });
  it("DeltaPill includes an explicit sign on the amount, not only color", () => {
    render(<DeltaPill value={-500} pct={-1.2} currency="USD" />);
    expect(screen.getByText(/−\$500\.00/)).toBeInTheDocument();
  });
});

describe("index.css semantic financial typography classes", () => {
  it("defines the five semantic classes with their documented floor font-sizes", async () => {
    // Vite statically rewrites `new URL(relative, import.meta.url)`: for a
    // path inside the project root it yields a root-relative pathname
    // ("/src/index.css") rather than a file:// URL, so resolve it against
    // the Vitest process cwd (the frontend/ project root) instead of using
    // fileURLToPath, which requires an actual file: scheme.
    const assetUrl = new URL("../../index.css", import.meta.url);
    const cssPath = path.resolve(decodeURIComponent(assetUrl.pathname).replace(/^\//, ""));
    const css = await readFile(cssPath, "utf-8");
    const floors = {
      "financial-headline": "1rem",
      "financial-data": "0.875rem",
      "financial-meta": "0.75rem",
      "data-label": "0.75rem",
      "chart-label": "0.75rem",
    };
    for (const [className, size] of Object.entries(floors)) {
      const rule = new RegExp(`\\.${className}\\s*\\{[^}]*font-size:\\s*${size.replace(".", "\\.")}`);
      expect(css, `.${className} should declare font-size: ${size}`).toMatch(rule);
    }
  });
});
