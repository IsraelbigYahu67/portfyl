import { LANDING_IMAGES } from "./landingImages";
import MiniDemoSlot from "./MiniDemoSlot";
import { DEMO_HREFS } from "./miniDemoRegistry";
import Shot from "./Shot";

const isPhone = (key) => key.startsWith("phone");

// A feature with a live mini demo is a row (text left, the demo below, its
// desktop screenshots standing in until it loads). Without one, a feature
// whose first desktop screenshot exists is a row with its pictures and the
// rest sit in a three-column text strip. Pictures keyed `phone...` are small
// insets beside the desktop ones in the old rows and are not used in a demo's
// placeholder.
export default function FeatureList({ copy, language }) {
  const shown = copy.features.map((feature) => {
    const pictures = feature.images
      .map((key, index) => ({ key, image: LANDING_IMAGES[key], alt: feature.alts[index] }))
      .filter((picture) => picture.image);
    return { feature, pictures, row: Boolean(feature.demo) || pictures.some((picture) => !isPhone(picture.key)) };
  });
  const rows = shown.filter((item) => item.row);
  const texts = shown.filter((item) => !item.row);
  return (
    <section className="welcome-block welcome-container" id="funkce" aria-labelledby="funkce-title">
      <div className="welcome-head"><h2 id="funkce-title">{copy.featuresHeading}</h2></div>
      {rows.map(({ feature, pictures }) => (
        <article className="welcome-feature" key={feature.title}>
          <div className="welcome-feature-text"><h3>{feature.title}</h3><p>{feature.text}</p></div>
          {feature.demo ? (
            <MiniDemoSlot
              kind={feature.demo}
              language={language}
              copy={copy.miniDemo}
              pictures={pictures.filter((picture) => !isPhone(picture.key))}
              demoHref={DEMO_HREFS[feature.demo]}
            />
          ) : (
            <div className="welcome-feature-shots">
              {pictures.map(({ key, image, alt }) => <Shot key={key} image={image} alt={alt} className={isPhone(key) ? "welcome-shot-phone" : ""} />)}
            </div>
          )}
        </article>
      ))}
      {texts.length > 0 && (
        <div className="welcome-more">
          {texts.map(({ feature }) => <div key={feature.title}><h3>{feature.title}</h3><p>{feature.text}</p></div>)}
        </div>
      )}
    </section>
  );
}
