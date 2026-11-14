import { useId, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { filterBrokers } from "../../lib/onboardingBrokers";
import { registerUrl } from "../../lib/signupIntent";

const MAX_TYPED = 60;

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
export default function BrokerCheck({ copy, language, signupOpen = import.meta.env.VITE_PUBLIC_SIGNUP === "true", onDemo }) {
  const [query, setQuery] = useState("");
  const titleId = useId();
  const { typed, matches, result } = resolve(query, language);
  const selectedKey = result?.kind === "supported" ? result.broker.key : null;
  const demoLink = (className) => (
    <a className={className} href="/demo" onClick={onDemo}>{copy.demo} <ArrowUpRight size={16} aria-hidden="true" /></a>
  );

  return (
    <section className="welcome-broker-check welcome-container" aria-labelledby={titleId}>
      <div className="welcome-broker-panel">
        <h2 id={titleId}>{copy.title}</h2>
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
                  <a className="welcome-cta" href={registerUrl({ source: "landing_broker_check", broker: result.broker.key, lang: language })}>{copy.signup} <ArrowUpRight size={17} aria-hidden="true" /></a>
                  {demoLink("welcome-preview-link")}
                </div>
              ) : (
                <>
                  <div className="welcome-broker-actions">{demoLink("welcome-cta")}</div>
                  <small>{copy.betaNote}</small>
                </>
              )}
            </div>
          )}
          {result?.kind === "unsupported" && (
            <div className="broker-check-result welcome-broker-result">
              <p>{copy.unsupported.replace("{name}", typed)}</p>
              <div className="welcome-broker-actions">{demoLink("welcome-cta")}</div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
