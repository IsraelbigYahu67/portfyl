import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import Pagination from "./Pagination";

describe("Pagination", () => {
  it("renders the item range and total", () => {
    render(<Pagination offset={0} limit={50} total={130} onOffsetChange={() => {}} ariaLabel="Test pages" />);
    expect(screen.getByText(/1[–-]50 of 130/)).toBeInTheDocument();
  });

  it("disables Previous on the first page and Next on the last page", () => {
    const { rerender } = render(
      <Pagination offset={0} limit={50} total={130} onOffsetChange={() => {}} ariaLabel="Test pages" />
    );
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next/i })).not.toBeDisabled();

    rerender(<Pagination offset={100} limit={50} total={130} onOffsetChange={() => {}} ariaLabel="Test pages" />);
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
  });

  it("calls onOffsetChange with the next page's offset", () => {
    const onOffsetChange = vi.fn();
    render(<Pagination offset={0} limit={50} total={130} onOffsetChange={onOffsetChange} ariaLabel="Test pages" />);
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(onOffsetChange).toHaveBeenCalledWith(50);
  });

  it("renders numbered pages when there are at most seven", () => {
    render(<Pagination offset={0} limit={50} total={300} onOffsetChange={() => {}} ariaLabel="Test pages" />);
    // 300 / 50 = 6 pages -> numbered buttons render
    expect(screen.getByRole("button", { name: "3" })).toBeInTheDocument();
  });

  it("omits numbered pages when there are more than seven", () => {
    render(<Pagination offset={0} limit={25} total={1000} onOffsetChange={() => {}} ariaLabel="Test pages" />);
    // 1000 / 25 = 40 pages -> no numbered buttons
    expect(screen.queryByRole("button", { name: "3" })).not.toBeInTheDocument();
  });

  it("renders an accessible page-size selector only when onLimitChange is provided", () => {
    const { rerender } = render(
      <Pagination offset={0} limit={50} total={130} onOffsetChange={() => {}} ariaLabel="Test pages" />
    );
    expect(screen.queryByLabelText(/rows per page/i)).not.toBeInTheDocument();

    const onLimitChange = vi.fn();
    rerender(
      <Pagination
        offset={0}
        limit={50}
        total={130}
        onOffsetChange={() => {}}
        onLimitChange={onLimitChange}
        ariaLabel="Test pages"
      />
    );
    fireEvent.click(screen.getByLabelText(/rows per page/i));
    fireEvent.click(document.querySelector('[role="option"][data-value="100"]'));
    expect(onLimitChange).toHaveBeenCalledWith(100);
  });

  it("has the given accessible label on the nav landmark", () => {
    render(<Pagination offset={0} limit={50} total={130} onOffsetChange={() => {}} ariaLabel="Transactions pages" />);
    expect(screen.getByRole("navigation", { name: "Transactions pages" })).toBeInTheDocument();
  });
});
