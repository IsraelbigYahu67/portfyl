import { Fragment, useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import termsCs from "../../../docs/legal/podminky-uzivani-cs.md?raw";
import termsEn from "../../../docs/legal/terms-of-service-en.md?raw";
import privacyCs from "../../../docs/legal/zasady-ochrany-osobnich-udaju-cs.md?raw";
import privacyEn from "../../../docs/legal/privacy-policy-en.md?raw";
import { COPY as LANDING_COPY, LANGUAGE_KEY } from "./welcomeCopy";
import LandingHeader from "../components/landing/LandingHeader";
import LandingFooter from "../components/landing/LandingFooter";
import SegmentedControl from "../components/ui/SegmentedControl";
import { CLAY_STYLE } from "../lib/clayStyle";
import { splitLegalDocument } from "../lib/legalMarkdown";
import { LANDING_PATHS } from "../lib/routes";
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

function Contents({ sections }) {
  return <ol>{sections.map(({ id, text }) => <li key={id}><a href={`#${id}`}>{text}</a></li>)}</ol>;
}

// The landing's own header and footer (the section links lead back to the
// landing page in the same language) around one flat text column.
export default function Legal({ page, signupOpen = import.meta.env.VITE_PUBLIC_SIGNUP === "true" }) {
  const [language, setLanguage] = useState(initialLegalLanguage);
  const t = COPY[language];
  const landing = LANDING_COPY[language];
  const anchorBase = LANDING_PATHS[language];
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
    <div className="welcome theme-clay legal" id="nahoru" style={CLAY_STYLE}>
      <a className="welcome-skip" href="#obsah">{t.skip}</a>
      <LandingHeader copy={landing} language={language} signupOpen={signupOpen} anchorBase={anchorBase} />
      <main id="obsah" className="legal-text welcome-container" lang={language}>
        <div className="legal-tools">
          <a className="legal-back" href={anchorBase}><ArrowLeft size={16} aria-hidden="true" />{t.back}</a>
          <nav className="legal-doc-links" aria-label={t.navigation}>
            {["terms", "privacy"].map((target) => (
              <a key={target} href={docLink(target)} aria-current={target === page ? "page" : undefined}>{t[target]}</a>
            ))}
          </nav>
          <SegmentedControl
            className="welcome-language-switch"
            aria-label={t.language}
            value={language}
            onChange={chooseLanguage}
            options={LEGAL_LANGUAGES.map((code) => ({ value: code, label: <span lang={code}>{code === "cs" ? "CZ" : "EN"}</span>, title: code === "cs" ? "CZ – Čeština" : "EN – English" }))}
          />
        </div>
        <h1>{doc.title}</h1>
        {doc.pendingCount > 0 && (
          <div className="legal-draft" role="note"><strong>{t.draftTitle}</strong> {t.draft}</div>
        )}
        <details className="legal-toc">
          <summary>{t.contents}</summary>
          <Contents sections={doc.sections} />
        </details>
        <article className="legal-body">
          {doc.blocks.map((block, index) => <Block key={index} block={block} t={t} />)}
        </article>
        <p className="legal-contact">{t.questions} <a href="mailto:support@portfyl.com">support@portfyl.com</a>.</p>
      </main>
      <LandingFooter copy={landing} language={language} anchorBase={anchorBase} />
    </div>
  );
}