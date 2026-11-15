import { LANGUAGES } from "../../pages/welcomeCopy";
import { LANDING_PATHS } from "../../lib/routes";
import { APP_ORIGIN, registerUrl } from "../../lib/signupIntent";
import Brand from "./Brand";
import { rememberLanguage } from "./languagePrefs";

// The in-page targets, in header order. `anchorBase` is "" on the landing
// itself; another public page (the legal pages) passes the landing's path so
// the same links lead back to the sections.
export const NAV_TARGETS = ["funkce", "brokeri", "cenik", "otazky"];

// Sticky 64px header: logo, four section links, language links, Log in and
// one primary button. Below 860px only the logo, the button and a <details>
// menu remain (no JavaScript needed, so it works in the prerendered HTML).
export default function LandingHeader({ copy, language, signupOpen, onDemo, anchorBase = "" }) {
  const target = (id) => `${anchorBase}#${id}`;
  const closeMenu = (event) => event.currentTarget.closest("details")?.removeAttribute("open");
  const others = LANGUAGES.filter(({ code }) => code !== language);
  return (
    <header className="welcome-header">
      <div className="welcome-nav welcome-container">
        <a className="welcome-logo" href={target("nahoru")} aria-label={copy.home}><Brand /></a>
        <nav className="welcome-links" aria-label={copy.navigation}>
          {NAV_TARGETS.map((id, index) => <a key={id} href={target(id)}>{copy.nav[index]}</a>)}
        </nav>
        <div className="welcome-lang" role="group" aria-label={copy.language}>
          {LANGUAGES.map(({ code, label, name }) => (
            <a
              key={code} href={LANDING_PATHS[code]} hrefLang={code} lang={code} title={name}
              aria-current={code === language ? "page" : undefined} onClick={() => rememberLanguage(code)}
            >{label}</a>
          ))}
        </div>
        <a className="welcome-login" href={`${APP_ORIGIN}/login`}>{copy.login}</a>
        {signupOpen
          ? <a className="welcome-btn" href={registerUrl({ source: "landing_hero", lang: language })}>{copy.trialCtaShort}</a>
          : <a className="welcome-btn" href="/demo" onClick={onDemo}>{copy.demoCtaShort}</a>}
        <details className="welcome-menu">
          <summary>{copy.menu}</summary>
          <nav aria-label={copy.menuNavigation}>
            {NAV_TARGETS.map((id, index) => <a key={id} href={target(id)} onClick={closeMenu}>{copy.nav[index]}</a>)}
            <hr />
            <a href={`${APP_ORIGIN}/login`}>{copy.login}</a>
            <span className="welcome-menu-langs">
              {others.map(({ code, name }) => (
                <a key={code} href={LANDING_PATHS[code]} hrefLang={code} lang={code} onClick={() => rememberLanguage(code)}>{name}</a>
              ))}
            </span>
          </nav>
        </details>
      </div>
    </header>
  );
}
