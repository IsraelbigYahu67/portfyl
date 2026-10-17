import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUpRight, ChartNoAxesCombined, PieChart, CalendarDays, Layers3, Check, Plus } from "lucide-react";
import { COPY, LANGUAGES, LANGUAGE_KEY } from "./welcomeCopy";
import { useAnalytics } from "../analytics/AnalyticsProvider";
import SegmentedControl from "../components/ui/SegmentedControl";
import { CLAY_TOKENS } from "../lib/themeTokens";
import { ANALYTICS_COPY, getAnalyticsLanguage } from "../analytics/analyticsCopy";
import { ANALYTICS_EVENTS } from "../analytics/eventContract";
import { DEMO_SESSION_SCOPE } from "../analytics/useDemoAnalytics";
import "./Welcome.css";
import "../fonts.css";

const images = ["allocation", "stock", "dashboard", "performance"];
const imageSizes = [[1047, 365], [1047, 350], [1047, 345], [1004, 455]];
const screenshotPath = (name) => `/landing/${name}-live-20260911.png`;
const icons = [ChartNoAxesCombined, PieChart, CalendarDays];

// The landing renders outside App.jsx, so applyAppearance() never runs here.
// Scope the same Clay variables to the page root instead of retyping values;
// the theme-clay class then resolves index.css's --clay-* shadows.
const CLAY_STYLE = {
  "--brand": CLAY_TOKENS.brand,
  "--brand-hover": CLAY_TOKENS.brandHover,
  "--brand-light": CLAY_TOKENS.brandLight,
  "--bg": CLAY_TOKENS.bg,
  "--bg-subtle": CLAY_TOKENS.bgSubtle,
  "--surface-card": CLAY_TOKENS.surfaceCard,
  "--surface-card-elevated": CLAY_TOKENS.surfaceCardElevated,
  "--border": CLAY_TOKENS.border,
  "--hairline": CLAY_TOKENS.hairline,
  "--ink": CLAY_TOKENS.ink,
  "--muted": CLAY_TOKENS.muted,
  "--gain": CLAY_TOKENS.gain,
  "--loss": CLAY_TOKENS.loss,
  "--shadow-ambient": CLAY_TOKENS.shadowAmbient,
  "--shadow-inset": CLAY_TOKENS.shadowInset,
  "--radius-card": CLAY_TOKENS.radiusCard,
  ...Object.fromEntries(CLAY_TOKENS.chart.map((color, i) => [`--chart-${i + 1}`, color])),
};

function savedLanguage() {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    return LANGUAGES.some(({ code }) => code === saved) ? saved : null;
  } catch { return null; }
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

function Brand({ children }) {
  return <><img src="/portfyl-mark.png" alt="" width="38" height="38" />Portfyl{children}</>;
}

function Heading({ lines }) {
  return <>{lines[0]}<br /><span>{lines[1]}</span></>;
}

function AnalyticsPreferencesLink() {
  const { reopenAnalyticsPreferences } = useAnalytics();
  const t = ANALYTICS_COPY[getAnalyticsLanguage()];
  return (
    <button type="button" onClick={reopenAnalyticsPreferences} className="welcome-preview-link" style={{ background: "none", border: "none", cursor: "pointer" }}>
      {t.manage}
    </button>
  );
}

