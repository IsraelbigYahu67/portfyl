import { registerUrl } from "../../lib/signupIntent";
import { LANDING_IMAGES } from "./landingImages";
import Shot from "./Shot";

// Hero. While signup is closed (VITE_PUBLIC_SIGNUP unset) the one call to action
// scrolls to the live examples under the features, a status line says why, and
// nothing links to /register. While it is open the trial button leads and a text
// link scrolls to the same examples.
export default function LandingHero({ copy, language, signupOpen }) {
  return (
    <section className="welcome-hero welcome-container" aria-labelledby="welcome-title">
      <div className="welcome-hero-text">
        {!signupOpen && <p className="welcome-status"><b>{copy.status[0]}</b> {copy.status[1]}</p>}
        <h1 id="welcome-title">{copy.heading}</h1>
        <p className="welcome-lead">{copy.lead}</p>
        {signupOpen ? (
          <>
            <div className="welcome-cta-row">
              <a className="welcome-btn welcome-btn-big" href={registerUrl({ source: "landing_hero", lang: language })}>{copy.trialCta}</a>
              <a className="welcome-textlink" href="#funkce">{copy.examplesCta}</a>
            </div>
            <p className="welcome-note">{copy.trialNote}</p>
          </>
        ) : (
          <div className="welcome-cta-row">
            <a className="welcome-btn welcome-btn-big" href="#funkce">{copy.examplesCta}</a>
            <span className="welcome-note">{copy.examplesNote}</span>
          </div>
        )}
      </div>
      <Shot image={LANDING_IMAGES.hero} alt={copy.heroAlt} eager />
      <p className="welcome-caption">{copy.caption}</p>
    </section>
  );
}
