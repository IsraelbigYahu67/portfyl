import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUpRight, ChartNoAxesCombined, PieChart, CalendarDays, Layers3, Check, Plus } from "lucide-react";
import { COPY, LANGUAGES, LANGUAGE_KEY } from "./welcomeCopy";
import "./Welcome.css";
import "../fonts.css";

const images = ["allocation", "stock", "dashboard", "performance"];
const imageSizes = [[1047, 365], [1047, 350], [1047, 345], [1004, 455]];
const screenshotPath = (name) => `/landing/${name}-live-20260911.png`;
const icons = [ChartNoAxesCombined, PieChart, CalendarDays];

function savedLanguage() {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    return LANGUAGES.some(({ code }) => code === saved) ? saved : null;
  } catch { return null; }
}

function Brand({ children }) {
  return <><img src="/portfyl-mark.png" alt="" width="38" height="38" />Portfyl{children}</>;
}

function Heading({ lines }) {
  return <>{lines[0]}<br /><span>{lines[1]}</span></>;
}

export default function Welcome() {
  const [language, setLanguage] = useState(savedLanguage);
  const [selected, setSelected] = useState(0);
  const headingRef = useRef(null);
  const focusHeading = useRef(false);
  const copy = language ? COPY[language] : null;

  useEffect(() => {
    const previousTitle = document.title;
    const previousLanguage = document.documentElement.lang;
    document.title = copy?.title || "Portfyl — CZ / EN / DE";
    document.documentElement.lang = language || "en";
    return () => { document.title = previousTitle; document.documentElement.lang = previousLanguage; };
  }, [language, copy]);

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
    <main className="welcome welcome-language-screen">
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
    <div className="welcome" id="nahoru">
      <a className="welcome-skip" href="#obsah">{copy.skip}</a>
      <header className="welcome-header"><div className="welcome-nav welcome-container">
        <a className="welcome-logo" href="#nahoru" aria-label={copy.home}><Brand><span className="welcome-beta">{copy.badge}</span></Brand></a>
        <nav aria-label={copy.navigation}><a href="#funkce">{copy.nav[0]}</a><a href="#ukazky">{copy.nav[1]}</a><a href="#otazky">{copy.nav[2]} <ArrowUpRight size={14} /></a></nav>
        <div className="welcome-language-switch" role="group" aria-label={copy.language}>
          {LANGUAGES.map(({ code, label, name }) => <button type="button" key={code} lang={code} aria-label={name} aria-pressed={language === code} onClick={() => chooseLanguage(code)}>{label}</button>)}
        </div>
      </div></header>
      <main id="obsah">
        <section className="welcome-hero welcome-container" aria-labelledby="welcome-title">
          <div className="welcome-eyebrow"><span />{copy.eyebrow}</div>
          <h1 id="welcome-title" ref={headingRef} tabIndex={-1}><Heading lines={copy.heading} /></h1>
          <p className="welcome-lead">{copy.lead[0]}<br className="welcome-desktop-break" /> {copy.lead[1]}</p>
          <div className="welcome-hero-actions"><a className="welcome-cta" href="/demo">{copy.demoCta} <ArrowUpRight size={17} /></a><a className="welcome-preview-link" href="#ukazky">{copy.cta} <ArrowDown size={17} /></a></div>
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
                <div className="welcome-preview-switch" role="group" aria-label={copy.selectPreview}>{copy.previews.map((item, index) => <button key={images[index]} type="button" aria-pressed={selected === index} onClick={() => setSelected(index)}>{item.label}</button>)}</div>
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
            {copy.questions.map(([question, answer], index) => <details key={index}><summary>{question}<Plus size={18} /></summary><p>{answer}</p></details>)}
          </div>
        </section>
        <section className="welcome-closing welcome-container"><div className="welcome-eyebrow"><span />{copy.closingKicker}</div><h2><Heading lines={copy.closingHeading} /></h2><p>{copy.closingNote}</p><div className="welcome-closing-actions"><a className="welcome-cta" href="/demo">{copy.demoCta} <ArrowUpRight size={17} /></a><a href="#nahoru">{copy.back} <ArrowUpRight size={16} /></a></div></section>
      </main>
      <footer className="welcome-footer welcome-container"><a className="welcome-logo" href="#nahoru"><Brand /></a><span>{copy.footer}</span><small>© {new Date().getFullYear()} Portfyl</small></footer>
    </div>
  );
}
