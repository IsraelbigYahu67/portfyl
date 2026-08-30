import { render, screen } from "@testing-library/react";
import Reveal from "./Reveal";

describe("Reveal", () => {
  it("renders children immediately when IntersectionObserver is unavailable (jsdom default)", () => {
    render(<Reveal>hello</Reveal>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("applies the delay as a transition-delay style", () => {
    const { container } = render(<Reveal delay={150}>hi</Reveal>);
    expect(container.firstChild.style.transitionDelay).toBe("150ms");
  });
});
