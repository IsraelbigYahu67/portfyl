import { useEffect, useId, useRef, useState } from "react";
import { ANALYTICS_EVENTS } from "../../analytics/eventContract";
import { useOptionalAnalytics } from "../../analytics/AnalyticsProvider";
import { filterBrokers } from "../../lib/onboardingBrokers";
import { registerUrl } from "../../lib/signupIntent";

const MAX_TYPED = 60;
const ANALYTICS_LANGUAGES = ["cs", "en", "de"];

// Whitespace collapsed and length capped: the text is only ever rendered as
// a text node, but the sentence it lands in should stay readable.
const tidy = (text) => text.replace(/\s+/g, " ").trim().slice(0, MAX_TYPED);

// What the visitor's text means: nothing yet, a supported broker, or one we
// cannot read. Several partial matches stay undecided until they pick a chip.
function resolve(query, language) {
  const typed = tidy(query);
  if (!typed) return { typed, matches: [], result: null };
  const { supported, unsupported } = filterBrokers(typed, language);
  const same = (name) => name.toLowerCase() === typed.toLowerCase();
  const exact = supported.find((broker) => same(broker.name));
  if (exact) return { typed, matches: supported, result: { kind: "supported", broker: exact } };
  if (unsupported.some(same)) return { typed, matches: supported, result: { kind: "unsupported" } };
  if (supported.length === 1 && unsupported.length === 0) {
    return { typed, matches: supported, result: { kind: "supported", broker: supported[0] } };
  }
  if (supported.length === 0) return { typed, matches: supported, result: { kind: "unsupported" } };
  return { typed, matches: supported, result: null };
}

// "Is your broker supported?" on the public landing page. Renders the same
// markup on the server and the client: all state starts empty, and nothing
// here touches window or storage.
export default function BrokerCheck({ copy, language, signupOpen = import.meta.env.VITE_PUBLIC_SIGNUP === "true" }) {
  const [query, setQuery] = useState("");
  const titleId = useId();
  const { typed, matches, result } = resolve(query, language);
  const selectedKey = result?.kind === "supported" ? result.broker.key : null;
  const analytics = useOptionalAnalytics();
  const capture = analytics?.capture;
  const lastReported = useRef(null);
  // One event per distinct result, from an effect: nothing is sent while
  // typing a half-matching name, and nothing runs during render, so the
  // server and client HTML stay identical. Only the result kind and the
  // landing language are sent, never the typed text.
  const resultKind = result?.kind ?? null;
  useEffect(() => {
    if (!resultKind || !capture || !ANALYTICS_LANGUAGES.includes(language)) return;
    const identity = resultKind === "supported" ? `supported:${selectedKey}` : "unsupported";
    if (lastReported.current === identity) return;
    lastReported.current = identity;
    capture(ANALYTICS_EVENTS.BROKER_CHECK_USED, { result: resultKind, language });
  }, [resultKind, selectedKey, language, capture]);
  // The examples sit under the features, on the same page.
  const examplesLink = (className) => (
    <a className={className} href="#funkce">{copy.examples}</a>
  );

  return (
    <div className="welcome-broker-check" role="group" aria-labelledby={titleId}>
      <div className="welcome-broker-panel">
        <p id={titleId} className="welcome-broker-title">{copy.title}</p>
        <input
          type="search" className="welcome-broker-input" value={query} placeholder={copy.placeholder}
          aria-labelledby={titleId} autoComplete="off" spellCheck={false} maxLength={MAX_TYPED * 2}
          onChange={(event) => setQuery(event.target.value)}
        />
        {matches.length > 0 && (
          <ul className="welcome-broker-chips">
            {matches.map((broker) => (
              <li key={broker.key}>
                <button type="button" aria-pressed={broker.key === selectedKey} onClick={() => setQuery(broker.name)}>
                  <img src={broker.icon} alt="" width="24" height="24" />{broker.name}
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="welcome-broker-live" aria-live="polite">
          {result?.kind === "supported" && (
            <div className="broker-check-result welcome-broker-result">
              <p>{copy.supported.replace("{name}", result.broker.name)}</p>
              {signupOpen ? (
                <div className="welcome-broker-actions">
                  <a className="welcome-btn" href={registerUrl({ source: "landing_broker_check", broker: result.broker.key, lang: language })}>{copy.signup}</a>
                  {examplesLink("welcome-textlink")}
                </div>
              ) : (
                <>
                  <div className="welcome-broker-actions">{examplesLink("welcome-btn")}</div>
                  <small>{copy.betaNote}</small>
                </>
              )}
            </div>
          )}
          {result?.kind === "unsupported" && (
            <div className="broker-check-result welcome-broker-result">
              <p>{copy.unsupported.replace("{name}", typed)}</p>
              <div className="welcome-broker-actions">{examplesLink("welcome-btn")}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
