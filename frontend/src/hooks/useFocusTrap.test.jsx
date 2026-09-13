import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { useFocusTrap } from "./useFocusTrap";

function Harness() {
  const [open, setOpen] = useState(false);
  const trapRef = useFocusTrap({ active: open, onEscape: () => setOpen(false) });
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open</button>
      {open && (
        <div ref={trapRef} role="dialog" aria-modal="true">
          <button>First</button>
          <button>Last</button>
        </div>
      )}
    </div>
  );
}

describe("useFocusTrap", () => {
  it("focuses the first focusable element on open", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    expect(screen.getByText("First")).toHaveFocus();
  });

  it("wraps Tab from the last element back to the first", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    screen.getByText("Last").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByText("First")).toHaveFocus();
  });

  it("wraps Shift+Tab from the first element back to the last", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByText("Last")).toHaveFocus();
  });

  it("closes on Escape and restores focus to the trigger", () => {
    render(<Harness />);
    const opener = screen.getByText("Open");
    opener.focus();
    fireEvent.click(opener);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("locks and restores body scroll", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});
