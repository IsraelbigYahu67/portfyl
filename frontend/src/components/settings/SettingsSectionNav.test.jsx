import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import SettingsSectionNav from "./SettingsSectionNav";

it("renders real section links and preserves unrelated search parameters", () => {
  render(
    <MemoryRouter>
      <SettingsSectionNav value="connections" searchParams={new URLSearchParams("source=alert&section=connections")} onSelect={vi.fn()} />
    </MemoryRouter>,
  );

  const nav = screen.getByRole("navigation", { name: "Settings sections" });
  expect(nav).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Notifications" })).toHaveAttribute("href", "/?source=alert&section=notifications");
  expect(screen.getByRole("link", { name: "Connections" })).toHaveAttribute("aria-current", "page");
});

it("offers a labelled narrow-screen chooser", () => {
  const onSelect = vi.fn();
  render(
    <MemoryRouter>
      <SettingsSectionNav value="preferences" searchParams={new URLSearchParams()} onSelect={onSelect} />
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByRole("combobox", { name: "Settings section" }), { target: { value: "data" } });
  expect(onSelect).toHaveBeenCalledWith("data", true);
});

