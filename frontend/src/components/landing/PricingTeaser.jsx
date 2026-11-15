import { PLAN_PRICES_CENTS, formatPlanPrice } from "../../lib/planPrices";

// Prices come from lib/planPrices.js (the pricing page's constant), shown
// even while billing is off. The trial line appears only when signup is open.
const PRICES = [0, PLAN_PRICES_CENTS.investor, PLAN_PRICES_CENTS.pro];

export default function PricingTeaser({ copy, language, signupOpen }) {
  const { pricing } = copy;
  return (
    <section className="welcome-block welcome-container" id="cenik" aria-labelledby="cenik-title">
      <div className="welcome-head">
        <h2 id="cenik-title">{pricing.heading}</h2>
        <p className="welcome-muted">{pricing.note}{signupOpen && <> {pricing.trial}</>}</p>
      </div>
      <div className="welcome-plans">
        {pricing.plans.map((plan, index) => (
          <div className="welcome-plan" key={plan.name}>
            <h3>{plan.name}</h3>
            <p className="welcome-price">
              {formatPlanPrice(PRICES[index], language)}
              {PRICES[index] > 0 && <> <span>{pricing.perMonth}</span></>}
            </p>
            <ul>{plan.features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
          </div>
        ))}
      </div>
    </section>
  );
}
