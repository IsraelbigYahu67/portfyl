import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { COPY, LANGUAGES } from "./welcomeCopy";
import { useAnalytics } from "../analytics/AnalyticsProvider";
import LandingHeader from "../components/landing/LandingHeader";
import LandingHero from "../components/landing/LandingHero";
import BrokerList from "../components/landing/BrokerList";
import FeatureList from "../components/landing/FeatureList";
import HowItWorks from "../components/landing/HowItWorks";
import PricingTeaser from "../components/landing/PricingTeaser";
import LandingFaq from "../components/landing/LandingFaq";
import LandingFooter from "../components/landing/LandingFooter";
import { isLanguage, rememberLanguage, savedLanguage } from "../components/landing/languagePrefs";
import { registerUrl } from "../lib/signupIntent";
import { CLAY_STYLE } from "../lib/clayStyle";
import { LANDING_PATHS } from "../lib/routes";
import { ANALYTICS_EVENTS } from "../analytics/eventContract";
import { DEMO_SESSION_SCOPE } from "../analytics/useDemoAnalytics";
import "./Welcome.css";
import "../fonts.css";

const SUGGESTION_DISMISSED_KEY = "portfyl_landing_suggestion_dismissed";

// The language to offer a visitor reading `pageLanguage`: their saved choice,
// else their browser's first supported language (Slovak reads Czech;
// anything unsupported reads English). Null when it is the page's own.
export function suggestedLanguage(pageLanguage, { saved = savedLanguage(), browserLanguages = [] } = {}) {
  let preferred = saved;
  if (!preferred) {
    const base = (browserLanguages[0] || "").toLowerCase().split("-")[0];
    preferred = base === "sk" ? "cs" : isLanguage(base) ? base : base ? "en" : null;
  }
  return preferred && preferred !== pageLanguage ? preferred : null;
}

function suggestionDismissed() {
  try { return sessionStorage.getItem(SUGGESTION_DISMISSED_KEY) === "1"; } catch { return false; }
}

// A one-line offer of the visitor's own language. Rendered only after mount
// (it depends on storage and the browser), so the prerendered HTML -- what
// crawlers index -- is the page's language alone. Never redirects.
function LanguageSuggestion({ pageLanguage }) {
  const [offer, setOffer] = useState(null);
  useEffect(() => {
    if (suggestionDismissed()) return;
    const code = suggestedLanguage(pageLanguage, { browserLanguages: navigator.languages?.length ? navigator.languages : [navigator.language] });
    setOffer(code ? LANGUAGES.find((language) => language.code === code) : null);
  }, [pageLanguage]);
  if (!offer) return null;
  function dismiss() {
    setOffer(null);
    try { sessionStorage.setItem(SUGGESTION_DISMISSED_KEY, "1"); } catch { /* Storage may be unavailable. */ }
  }
  return (
    <aside className="welcome-language-suggestion welcome-container" lang={offer.code} aria-label={offer.suggestion}>
      <span>{offer.suggestion}</span>
      <a href={LANDING_PATHS[offer.code]} hrefLang={offer.code} onClick={() => rememberLanguage(offer.code)}>{offer.action}</a>
      <button type="button" onClick={dismiss} aria-label={offer.dismiss} title={offer.dismiss}><X size={16} aria-hidden="true" /></button>
    </aside>
  );
}

const SEARCH_ENGINE_HOSTS = ["google.", "bing.", "seznam.", "duckduckgo.", "yahoo."];
const SOCIAL_HOSTS = ["facebook.", "twitter.", "x.com", "linkedin.", "instagram.", "t.co"];

// referrer_class is a coarse bucket, never the raw referrer URL -- see
// eventContract.js's landing_viewed schema.
function classifyReferrer(referrer) {
  if (!referrer) return "direct";
  try {
    const host = new URL(referrer).hostname.toLowerCase();
    if (host === window.location.hostname) return "internal";
    if (SEARCH_ENGINE_HOSTS.some((s) => host.includes(s))) return "search";
    if (SOCIAL_HOSTS.some((s) => host.includes(s))) return "social";
    return "referral";
  } catch {
    return "unknown";
  }
}

