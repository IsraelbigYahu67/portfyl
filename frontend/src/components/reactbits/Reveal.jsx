import { useEffect, useRef, useState } from "react";

// Plays react-bits' AnimatedContent's role (fade+lift on scroll into view)
// without gsap/ScrollTrigger: a plain IntersectionObserver flips a CSS class,
// and index.css's .reveal/.reveal-visible transition does the rest.
// jsdom (this repo's test environment) doesn't implement
// IntersectionObserver -- same situation as ResizeObserver in src/test/setup.js
// -- so this renders already-visible rather than crashing or staying hidden.
export default function Reveal({ children, className = "", delay = 0, as: Tag = "div" }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`reveal ${visible ? "reveal-visible" : ""} ${className}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </Tag>
  );
}
