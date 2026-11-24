import { LANGUAGES } from "../../pages/welcomeCopy";
import { LANDING_PATHS } from "../../lib/routes";
import { useAnalytics } from "../../analytics/AnalyticsProvider";
import { ANALYTICS_COPY } from "../../analytics/analyticsCopy";
import Brand from "./Brand";
import { NAV_TARGETS } from "./LandingHeader";
import { rememberLanguage } from "./languagePrefs";

function AnalyticsPreferencesLink({ language }) {
  const { reopenAnalyticsPreferences } = useAnalytics();
  return <button type="button" className="welcome-preview-link" onClick={reopenAnalyticsPreferences}>{ANALYTICS_COPY[language].manage}</button>;
}

// Four columns: about, product, legal, contact. `anchorBase` works as in
// LandingHeader.
export default function LandingFooter({ copy, language, anchorBase = "", languagePaths = LANDING_PATHS }) {
  const others = LANGUAGES.filter(({ code }) => code !== language);
  return (
    <footer className="welcome-footer">
      <div className="welcome-container welcome-footer-grid">
        <div className="welcome-footer-about">
          <a className="welcome-logo" href={`${anchorBase}#nahoru`}><Brand /></a>
          <p>{copy.footer.tagline}</p>
          <p><small suppressHydrationWarning>© {new Date().getFullYear()} Portfyl</small></p>
        </div>
        <div>
          <h3>{copy.footer.product}</h3>
          <ul>
            {NAV_TARGETS.slice(0, 3).map((id, index) => <li key={id}><a href={`${anchorBase}#${id}`}>{copy.nav[index]}</a></li>)}
            <li><a href={`${anchorBase}#funkce`}>{copy.footer.examples}</a></li>
          </ul>
        </div>
        <div>
          <h3>{copy.footer.legal}</h3>
          <nav aria-label={copy.legalNavigation}>
            <ul>{copy.legal.map(([page, label]) => <li key={page}><a href={`/${page}?lang=${copy.legalLanguage}`}>{label}</a></li>)}</ul>
          </nav>
          <ul><li><AnalyticsPreferencesLink language={language} /></li></ul>
        </div>
        <div>
          <h3>{copy.footer.contact}</h3>
          <ul>
            <li><a href="mailto:support@portfyl.com">support@portfyl.com</a></li>
            <li>
              {others.map(({ code, name }, index) => (
                <span key={code}>{index > 0 && " · "}<a href={languagePaths[code]} hrefLang={code} lang={code} onClick={() => rememberLanguage(code)}>{name}</a></span>
              ))}
            </li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
