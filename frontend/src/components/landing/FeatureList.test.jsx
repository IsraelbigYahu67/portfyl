import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FeatureList from "./FeatureList";
import { LANDING_IMAGES } from "./landingImages";
import * as registry from "./miniDemoRegistry";
import { MINI_DEMO_KINDS } from "./miniDemoRegistry";
import { COPY, LANGUAGES } from "../../pages/welcomeCopy";

// The real set has no phone picture yet; this one does, to prove that the
// placeholder leaves it out.
vi.mock("./landingImages", () => ({
  LANDING_IMAGES: Object.freeze({
    hero: { src: "/landing/hero.png", width: 1004, height: 455 },
    allocation: { src: "/landing/allocation.png", width: 1047, height: 365 },
    sectors: null, dividends: null,
    stock: { src: "/landing/stock.png", width: 1047, height: 350 },
    valuation: null, analytics: null, importPreview: null, onboardingBrokers: null,
    phoneDashboard: null,
    phoneAllocation: { src: "/landing/phone-allocation.png", width: 390, height: 800 },
  }),
}));

// A frame never reaches its demo here: the observer never reports a crossing.
beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} takeRecords() { return []; } });
});
afterEach(() => vi.unstubAllGlobals());

describe.each(LANGUAGES)("$name feature list", ({ code }) => {
  const copy = COPY[code];

  it("shows all five features as rows, each with one mini demo frame in the planned order", () => {
    const { container } = render(<FeatureList copy={copy} language={code} />);
    const articles = [...container.querySelectorAll("article.welcome-feature")];
    expect(articles).toHaveLength(5);
    for (const article of articles) expect(article.querySelectorAll("figure.welcome-minidemo")).toHaveLength(1);
    expect(articles.map((article) => article.querySelector("figure.welcome-minidemo").dataset.minidemo)).toEqual(MINI_DEMO_KINDS);
    expect(articles.map((article) => article.querySelector("h3").textContent)).toEqual(copy.features.map((feature) => feature.title));
  });

  it("drops the text strip when every feature has a demo", () => {
    const { container } = render(<FeatureList copy={copy} language={code} />);
    expect(container.querySelector(".welcome-more")).toBeNull();
  });

  it("labels every frame and links nothing under it (there is no full demo page any more)", () => {
    const { container } = render(<FeatureList copy={copy} language={code} />);
    for (const frame of container.querySelectorAll("figure.welcome-minidemo")) {
      expect(frame).toHaveTextContent(copy.miniDemo.badge);
      expect(frame).toHaveTextContent(copy.miniDemo.disclaimer);
      expect(frame.querySelector("a")).toBeNull();
    }
    expect([...container.querySelectorAll("a[href]")].filter((link) => /^\/demo/.test(link.getAttribute("href")))).toEqual([]);
  });

  it("does not export the old demo page links from the registry", () => {
    expect(registry.DEMO_HREFS).toBeUndefined();
  });
});

describe("placeholder content", () => {
  const copy = COPY.en;

  it("holds the desktop screenshots of the feature, never a phone picture", () => {
    const withPhone = { ...copy, features: copy.features.map((feature, index) => (index === 0
      ? { ...feature, images: ["allocation", "phoneAllocation"], alts: ["desktop", "phone"] }
      : feature)) };
    const { container } = render(<FeatureList copy={withPhone} language="en" />);
    const allocation = container.querySelector('figure[data-minidemo="allocation"]');
    expect([...allocation.querySelectorAll("img")].map((img) => img.getAttribute("src"))).toEqual([LANDING_IMAGES.allocation.src]);
    const stock = container.querySelector('figure[data-minidemo="stock"]');
    expect([...stock.querySelectorAll("img")].map((img) => img.getAttribute("src"))).toEqual([LANDING_IMAGES.stock.src]);
  });

  it("holds only text for a feature without a screenshot", () => {
    const { container } = render(<FeatureList copy={copy} language="en" />);
    const portfolios = container.querySelector('figure[data-minidemo="portfolios"]');
    expect(portfolios.querySelector("img")).toBeNull();
    expect(portfolios).toHaveTextContent(copy.miniDemo.loading);
  });

  it("still lays out a feature without a demo as before: a row with a screenshot, otherwise the text strip", () => {
    const plain = { ...copy, features: copy.features.map(({ demo, ...rest }) => rest) };
    const { container } = render(<FeatureList copy={plain} language="en" />);
    expect(container.querySelectorAll("figure.welcome-minidemo")).toHaveLength(0);
    expect(container.querySelectorAll("article.welcome-feature")).toHaveLength(2);
    expect(container.querySelectorAll(".welcome-more h3")).toHaveLength(3);
  });
});
