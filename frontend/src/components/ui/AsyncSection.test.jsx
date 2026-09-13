import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import AsyncSection from "./AsyncSection";

it("uses loading, error, empty, content precedence", () => {
  const { rerender } = render(
    <AsyncSection
      isLoading
      loading={<p>Skeleton</p>}
      error={new Error("Boom")}
      isEmpty
      empty={<p>Empty</p>}
    >
      <p>Data</p>
    </AsyncSection>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Skeleton");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();

  rerender(
    <AsyncSection error={new Error("Boom")} isEmpty empty={<p>Empty</p>}>
      <p>Data</p>
    </AsyncSection>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Boom");

  rerender(
    <AsyncSection isEmpty empty={<p>Empty</p>}>
      <p>Data</p>
    </AsyncSection>,
  );
  expect(screen.getByText("Empty")).toBeInTheDocument();

  rerender(
    <AsyncSection>
      <p>Data</p>
    </AsyncSection>,
  );
  expect(screen.getByText("Data")).toBeInTheDocument();
});

it("offers retry only when provided", () => {
  const retry = vi.fn();
  const { rerender } = render(
    <AsyncSection error={new Error("Nope")} onRetry={retry}>
      <span />
    </AsyncSection>,
  );
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(retry).toHaveBeenCalledOnce();

  rerender(
    <AsyncSection error={new Error("Still nope")}>
      <span />
    </AsyncSection>,
  );
  expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
});
