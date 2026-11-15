import { LANDING_IMAGES } from "./landingImages";
import Shot from "./Shot";

const isPhone = (key) => key.startsWith("phone");

// A feature whose first desktop screenshot exists is a row with its pictures;
// the rest (no picture, or one not shot yet) sit in a three-column text strip.
// Pictures keyed `phone...` are small insets beside the desktop ones.
export default function FeatureList({ copy }) {
  const shown = copy.features.map((feature) => {
    const pictures = feature.images
      .map((key, index) => ({ key, image: LANDING_IMAGES[key], alt: feature.alts[index] }))
      .filter((picture) => picture.image);
    return { feature, pictures, row: pictures.some((picture) => !isPhone(picture.key)) };
  });
  const rows = shown.filter((item) => item.row);
  const texts = shown.filter((item) => !item.row);
  return (
    <section className="welcome-block welcome-container" id="funkce" aria-labelledby="funkce-title">
      <div className="welcome-head"><h2 id="funkce-title">{copy.featuresHeading}</h2></div>
      {rows.map(({ feature, pictures }) => (
        <article className="welcome-feature" key={feature.title}>
          <div className="welcome-feature-text"><h3>{feature.title}</h3><p>{feature.text}</p></div>
          <div className="welcome-feature-shots">
            {pictures.map(({ key, image, alt }) => <Shot key={key} image={image} alt={alt} className={isPhone(key) ? "welcome-shot-phone" : ""} />)}
          </div>
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
