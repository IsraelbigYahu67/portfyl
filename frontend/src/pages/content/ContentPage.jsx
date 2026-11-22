import { useEffect } from "react";
import { ArrowLeft } from "lucide-react";
import { COPY as LANDING_COPY } from "../welcomeCopy";
import LandingHeader from "../../components/landing/LandingHeader";
import LandingFooter from "../../components/landing/LandingFooter";
import { CLAY_STYLE } from "../../lib/clayStyle";
import { LANDING_PATHS } from "../../lib/routes";
import { registerUrl } from "../../lib/signupIntent";
import "../Welcome.css";
import "./ContentPage.css";
import "../../fonts.css";

// The chrome every content page shares, in the page's own language. The
// article text (children) never repeats any of it.
const COPY = {
  cs: {
    back: "Zpět na úvod",
    updated: "Aktualizováno",
    months: null,
    note: "Nejde o investiční poradenství.",
    noteText: "Text je obecná informace, nezohledňuje vaši situaci a nic v něm není doporučením ke koupi nebo prodeji.",
    ctaTitle: "Vyzkoušejte Portfyl",
    ctaText: "Výkonnost, rozložení a dividendy akcií a ETF na jednom místě.",
  },
  en: {
    back: "Back to home",
    updated: "Updated",
    months: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    note: "Not investment advice.",
    noteText: "This text is general information, does not take your situation into account, and nothing in it is a recommendation to buy or sell.",
    ctaTitle: "Try Portfyl",
    ctaText: "Performance, allocation and dividends of your stocks and ETFs in one place.",
  },
  de: {
    back: "Zurück zur Startseite",
    updated: "Aktualisiert",
    months: ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"],
    note: "Keine Anlageberatung.",
    noteText: "Dieser Text ist eine allgemeine Information, berücksichtigt deine Situation nicht, und nichts darin ist eine Kauf- oder Verkaufsempfehlung.",
    ctaTitle: "Portfyl ausprobieren",
    ctaText: "Performance, Aufteilung und Dividenden deiner Aktien und ETFs an einem Ort.",
  },
};

// "2026-11-22" as "22. 11. 2026" (Czech), "22 November 2026" (English) or
// "22. November 2026" (German). Written by hand, not with Intl, so the server
// render and the browser always produce the same text.
export function formatUpdated(lastmod, language) {
  const [year, month, day] = lastmod.split("-").map(Number);
  const { months } = COPY[language];
  if (language === "cs") return `${day}. ${month}. ${year}`;
  return language === "en" ? `${day} ${months[month - 1]} ${year}` : `${day}. ${months[month - 1]} ${year}`;
}

// The landing's own header and footer around one article column: one <h1>,
// readable body text, a "not investment advice" note, and a call to action
// that matches the landing's (the trial when sign-up is open, else the
// examples). `languagePaths` sends the language links to this page's sibling
// versions where they exist (see seo/contentPages.js languagePathsFor).
export default function ContentPage({ page, languagePaths = LANDING_PATHS, signupOpen = import.meta.env.VITE_PUBLIC_SIGNUP === "true", children }) {
  const { language } = page;
  const t = COPY[language];
  const landing = LANDING_COPY[language];
  const landingPath = LANDING_PATHS[language];

  useEffect(() => {
    const previousTitle = document.title;
    const previousLanguage = document.documentElement.lang;
    document.title = page.title;
    document.documentElement.lang = language;
    return () => { document.title = previousTitle; document.documentElement.lang = previousLanguage; };
  }, [page.title, language]);

  return (
    <div className="welcome theme-clay content-page" id="nahoru" style={CLAY_STYLE}>
      <a className="welcome-skip" href="#obsah">{landing.skip}</a>
      <LandingHeader copy={landing} language={language} signupOpen={signupOpen} anchorBase={landingPath} languagePaths={languagePaths} />
      <main id="obsah" className="content-main welcome-container" lang={language}>
        <a className="content-back" href={landingPath}><ArrowLeft size={16} aria-hidden="true" />{t.back}</a>
        <article className="content-article">
          <h1>{page.heading}</h1>
          <p className="content-updated">{t.updated} <time dateTime={page.lastmod}>{formatUpdated(page.lastmod, language)}</time></p>
          <div className="content-body">{children}</div>
          {page.adviceNote && (
            <aside className="content-note" role="note"><strong>{t.note}</strong> {t.noteText}</aside>
          )}
        </article>
        <section className="content-cta" aria-labelledby="content-cta-title">
          <div>
            <h2 id="content-cta-title">{t.ctaTitle}</h2>
            <p className="welcome-muted">{t.ctaText}</p>
          </div>
          {signupOpen
            ? <a className="welcome-btn welcome-btn-big" href={registerUrl({ source: "content_page", lang: language })}>{landing.trialCtaShort}</a>
            : <a className="welcome-btn welcome-btn-big" href={`${landingPath}#funkce`}>{landing.examplesCta}</a>}
        </section>
      </main>
      <LandingFooter copy={landing} language={language} anchorBase={landingPath} languagePaths={languagePaths} />
    </div>
  );
}
