import { brokersForLanguage } from "../../lib/onboardingBrokers";
import BrokerCheck from "./BrokerCheck";

// The two groups come straight from the onboarding's broker list, so the
// landing can never name a broker the product does not read.
export default function BrokerList({ copy, language, signupOpen }) {
  const ordered = brokersForLanguage(language);
  const api = ordered.filter((broker) => broker.api).map((broker) => broker.name);
  const file = [...ordered.filter((broker) => !broker.api).map((broker) => broker.name), copy.brokers.custom];
  return (
    <section className="welcome-brokers welcome-container" id="brokeri" aria-label={copy.nav[1]}>
      <dl>
        <dt>{copy.brokers.api}</dt><dd>{api.join(" · ")}</dd>
        <dt>{copy.brokers.file}</dt><dd>{file.join(" · ")}</dd>
      </dl>
      <BrokerCheck copy={copy.brokerCheck} language={language} signupOpen={signupOpen} />
    </section>
  );
}