export default function Welcome() {
  const [language, setLanguage] = useState(savedLanguage);
  const [selected, setSelected] = useState(0);
  const headingRef = useRef(null);
  const focusHeading = useRef(false);
  const copy = language ? COPY[language] : null;
  const { ready, capture, captureOnce } = useAnalytics();
  const landingViewedRef = useRef(false);

  useEffect(() => {
    const previousTitle = document.title;
    const previousLanguage = document.documentElement.lang;
    document.title = copy?.title || "Portfyl — CZ / EN / DE";
    document.documentElement.lang = language || "en";
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
      language: language || "en",
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
      event.preventDefault();
      captureOnce(DEMO_SESSION_SCOPE, ANALYTICS_EVENTS.DEMO_STARTED, { language: language || "en", entry_point: entryPoint });
      window.history.pushState(null, "", "/demo");
      window.dispatchEvent(new PopStateEvent("popstate"));
    };
  }

  useEffect(() => {
    if (language && focusHeading.current) {
      headingRef.current?.focus({ preventScroll: true });
      focusHeading.current = false;
    }
  }, [language]);

  function chooseLanguage(code) {
    focusHeading.current = !language;
    setLanguage(code);
    try { localStorage.setItem(LANGUAGE_KEY, code); } catch { /* Storage may be unavailable. */ }
  }

  if (!copy) return (
    <main className="welcome theme-clay welcome-language-screen" style={CLAY_STYLE}>
      <div className="welcome-language-brand welcome-logo"><Brand /></div>
      <div className="welcome-language-intro">
        <p className="welcome-kicker">CZ / EN / DE</p>
        <h1><span lang="cs">Vítejte.</span> <span lang="en">Welcome.</span><br /><span lang="de">Willkommen.</span></h1>
        <p><span lang="cs">Vyberte si jazyk.</span> <span lang="en">Choose your language.</span> <span lang="de">Wähle deine Sprache.</span></p>
      </div>
      <div className="welcome-language-options" role="group" aria-label="Vyberte jazyk / Choose your language / Sprache wählen">
        {LANGUAGES.map(({ code, label, name, welcome, action }) => (
          <button type="button" lang={code} key={code} onClick={() => chooseLanguage(code)}>
            <span className="welcome-language-code">{label}</span><strong>{name}</strong><span>{welcome}</span><span className="welcome-language-action">{action}<ArrowUpRight size={18} aria-hidden="true" /></span>
          </button>
        ))}
      </div>
      <p className="welcome-language-footnote"><span lang="cs">Jazyk můžete kdykoliv změnit.</span><span lang="en">You can change it anytime.</span><span lang="de">Du kannst die Sprache jederzeit ändern.</span></p>
    </main>
  );

  const preview = copy.previews[selected];
  const image = images[selected];
  return (
    <div className="welcome theme-clay" id="nahoru" style={CLAY_STYLE}>
      <a className="welcome-skip" href="#obsah">{copy.skip}</a>
      <header className="welcome-header"><div className="welcome-nav welcome-container">
        <a className="welcome-logo" href="#nahoru" aria-label={copy.home}><Brand><span className="welcome-beta">{copy.badge}</span></Brand></a>
        <nav aria-label={copy.navigation}><a href="#funkce">{copy.nav[0]}</a><a href="#ukazky">{copy.nav[1]}</a><a href="#otazky">{copy.nav[2]} <ArrowUpRight size={14} /></a></nav>
        <SegmentedControl
          className="welcome-language-switch"
          aria-label={copy.language}
          value={language}
          onChange={chooseLanguage}
          options={LANGUAGES.map(({ code, label, name }) => ({ value: code, label: <span lang={code}>{label}</span>, title: name }))}
        />
      </div></header>
      <main id="obsah">
        <section className="welcome-hero welcome-container" aria-labelledby="welcome-title">
          <div className="welcome-eyebrow"><span />{copy.eyebrow}</div>
          <h1 id="welcome-title" ref={headingRef} tabIndex={-1}><Heading lines={copy.heading} /></h1>
          <p className="welcome-lead">{copy.lead[0]}<br className="welcome-desktop-break" /> {copy.lead[1]}</p>
          <div className="welcome-hero-actions"><a className="welcome-cta" href="/demo" onClick={handleDemoCtaClick("landing_hero")}>{copy.demoCta} <ArrowUpRight size={17} /></a><a className="welcome-preview-link" href="#ukazky">{copy.cta} <ArrowDown size={17} /></a></div>
          <p className="welcome-hero-note">{copy.heroNote}</p>
          <div className="welcome-hero-visual">
            <div className="welcome-orbit welcome-orbit-one" /><div className="welcome-orbit welcome-orbit-two" />
            <div className="welcome-window">
              <div className="welcome-window-bar"><span className="welcome-window-dots"><i /><i /><i /></span><span>{copy.window}</span><span className="welcome-window-status">● &nbsp; {copy.previewBadge}</span></div>
              <img src={screenshotPath("performance")} alt={copy.heroAlt} width="1004" height="455" fetchPriority="high" />
            </div>
            <div className="welcome-float"><span className="welcome-float-icon"><Check size={20} /></span><div>{copy.float[0]}<small>{copy.float[1]}</small></div></div>
          </div>
          <p className="welcome-caption">{copy.caption}</p>
        </section>
        <div className="welcome-ribbon"><div className="welcome-container"><span>{copy.ribbon}</span><span>{copy.assets}</span><i /><span>Trading 212</span><i /><span>{copy.moreBrokers}</span><i /><span>{copy.import}</span></div></div>
        <section className="welcome-features welcome-container" id="funkce" aria-labelledby="features-title">
          <div className="welcome-section-heading"><div><p className="welcome-kicker">{copy.featuresKicker}</p><h2 id="features-title"><Heading lines={copy.featuresHeading} /></h2></div><p>{copy.featuresLead}</p></div>
          <div className="welcome-feature-grid">
            {copy.features.map(([title, description], index) => {
              const Icon = icons[index];
              return <article className="welcome-feature" key={index}><div className="welcome-feature-top"><Icon size={24} strokeWidth={1.5} /><span>0{index + 1}</span></div><h3>{title}</h3><p>{description}</p></article>;
            })}
          </div>
        </section>
        <section className="welcome-showcase" id="ukazky" aria-labelledby="showcase-title">
          <div className="welcome-container">
            <div className="welcome-showcase-top"><p className="welcome-kicker">{copy.showcaseKicker}</p><span>{copy.showcaseNote}</span></div>
            <div className="welcome-showcase-grid">
              <div className="welcome-showcase-copy">
                <SegmentedControl
                  className="welcome-preview-switch"
                  aria-label={copy.selectPreview}
                  value={selected}
                  onChange={setSelected}
                  options={copy.previews.map((item, index) => ({ value: index, label: item.label }))}
                />
                <h2 id="showcase-title">{preview.title}</h2><p>{preview.description}</p>
                <div className="welcome-detail-note"><Layers3 size={18} /><span>{copy.detailNote}</span></div>
              </div>
              <figure className="welcome-detail-preview"><div className={`welcome-detail-image welcome-detail-image-${image}`}><img src={screenshotPath(image)} alt={preview.alt} width={imageSizes[selected][0]} height={imageSizes[selected][1]} loading="lazy" /></div><figcaption>{copy.imageCaption}</figcaption></figure>
            </div>
          </div>
        </section>
        <section className="welcome-faq welcome-container" id="otazky" aria-labelledby="faq-title">
          <div><p className="welcome-kicker">{copy.faqKicker}</p><h2 id="faq-title"><Heading lines={copy.faqHeading} /></h2></div>
          <div className="welcome-questions">
            {copy.questions.map(([question, answer], index) => <details key={index}><summary>{question}<span className="welcome-faq-icon" aria-hidden="true"><Plus size={18} /></span></summary><p>{answer}</p></details>)}
          </div>
        </section>
        <section className="welcome-closing welcome-container"><div className="welcome-eyebrow"><span />{copy.closingKicker}</div><h2><Heading lines={copy.closingHeading} /></h2><p>{copy.closingNote}</p><div className="welcome-closing-actions"><a className="welcome-cta" href="/demo" onClick={handleDemoCtaClick("landing_closing")}>{copy.demoCta} <ArrowUpRight size={17} /></a><a href="#nahoru">{copy.back} <ArrowUpRight size={16} /></a></div></section>
      </main>
      <footer className="welcome-footer welcome-container"><a className="welcome-logo" href="#nahoru"><Brand /></a><span>{copy.footer}</span><AnalyticsPreferencesLink /><small>© {new Date().getFullYear()} Portfyl</small></footer>
    </div>
  );
}
