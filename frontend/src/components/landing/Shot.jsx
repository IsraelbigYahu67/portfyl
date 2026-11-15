// One product screenshot: the only raised object on the landing page.
// `image` is a LANDING_IMAGES entry; a null one renders nothing.
export default function Shot({ image, alt, eager = false, className = "" }) {
  if (!image) return null;
  return (
    <figure className={`welcome-shot ${className}`.trim()}>
      <img
        src={image.src} alt={alt} width={image.width} height={image.height}
        {...(eager ? { fetchPriority: "high" } : { loading: "lazy" })}
      />
    </figure>
  );
}
