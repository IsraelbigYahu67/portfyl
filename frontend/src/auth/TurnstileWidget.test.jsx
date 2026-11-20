import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TurnstileWidget, { resetTurnstileLoader } from "./TurnstileWidget";

const SCRIPT = 'script[src^="https://challenges.cloudflare.com/turnstile/v0/api.js"]';

function stubTurnstile() {
  const stub = { render: vi.fn(() => "widget-1"), remove: vi.fn(), reset: vi.fn() };
  window.turnstile = stub;
  return stub;
}

beforeEach(() => resetTurnstileLoader());
afterEach(() => {
  delete window.turnstile;
  document.querySelectorAll(SCRIPT).forEach((script) => script.remove());
});

describe("TurnstileWidget", () => {
  it("renders explicitly with the site key, the signup action and the language", async () => {
    const turnstile = stubTurnstile();
    await act(async () => {
      render(<TurnstileWidget siteKey="1x00000000000000000000AA" language="cs" onToken={() => {}} />);
    });

    expect(turnstile.render).toHaveBeenCalledTimes(1);
    expect(turnstile.render.mock.calls[0][1]).toMatchObject({
      sitekey: "1x00000000000000000000AA",
      action: "signup",
      language: "cs",
      theme: "light",
    });
  });

  it("hands the token to onToken and reports widget errors", async () => {
    const turnstile = stubTurnstile();
    const onToken = vi.fn();
    const onError = vi.fn();
    await act(async () => {
      render(<TurnstileWidget siteKey="key" onToken={onToken} onError={onError} />);
    });
    const options = turnstile.render.mock.calls[0][1];

    options.callback("tok");
    options["error-callback"]();
    options["expired-callback"]();

    expect(onToken).toHaveBeenCalledWith("tok");
    expect(onError).toHaveBeenCalledTimes(1);
    expect(turnstile.reset).toHaveBeenCalledWith("widget-1");
  });

  it("removes the widget on unmount", async () => {
    const turnstile = stubTurnstile();
    let utils;
    await act(async () => {
      utils = render(<TurnstileWidget siteKey="key" onToken={() => {}} />);
    });

    utils.unmount();

    expect(turnstile.remove).toHaveBeenCalledWith("widget-1");
  });

  it("injects Cloudflare's script once for two widgets, then renders both", async () => {
    const onError = vi.fn();
    await act(async () => {
      render(
        <>
          <TurnstileWidget siteKey="key" onToken={() => {}} onError={onError} />
          <TurnstileWidget siteKey="key" onToken={() => {}} onError={onError} />
        </>,
      );
    });
    const scripts = document.querySelectorAll(SCRIPT);
    expect(scripts).toHaveLength(1);

    const turnstile = stubTurnstile();
    await act(async () => {
      scripts[0].onload();
    });

    expect(turnstile.render).toHaveBeenCalledTimes(2);
    expect(onError).not.toHaveBeenCalled();
  });

  it("reports an error when the script cannot load", async () => {
    const onError = vi.fn();
    await act(async () => {
      render(<TurnstileWidget siteKey="key" onToken={() => {}} onError={onError} />);
    });

    await act(async () => {
      document.querySelector(SCRIPT).onerror();
    });

    expect(onError).toHaveBeenCalled();
  });
});
