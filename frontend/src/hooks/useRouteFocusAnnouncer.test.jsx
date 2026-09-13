import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { useRouteFocusAnnouncer } from "./useRouteFocusAnnouncer";

function Shell({ children }) {
  const mainRef = useRef(null);
  useRouteFocusAnnouncer(mainRef);
  return (
    <main ref={mainRef} id="main-content" tabIndex={-1}>
      {children}
    </main>
  );
}

function PageA() {
  const navigate = useNavigate();
  return (
    <div>
      <h1>Page A</h1>
      <button onClick={() => navigate("/b")}>Go to B</button>
      <button onClick={() => navigate("/plain")}>Go to plain page</button>
    </div>
  );
}

function Harness() {
  return (
    <Shell>
      <Routes>
        <Route path="/a" element={<PageA />} />
        <Route path="/b" element={<h1>Page B</h1>} />
        <Route path="/plain" element={<p>Plain page</p>} />
      </Routes>
    </Shell>
  );
}

describe("useRouteFocusAnnouncer", () => {
  it("focuses the new page's h1 after a route change", async () => {
    render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Go to B"));
    const heading = await screen.findByText("Page B");
    expect(heading).toHaveFocus();
    expect(heading).toHaveAttribute("tabindex", "-1");
  });

  it("falls back to the main landmark when a page has no h1", async () => {
    render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Go to plain page"));
    await screen.findByText("Plain page");
    expect(document.querySelector("#main-content")).toHaveFocus();
  });

  it("does not steal focus on the initial render", () => {
    render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(document.body).toHaveFocus();
  });
});
