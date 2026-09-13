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
});
