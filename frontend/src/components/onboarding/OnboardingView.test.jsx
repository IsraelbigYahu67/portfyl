import { createRef } from "react";
import { render, screen } from "@testing-library/react";

import { legacyColorClassesIn } from "../../test/legacyClasses";

import OnboardingView, { ONBOARDING_CHOICES, ONBOARDING_CHOICE_KEYS, choiceHandler } from "./OnboardingView";

const noop = () => {};

function choiceButtons() {
  return ONBOARDING_CHOICES.map(({ title }) => screen.getByRole("button", { name: title }));
}

describe("OnboardingView", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses only token-based colors", async () => {
    expect(await legacyColorClassesIn(new URL("./OnboardingView.jsx", import.meta.url))).toEqual([]);
  });

  it("lists one unique key per choice", () => {
    expect(ONBOARDING_CHOICE_KEYS).toEqual(ONBOARDING_CHOICES.map(({ key }) => key));
    expect(new Set(ONBOARDING_CHOICE_KEYS).size).toBe(ONBOARDING_CHOICE_KEYS.length);
    expect(ONBOARDING_CHOICE_KEYS).not.toContain("blank");
  });

  it("renders plain action buttons when no selection is in use", () => {
    render(<OnboardingView onChoose={noop} onStartBlank={noop} />);

    for (const button of choiceButtons()) {
      expect(button).not.toHaveAttribute("aria-pressed");
      expect(button).not.toHaveClass("outline-brand");
    }
    expect(screen.queryByText("Selected")).not.toBeInTheDocument();
    expect(screen.getByRole("main")).not.toHaveAttribute("tabindex");
  });

  it("marks the selected choice with aria-pressed, an outline and a badge", () => {
    const { rerender } = render(<OnboardingView onChoose={noop} onStartBlank={noop} selected={null} />);

    for (const button of choiceButtons()) expect(button).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText("Selected")).not.toBeInTheDocument();

    rerender(<OnboardingView onChoose={noop} onStartBlank={noop} selected="demo" />);

    const demo = screen.getByRole("button", { name: "Explore sample portfolio" });
    expect(demo).toHaveAttribute("aria-pressed", "true");
    // An outline, not a border or ring: Clay hides .card borders and owns the
    // card box-shadow (index.css), but sets no outline on cards.
    expect(demo).toHaveClass("outline", "outline-2", "outline-brand");
    expect(demo).toHaveTextContent("Selected");
    for (const button of choiceButtons().filter((button) => button !== demo)) {
      expect(button).toHaveAttribute("aria-pressed", "false");
      expect(button).not.toHaveClass("outline-brand");
    }
  });

  it("forwards mainRef to a programmatically focusable <main>", () => {
    const mainRef = createRef();
    render(<OnboardingView onChoose={noop} onStartBlank={noop} mainRef={mainRef} />);

    const main = screen.getByRole("main");
    expect(mainRef.current).toBe(main);
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(main).toHaveClass("!outline-none");
  });
});

describe("choiceHandler", () => {
  it("returns the handler registered for a choice", () => {
    const demo = vi.fn();
    choiceHandler({ demo }, "demo")();
    expect(demo).toHaveBeenCalledTimes(1);
  });

  it("logs and does nothing for a choice without a handler", () => {
    const error = vi.spyOn(console, "error").mockImplementation(noop);

    expect(() => choiceHandler({}, "new-choice")()).not.toThrow();
    expect(() => choiceHandler({ demo: "not a function" }, "demo")()).not.toThrow();
    // Inherited properties are not handlers.
    expect(() => choiceHandler({}, "toString")()).not.toThrow();

    expect(error).toHaveBeenCalledTimes(3);
    expect(error).toHaveBeenCalledWith('Onboarding choice "new-choice" has no handler.');
  });
});
