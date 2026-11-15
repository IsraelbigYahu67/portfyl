// Questions with `signupOnly` (what happens after the trial) are shown only
// while signup is open, and `aOpen` replaces the answer that says signup is
// invite-only. Native <details>: works without JavaScript.
export default function LandingFaq({ copy, signupOpen }) {
  const questions = copy.questions.filter((item) => signupOpen || !item.signupOnly);
  return (
    <section className="welcome-block welcome-faq welcome-container" id="otazky" aria-labelledby="faq-title">
      <h2 id="faq-title">{copy.faqHeading}</h2>
      <div>
        {questions.map((item, index) => (
          <details key={item.q} open={index === 0}>
            <summary>{item.q}</summary>
            <p>{signupOpen && item.aOpen ? item.aOpen : item.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
