import { Fragment, useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import termsCs from "../../../docs/legal/podminky-uzivani-cs.md?raw";
import termsEn from "../../../docs/legal/terms-of-service-en.md?raw";
import privacyCs from "../../../docs/legal/zasady-ochrany-osobnich-udaju-cs.md?raw";
import privacyEn from "../../../docs/legal/privacy-policy-en.md?raw";
import { LANGUAGE_KEY } from "./welcomeCopy";
import { useAnalytics } from "../analytics/AnalyticsProvider";
import { ANALYTICS_COPY } from "../analytics/analyticsCopy";
import SegmentedControl from "../components/ui/SegmentedControl";
import { CLAY_STYLE } from "../lib/clayStyle";
import { splitLegalDocument } from "../lib/legalMarkdown";
import "./Welcome.css";
import "./Legal.css";
import "../fonts.css";

// Public /terms and /privacy (cloud edition). The text is read at build time
// from docs/legal/, the single source the lawyer reviews, so the page cannot
// drift from it. The Dockerfile copies docs/legal/ into the frontend build
// stage for these imports.
const SOURCES = {
  terms: { cs: termsCs, en: termsEn },
  privacy: { cs: privacyCs, en: privacyEn },
};

export const LEGAL_LANGUAGES = ["cs", "en"];

const COPY = {
  cs: {
    terms: "Obchodní podmínky",
    privacy: "Ochrana osobních údajů",
    navigation: "Právní dokumenty",
    language: "Jazyk stránky",
    skip: "Přejít na obsah",
    home: "Portfyl — úvod",
    back: "Zpět na úvod",
    contents: "Obsah",
    draftTitle: "Pracovní verze.",
    draft: "Text ještě kontroluje advokát. Žlutě označená místa se před zveřejněním doplní.",
    pending: "Doplní se",
    questions: "Dotazy k těmto dokumentům posílejte na",
  },
  en: {
    terms: "Terms of Service",
    privacy: "Privacy Policy",
    navigation: "Legal documents",
    language: "Page language",
    skip: "Skip to content",
    home: "Portfyl — home",
    back: "Back to home",
    contents: "Contents",
    draftTitle: "Working draft.",
    draft: "This text is still being reviewed by a lawyer. Highlighted items will be completed before publication.",
    pending: "To be completed",
    questions: "Send questions about these documents to",
  },
};

// ?lang= wins (links from the app and from Stripe can pin it), then the
// landing page's saved choice (German readers get English), then the browser.
export function initialLegalLanguage() {
  const requested = new URLSearchParams(window.location.search).get("lang");
  if (LEGAL_LANGUAGES.includes(requested)) return requested;
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved) return saved === "cs" ? "cs" : "en";
  } catch { /* Storage may be unavailable. */ }
  const browser = (navigator.language || "").toLowerCase();
  return browser.startsWith("cs") || browser.startsWith("sk") ? "cs" : "en";
}

const plainText = (nodes) => nodes.map((node) => (node.children ? plainText(node.children) : node.value || "")).join("");

function Inline({ nodes, t }) {
  return nodes.map((node, index) => {
    switch (node.type) {
      case "text": return <Fragment key={index}>{node.value}</Fragment>;
      case "break": return <br key={index} />;
      case "strong": return <strong key={index}><Inline nodes={node.children} t={t} /></strong>;
      case "em": return <em key={index}><Inline nodes={node.children} t={t} /></em>;
      case "code": return <code key={index}>{node.value}</code>;
      case "span": return <Fragment key={index}><Inline nodes={node.children} t={t} /></Fragment>;
      case "pending": {
        // The badge already says "to be completed"; drop the marker's own
        // TODO/DOPLNIT keyword but keep LAWYER/DECIDE-style notes as written.
        const detail = node.value.replace(/^(TODO|DOPLNIT)\s*:?\s*/i, "");
        return <mark key={index} className="legal-pending"><span className="legal-pending-label">{t.pending}</span>{detail && ` ${detail}`}</mark>;
      }
      case "link": {
        const external = /^https?:/.test(node.href);
        return <a key={index} href={node.href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}><Inline nodes={node.children} t={t} /></a>;
      }
      default: return null;
    }
  });
}

