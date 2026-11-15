import { LANDING_IMAGES } from "./landingImages";
import Shot from "./Shot";

export default function HowItWorks({ copy }) {
  return (
    <section className="welcome-band" aria-labelledby="how-title">
      <div className="welcome-block welcome-container">
        <div className="welcome-head"><h2 id="how-title">{copy.howHeading}</h2></div>
        <ol className="welcome-steps">
          {copy.steps.map((step) => (
            <li key={step.title}>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
              {step.image && <Shot image={LANDING_IMAGES[step.image]} alt={step.alt} />}
            </li>
          ))}
        </ol>
        <div className="welcome-facts">
          <h3>{copy.factsHeading}</h3>
          <ul>{copy.dataFacts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
        </div>
      </div>
    </section>
  );
}
