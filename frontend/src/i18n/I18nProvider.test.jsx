import { act, render, screen } from "@testing-library/react";

import { I18nProvider, rich, translate, useI18n } from "./I18nProvider";
import { LANGUAGE_STORAGE_KEY, initialLanguage } from "./languages";

afterEach(() => localStorage.clear());

describe("translate", () => {
  it("looks the English text up and fills placeholders", () => {
    const messages = { "Hello {name}": "Ahoj {name}" };
    expect(translate(messages, "Hello {name}", { name: "Ada" })).toBe("Ahoj Ada");
  });

  it("falls back to the English text when there is no translation", () => {
    expect(translate({}, "Connect {broker}", { broker: "XTB" })).toBe("Connect XTB");
    expect(translate(null, "Retry")).toBe("Retry");
  });

  it("leaves a placeholder without a value as it is", () => {
    expect(translate(null, "Hi {name}", {})).toBe("Hi {name}");
  });
});

describe("rich", () => {
  it("draws tagged words with their renderer and keeps the rest as text", () => {
    render(<p>{rich("Open <b>Settings</b> now.", { b: (words) => <strong>{words}</strong> })}</p>);
    expect(screen.getByText("Settings").tagName).toBe("STRONG");
    expect(screen.getByRole("paragraph")).toHaveTextContent("Open Settings now.");
  });
});

describe("initialLanguage", () => {
  it("prefers the saved choice, then the landing page's, then the browser's", () => {
    expect(initialLanguage(["pl-PL"])).toBe("pl");
    localStorage.setItem("portfyl_landing_language", "de");
    expect(initialLanguage(["pl-PL"])).toBe("de");
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "nl");
    expect(initialLanguage(["pl-PL"])).toBe("nl");
  });

  it("ignores languages the app does not offer", () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "xx");
    expect(initialLanguage(["ja-JP", "sk"])).toBe("en");
  });
});

function Probe() {
  const { language, setLanguage, t } = useI18n();
  return (
    <>
      <p>{t("Settings")}</p>
      <output>{language}</output>
      <button type="button" onClick={() => setLanguage("cs")}>cs</button>
    </>
  );
}

describe("I18nProvider", () => {
  it("renders the saved language from the first paint and sets the page language", async () => {
    render(<I18nProvider initial="fr"><Probe /></I18nProvider>);

    expect(await screen.findByText("Paramètres")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
  });

  it("switches language, saves the choice and translates", async () => {
    render(<I18nProvider initial="en"><Probe /></I18nProvider>);
    expect(screen.getByText("Settings")).toBeInTheDocument();

    await act(async () => screen.getByRole("button", { name: "cs" }).click());

    expect(await screen.findByText("Nastavení")).toBeInTheDocument();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("cs");
  });

  it("does not save a language it only guessed", async () => {
    render(<I18nProvider initial="de"><Probe /></I18nProvider>);

    expect(await screen.findByText("Einstellungen")).toBeInTheDocument();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBeNull();
  });
});