function Block({ block, t }) {
  switch (block.type) {
    case "heading": {
      const Tag = block.level === 2 ? "h2" : "h3";
      return <Tag id={block.id}><Inline nodes={block.children} t={t} /></Tag>;
    }
    case "quote": return <blockquote><Inline nodes={block.children} t={t} /></blockquote>;
    case "list": return <ul>{block.items.map((item, index) => <li key={index}><Inline nodes={item} t={t} /></li>)}</ul>;
    case "table": {
      const labels = block.header.map(plainText);
      return (
        <div className="legal-table">
          <table>
            <thead><tr>{block.header.map((cell, index) => <th key={index} scope="col"><Inline nodes={cell} t={t} /></th>)}</tr></thead>
            <tbody>{block.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>{row.map((cell, index) => <td key={index} data-label={labels[index]}><Inline nodes={cell} t={t} /></td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      );
    }
    default: {
      const onlyPending = block.children.length === 1 && block.children[0].type === "pending";
      return <p className={onlyPending ? "legal-pending-block" : undefined}><Inline nodes={block.children} t={t} /></p>;
    }
  }
}

function Brand() {
  return <><img src="/portfyl-mark.svg" alt="" width="38" height="38" />Portfyl</>;
}

function AnalyticsPreferencesLink({ language }) {
  const { reopenAnalyticsPreferences } = useAnalytics();
  return (
    <button type="button" onClick={reopenAnalyticsPreferences} className="welcome-preview-link" style={{ background: "none", border: "none", cursor: "pointer" }}>
      {ANALYTICS_COPY[language].manage}
    </button>
  );
}

function Contents({ sections }) {
  return <ol>{sections.map(({ id, text }) => <li key={id}><a href={`#${id}`}>{text}</a></li>)}</ol>;
}

export default function Legal({ page }) {
  const [language, setLanguage] = useState(initialLegalLanguage);
  const t = COPY[language];
  const doc = useMemo(() => splitLegalDocument(SOURCES[page][language]), [page, language]);

  useEffect(() => {
    const previousTitle = document.title;
    const previousLanguage = document.documentElement.lang;
    document.title = `${doc.title} — Portfyl`;
    document.documentElement.lang = language;
    return () => { document.title = previousTitle; document.documentElement.lang = previousLanguage; };
  }, [doc.title, language]);

  function chooseLanguage(code) {
    setLanguage(code);
    const url = new URL(window.location.href);
    url.searchParams.set("lang", code);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
  }

  const docLink = (target) => `/${target}?lang=${language}`;
  return (
    <div className="welcome theme-clay legal" style={CLAY_STYLE}>
      <a className="welcome-skip" href="#obsah">{t.skip}</a>
      <header className="welcome-header"><div className="welcome-nav welcome-container">
        <a className="welcome-logo" href="/" aria-label={t.home}><Brand /></a>
        <nav aria-label={t.navigation}>
          {["terms", "privacy"].map((target) => (
            <a key={target} href={docLink(target)} aria-current={target === page ? "page" : undefined}>{t[target]}</a>
          ))}
        </nav>
        <SegmentedControl
          className="welcome-language-switch"
          aria-label={t.language}
          value={language}
          onChange={chooseLanguage}
          options={LEGAL_LANGUAGES.map((code) => ({ value: code, label: <span lang={code}>{code === "cs" ? "CZ" : "EN"}</span>, title: code === "cs" ? "Čeština" : "English" }))}
        />
      </div></header>
      <div className="legal-layout welcome-container">
        <aside className="legal-toc legal-toc-aside" aria-labelledby="legal-toc-title">
          <p id="legal-toc-title" className="welcome-kicker">{t.contents}</p>
          <Contents sections={doc.sections} />
        </aside>
        <main id="obsah" className="legal-card" lang={language}>
          <a className="legal-back" href="/"><ArrowLeft size={16} aria-hidden="true" />{t.back}</a>
          <h1>{doc.title}</h1>
          {doc.pendingCount > 0 && (
            <div className="legal-draft" role="note"><strong>{t.draftTitle}</strong> {t.draft}</div>
          )}
          <details className="legal-toc legal-toc-mobile">
            <summary>{t.contents}</summary>
            <Contents sections={doc.sections} />
          </details>
          <article className="legal-body">
            {doc.blocks.map((block, index) => <Block key={index} block={block} t={t} />)}
          </article>
          <p className="legal-contact">{t.questions} <a href="mailto:support@portfyl.com">support@portfyl.com</a>.</p>
        </main>
      </div>
      <footer className="welcome-footer welcome-container">
        <a className="welcome-logo" href="/"><Brand /></a>
        <nav className="legal-footer-links" aria-label={t.navigation}>
          <a href={docLink("terms")}>{t.terms}</a>
          <a href={docLink("privacy")}>{t.privacy}</a>
        </nav>
        <AnalyticsPreferencesLink language={language} />
        <small>© {new Date().getFullYear()} Portfyl</small>
      </footer>
    </div>
  );
}
