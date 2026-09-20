import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { useStockDetail } from "./useStockDetail";

function wrapper({ children }) {
  return <MemoryRouter initialEntries={["/"]}>{children}</MemoryRouter>;
}

it("navigates to an encoded uppercase stock route and ignores an empty ticker", () => {
  const { result } = renderHook(() => ({ detail: useStockDetail(), location: useLocation() }), { wrapper });

  act(() => result.current.detail.openStock("brk/b"));
  expect(result.current.location.pathname).toBe("/stock/BRK%2FB");
  act(() => result.current.detail.openStock(""));
  expect(result.current.location.pathname).toBe("/stock/BRK%2FB");
});
