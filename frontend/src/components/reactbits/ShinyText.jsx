// Adapted from react-bits' ShinyText: the upstream version drives the sweep
// with `motion/react`'s useAnimationFrame; this instead emits a plain <span>
// and lets a CSS @keyframes animation (.shiny-text in index.css) do the
// sweep, so no animation library is needed.
export default function ShinyText({ text, className = "", disabled = false }) {
  return (
    <span className={`shiny-text ${disabled ? "" : "shiny-text-animated"} ${className}`}>
      {text}
    </span>
  );
}
