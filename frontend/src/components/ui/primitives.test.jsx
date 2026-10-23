import { readFile } from "node:fs/promises";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { Calendar } from "lucide-react";
import { Card, SectionHeader, Skeleton, EmptyState, DeltaPill, Badge, Modal } from "./index";
import Toggle from "./Toggle";
import { legacyColorClassesIn } from "../../test/legacyClasses";
import { sourcePath } from "../../test/sourcePath";

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

describe("Badge and Modal", () => {
  it("Badge renders its tone", () => {
    render(<Badge tone="warn">Stale</Badge>);
    expect(screen.getByText("Stale")).toHaveAttribute("data-tone", "warn");
  });

  it("Modal closes on Escape and restores focus", () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open</button>
          <Modal open={open} onClose={() => setOpen(false)} titleId="t">
            <h2 id="t">Add</h2>
            <input aria-label="Name" />
          </Modal>
        </>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Add" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("Modal closes on a backdrop click but not a click inside the panel", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} titleId="t2">
        <h2 id="t2">Panel</h2>
      </Modal>,
    );
    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(screen.getByRole("dialog").parentElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Modal renders nothing while closed", () => {
    render(<Modal open={false} onClose={() => {}} titleId="t3"><h2 id="t3">x</h2></Modal>);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Badge uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./Badge.jsx", import.meta.url))).toEqual([]);
  });

  it("Toggle uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./Toggle.jsx", import.meta.url))).toEqual([]);
  });

  it("Toggle keeps its switch semantics and flips on click", () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} aria-label="Sync" />);
    const toggle = screen.getByRole("switch", { name: "Sync" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe("index.css semantic financial typography classes", () => {
  it("defines the five semantic classes with their documented floor font-sizes", async () => {
    const assetUrl = new URL("../../index.css", import.meta.url);
    const cssPath = sourcePath(assetUrl);
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
