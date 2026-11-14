import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { I18nProvider } from "../../i18n/I18nProvider";
import { PREFERENCES_CONFIRMED_KEY } from "../../lib/preferencesConfirmation";
import { legacyColorClassesIn } from "../../test/legacyClasses";

import PreferencesChip from "./PreferencesChip";

function Harness({ initialCurrency, onCurrencyChange }) {
  const [currency, setCurrency] = useState(initialCurrency);
  return (
    <PreferencesChip
      currency={currency}
      onCurrencyChange={(code) => {
        onCurrencyChange(code);
        setCurrency(code);
      }}
    />
  );
}

function renderChip({ language = "en", currency = "GBP", onCurrencyChange = vi.fn() } = {}) {
  render(
    <I18nProvider initial={language}>
      <Harness initialCurrency={currency} onCurrencyChange={onCurrencyChange} />
    </I18nProvider>
  );
  return { onCurrencyChange };
}

function pick(value) {
  fireEvent.click(document.querySelector(`[role="option"][data-value="${value}"]`));
}

describe("PreferencesChip", () => {
  afterEach(() => localStorage.clear());

  it("uses only token-based colors", async () => {
    expect(await legacyColorClassesIn(new URL("./PreferencesChip.jsx", import.meta.url))).toEqual([]);
  });

  it("is a collapsed button naming the language and the currency", () => {
    renderChip();

    const chip = screen.getByRole("button", { name: "English · GBP" });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("combobox", { name: "Language" })).not.toBeInTheDocument();
  });

  it("names the language in its own language", async () => {
    renderChip({ language: "cs", currency: "CZK" });

    expect(await screen.findByRole("button", { name: "Čeština · CZK" })).toBeInTheDocument();
  });

  it("expands to a language select, a currency select and a note", () => {
    renderChip();

    fireEvent.click(screen.getByRole("button", { name: "English · GBP" }));

    expect(screen.getByRole("button", { name: "English · GBP" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveAttribute("data-value", "en");
    expect(screen.getByRole("combobox", { name: "Display currency" })).toHaveAttribute("data-value", "GBP");
    expect(screen.getByText("You can change both later in Settings → Preferences.")).toBeInTheDocument();
  });

  it("offers every app language by its own name and the currencies as symbol · code", async () => {
    renderChip();
    fireEvent.click(screen.getByRole("button", { name: "English · GBP" }));

    fireEvent.click(screen.getByRole("combobox", { name: "Language" }));
    expect(within(screen.getByRole("listbox", { name: "Language" })).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Čeština", "English", "Deutsch", "Français", "Español", "Italiano", "Português", "Polski", "Nederlands",
    ]);
    // The menu counts as open from the next animation frame.
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Language" })).toHaveAttribute("aria-expanded", "true"));
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Language" }), { key: "Escape" });

    fireEvent.click(screen.getByRole("combobox", { name: "Display currency" }));
    expect(within(screen.getByRole("listbox", { name: "Display currency" })).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "$ · USD", "Kč · CZK", "€ · EUR", "£ · GBP", "zł · PLN",
    ]);
  });

  it("picking a language switches it and preselects its local currency", async () => {
    const { onCurrencyChange } = renderChip();
    fireEvent.click(screen.getByRole("button", { name: "English · GBP" }));

    fireEvent.click(screen.getByRole("combobox", { name: "Language" }));
    pick("cs");

    expect(onCurrencyChange).toHaveBeenLastCalledWith("CZK");
    expect(await screen.findByRole("button", { name: "Čeština · CZK" })).toBeInTheDocument();
    expect(localStorage.getItem("portfyl_language")).toBe("cs");
  });

  it("picking a currency changes only the currency", () => {
    const { onCurrencyChange } = renderChip();
    fireEvent.click(screen.getByRole("button", { name: "English · GBP" }));

    fireEvent.click(screen.getByRole("combobox", { name: "Display currency" }));
    pick("EUR");

    expect(onCurrencyChange).toHaveBeenCalledTimes(1);
    expect(onCurrencyChange).toHaveBeenCalledWith("EUR");
    expect(screen.getByRole("button", { name: "English · EUR" })).toBeInTheDocument();
    expect(localStorage.getItem("portfyl_language")).toBeNull();
  });

  it("'Looks good' confirms the preferences and collapses", () => {
    renderChip();
    fireEvent.click(screen.getByRole("button", { name: "English · GBP" }));
    expect(localStorage.getItem(PREFERENCES_CONFIRMED_KEY)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Looks good" }));

    expect(localStorage.getItem(PREFERENCES_CONFIRMED_KEY)).toBe("1");
    expect(screen.getByRole("button", { name: "English · GBP" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Looks good" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "English · GBP" })).toHaveFocus();
  });

  it("closes on Escape, returns focus to the chip and confirms nothing", () => {
    renderChip();
    fireEvent.click(screen.getByRole("button", { name: "English · GBP" }));

    fireEvent.keyDown(screen.getByRole("button", { name: "Looks good" }), { key: "Escape" });

    const chip = screen.getByRole("button", { name: "English · GBP" });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(chip).toHaveFocus();
    expect(localStorage.getItem(PREFERENCES_CONFIRMED_KEY)).toBeNull();
  });

  it("Escape in an open select closes only the select menu", async () => {
    renderChip();
    fireEvent.click(screen.getByRole("button", { name: "English · GBP" }));
    const language = screen.getByRole("combobox", { name: "Language" });
    fireEvent.click(language);
    await waitFor(() => expect(language).toHaveAttribute("aria-expanded", "true"));

    fireEvent.keyDown(language, { key: "Escape" });
    await waitFor(() => expect(language).toHaveAttribute("aria-expanded", "false"));

    expect(screen.getByRole("button", { name: "English · GBP" })).toHaveAttribute("aria-expanded", "true");
  });

  it("collapses again when the chip is clicked a second time", () => {
    renderChip();
    const chip = screen.getByRole("button", { name: "English · GBP" });

    fireEvent.click(chip);
    fireEvent.click(chip);

    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(localStorage.getItem(PREFERENCES_CONFIRMED_KEY)).toBeNull();
  });
});