// The public home in one language. `language` comes from the URL ("/" = cs,
// "/en/", "/de/"), so the same URL always renders the same page -- on the
// server (prerender) and in the browser alike. `signupOpen` decides the call
// to action: the trial sign-up when VITE_PUBLIC_SIGNUP is "true", else the demo.
export default function Welcome({ language, signupOpen = import.meta.env.VITE_PUBLIC_SIGNUP === "true" }) {
  const copy = COPY[language];
  const { ready, capture, captureOnce } = useAnalytics();
  const landingViewedRef = useRef(false);

  useEffect(() => {
    const previousTitle = document.title;
    const previousLanguage = document.documentElement.lang;
    document.title = copy.title;
    document.documentElement.lang = language;
    return () => { document.title = previousTitle; document.documentElement.lang = previousLanguage; };
  }, [language, copy]);

  // landing_viewed fires once per page load, only once analytics is ready
  // (pending never sends). UTM params are read once at mount, sanitized
  // through the event contract, then stripped from the URL -- the raw URL
  // and its query string are never captured.
  useEffect(() => {
    if (!ready || landingViewedRef.current) return;
    landingViewedRef.current = true;
    const params = new URL(window.location.href).searchParams;
    capture(ANALYTICS_EVENTS.LANDING_VIEWED, {
      language,
      referrer_class: classifyReferrer(document.referrer),
      // eventContract.js's stringField rejects empty strings (and the
      // contract is off-limits to change here), so an absent UTM param is
      // sent as the literal placeholder "none" rather than "".
      utm_source: params.get("utm_source") || "none",
      utm_medium: params.get("utm_medium") || "none",
      utm_campaign: params.get("utm_campaign") || "none",
    });
    if (params.has("utm_source") || params.has("utm_medium") || params.has("utm_campaign")) {
      const url = new URL(window.location.href);
      ["utm_source", "utm_medium", "utm_campaign"].forEach((key) => url.searchParams.delete(key));
      window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    }
  }, [ready, language, capture]);

  // Same-tab, unmodified click: swap to the demo without a full reload.
  // Modified clicks (new tab/window, download, etc.) fall through to the
  // plain href="/demo" anchor and record entry_point="direct" once the demo
  // mounts, via the same session-scoped captureOnce key.
  function handleDemoCtaClick(entryPoint) {
    return (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      // The demo reads the saved language; entering it from this page is a choice.
      rememberLanguage(language);
      event.preventDefault();
      captureOnce(DEMO_SESSION_SCOPE, ANALYTICS_EVENTS.DEMO_STARTED, { language, entry_point: entryPoint });
      window.history.pushState(null, "", "/demo");
      window.dispatchEvent(new PopStateEvent("popstate"));
    };
  }

  const onHeroDemo = handleDemoCtaClick("landing_hero");
  const onClosingDemo = handleDemoCtaClick("landing_closing");
  return (
    <div className="welcome theme-clay" id="nahoru" style={CLAY_STYLE}>
      <a className="welcome-skip" href="#obsah">{copy.skip}</a>
      <LandingHeader copy={copy} language={language} signupOpen={signupOpen} onDemo={onHeroDemo} />
      <LanguageSuggestion pageLanguage={language} />
      <main id="obsah">
        <LandingHero copy={copy} language={language} signupOpen={signupOpen} onDemo={onHeroDemo} />
        <BrokerList copy={copy} language={language} signupOpen={signupOpen} onDemo={onHeroDemo} />
        <FeatureList copy={copy} language={language} />
        <HowItWorks copy={copy} />
        <PricingTeaser copy={copy} language={language} signupOpen={signupOpen} />
        <LandingFaq copy={copy} signupOpen={signupOpen} />
        <section className="welcome-closing" aria-labelledby="closing-title">
          <div className="welcome-container">
            <h2 id="closing-title">{copy.closing}</h2>
            {signupOpen
              ? <a className="welcome-btn welcome-btn-big" href={registerUrl({ source: "landing_closing", lang: language })}>{copy.trialCtaShort}</a>
              : <a className="welcome-btn welcome-btn-big" href="/demo" onClick={onClosingDemo}>{copy.demoCta}</a>}
          </div>
        </section>
      </main>
      <LandingFooter copy={copy} language={language} onDemo={handleDemoCtaClick("direct")} />
    </div>
  );
}
