import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode, useRef } from "react";
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { resetRouteFocusAnnouncerForTests, useRouteFocusAnnouncer } from "./useRouteFocusAnnouncer";

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

// Mirrors App.jsx: the onboarding preview renders its own <main> outside the
// shell, so every switch between them unmounts one caller and mounts the other.
function Preview() {
  const mainRef = useRef(null);
  useRouteFocusAnnouncer(mainRef);
  return (
    <main ref={mainRef} tabIndex={-1}>
      <h1>Preview heading</h1>
      <Link to="/settings">Exit preview</Link>
    </main>
  );
}

function PreviewOrShell({ settings = <h1>Settings heading</h1> }) {
  const { pathname } = useLocation();
  if (pathname === "/preview") return <Preview />;
  return (
    <Shell>
      <Routes>
        <Route path="/settings" element={<>{settings}<Link to="/preview">Open preview</Link></>} />
      </Routes>
    </Shell>
  );
}

describe("useRouteFocusAnnouncer", () => {
  beforeEach(() => {
    resetRouteFocusAnnouncerForTests();
  });

  it('focuses a heading that arrives after the route fallback', async () => {
    const content = heading => <MemoryRouter initialEntries={['/a']}><Shell><Routes><Route path="/a" element={<PageA />} /><Route path="/b" element={heading ? <h1>Deferred page</h1> : <div role="status">Loading page</div>} /></Routes></Shell></MemoryRouter>;
    const view = render(content(false));
    fireEvent.click(screen.getByText('Go to B'));
    view.rerender(content(true));
    await waitFor(() => expect(screen.getByText('Deferred page')).toHaveFocus());
  });
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

  it("focuses the h1 when a remount lands on a different path than the last one seen", () => {
    const first = render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>,
    );
    first.unmount();

    render(
      <MemoryRouter initialEntries={["/b"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Page B" })).toHaveFocus();
  });

  it("does not move focus when a remount lands on the path it last saw", () => {
    const first = render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>,
    );
    first.unmount();

    render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(document.body).toHaveFocus();
  });

  it("moves focus into and back out of a page rendered outside the shell", () => {
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <PreviewOrShell />
      </MemoryRouter>,
    );
    expect(document.body).toHaveFocus();

    fireEvent.click(screen.getByRole("link", { name: "Open preview" }));
    expect(screen.getByRole("heading", { name: "Preview heading" })).toHaveFocus();

    fireEvent.click(screen.getByRole("link", { name: "Exit preview" }));
    expect(screen.getByRole("heading", { name: "Settings heading" })).toHaveFocus();
  });

  it("still waits for a lazy heading when StrictMode re-runs the remount effect", async () => {
    const content = settings => (
      <StrictMode>
        <MemoryRouter initialEntries={["/preview"]}>
          <PreviewOrShell settings={settings} />
        </MemoryRouter>
      </StrictMode>
    );
    const view = render(content(<div role="status">Loading page</div>));
    fireEvent.click(screen.getByRole("link", { name: "Exit preview" }));
    expect(document.querySelector("#main-content")).toHaveFocus();

    view.rerender(content(<h1>Settings heading</h1>));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Settings heading" })).toHaveFocus());
  });
});
