import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, afterEach } from "vitest";
import AnalyticsProvider from "./AnalyticsProvider";
import ConsentBanner from "./ConsentBanner";
import { createMemoryAdapter } from "./analyticsClient";
import { ANALYTICS_COPY, LANGUAGE_KEY } from "./analyticsCopy";

function mount() {
  return render(
    <AnalyticsProvider initialConsent="pending" adapterFactory={() => createMemoryAdapter()}>
      <ConsentBanner />
    </AnalyticsProvider>
  );
}

afterEach(() => localStorage.clear());

describe("ConsentBanner", () => {
  it.each(Object.keys(ANALYTICS_COPY))("shows the essential/optional explanation and accessible actions in %s", (lang) => {
    localStorage.setItem(LANGUAGE_KEY, lang);
    mount();
    const t = ANALYTICS_COPY[lang];
    const region = screen.getByRole("region", { name: t.bannerTitle });
    expect(region).toHaveTextContent(t.essential);
    expect(region).toHaveTextContent(t.optional);
    expect(screen.getByRole("button", { name: t.accept })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.reject })).toBeInTheDocument();
  });

  it("accepting hides the banner", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: ANALYTICS_COPY.en.accept }));
    await waitFor(() => expect(screen.queryByRole("region", { name: ANALYTICS_COPY.en.bannerTitle })).not.toBeInTheDocument());
  });

  it("rejecting hides the banner", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: ANALYTICS_COPY.en.reject }));
    await waitFor(() => expect(screen.queryByRole("region", { name: ANALYTICS_COPY.en.bannerTitle })).not.toBeInTheDocument());
  });
});
