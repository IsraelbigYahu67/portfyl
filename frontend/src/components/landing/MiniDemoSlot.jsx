import { Component, Suspense, useEffect, useRef, useState } from "react";
import { MINI_DEMOS } from "./miniDemoRegistry";
import { useMiniDemoAnalytics } from "./useMiniDemoAnalytics";

// What stands in the frame until the live demo is shown (and when it cannot
// be): the feature's screenshots, else a short text. No numbers: this is part
// of the prerendered HTML. Plain <img> and no nested <figure>, so a frame is
// one balanced block (scripts/landing-bundle-guard.mjs counts them).
function Placeholder({ copy, pictures, notice }) {
  return (
    <div className="welcome-minidemo-placeholder">
      {pictures.length === 0 && <p className="welcome-minidemo-text">{copy.loading}</p>}
      {pictures.map(({ key, image, alt }) => (
        <img key={key} src={image.src} alt={alt} width={image.width} height={image.height} loading="lazy" />
      ))}
      {notice && <p className="welcome-minidemo-text" role="status">{notice}</p>}
    </div>
  );
}

// A demo that throws, or whose chunk fails to load, must not take the page
// down: the placeholder stays and a notice says what happened.
class DemoBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { console.error("Mini demo failed", error); }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

// One live mini demo under a feature. On the server and on the first render
// in the browser only the label and the placeholder exist (`active` starts
// false); the demo is imported and drawn once the frame comes within 200px of
// the screen. Nothing here reads `window` or time while rendering.
export default function MiniDemoSlot({ kind, language, copy, pictures = [], demoHref }) {
  const [active, setActive] = useState(false);
  const frame = useRef(null);
  const { reportUse } = useMiniDemoAnalytics(kind, language);
  const Demo = MINI_DEMOS[kind];

  useEffect(() => {
    if (active) return undefined;
    if (typeof IntersectionObserver === "undefined" || !frame.current) {
      setActive(true);
      return undefined;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setActive(true);
        observer.disconnect();
      }
    }, { rootMargin: "200px 0px" });
    observer.observe(frame.current);
    return () => observer.disconnect();
  }, [active]);

  const placeholder = <Placeholder copy={copy} pictures={pictures} />;
  return (
    <figure className="welcome-minidemo" data-minidemo={kind} ref={frame}>
      <p className="welcome-minidemo-label"><strong>{copy.badge}</strong> <span>{copy.disclaimer}</span></p>
      <div className="welcome-minidemo-body">
        {active && Demo ? (
          <DemoBoundary fallback={<Placeholder copy={copy} pictures={pictures} notice={copy.unavailable} />}>
            <Suspense fallback={placeholder}>
              <Demo language={language} copy={copy} onUse={reportUse} />
            </Suspense>
          </DemoBoundary>
        ) : placeholder}
      </div>
      {demoHref && <p className="welcome-minidemo-more"><a className="welcome-textlink" href={demoHref}>{copy.openDemo}</a></p>}
    </figure>
  );
}
