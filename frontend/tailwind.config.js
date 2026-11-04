/** @type {import('tailwindcss').Config} */
import defaultTheme from "tailwindcss/defaultTheme";

// Theme colors are CSS variables (lib/themeTokens.js, index.css), which
// Tailwind cannot split into channels. Given a bare var(--x) it silently
// drops every opacity modifier, so bg-loss/10, border-brand/30, ring-brand/30
// and the like produced no CSS at all. Mixing the token with transparent gives
// Tailwind an <alpha-value> slot: "/10" becomes 10%, and a class without a
// modifier gets alpha 1, i.e. exactly the token color. Token values are sRGB
// (hex/rgba), so mixing in srgb loses nothing. src/tailwindTokens.test.js guards it.
const token = (name) => `color-mix(in srgb, var(${name}) calc(<alpha-value> * 100%), transparent)`;

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        display: ['"Plus Jakarta Sans Variable"', '"Plus Jakarta Sans"', ...defaultTheme.fontFamily.sans],
        sans: ['"Inter Variable"', "Inter", ...defaultTheme.fontFamily.sans],
        mono: ['"JetBrains Mono Variable"', '"JetBrains Mono"', ...defaultTheme.fontFamily.mono],
      },
      colors: {
        surface: {
          DEFAULT: token("--bg"),
          card: token("--surface-card"),
          "card-elevated": token("--surface-card-elevated"),
          hover: token("--bg-subtle"),
          border: token("--border"),
        },
        brand: {
          DEFAULT: token("--brand"),
          dim: token("--brand-hover"),
          light: token("--brand-light"),
        },
        ink: token("--ink"),
        muted: token("--muted"),
        hairline: token("--hairline"),
        gain: token("--gain"),
        loss: token("--loss"),
      },
      boxShadow: {
        card: "0 1px 2px rgba(11,18,32,0.04), 0 1px 3px rgba(11,18,32,0.06)",
        "card-hover": "0 6px 16px rgba(11,18,32,0.08), 0 2px 6px rgba(11,18,32,0.05)",
        pop: "0 12px 32px rgba(11,18,32,0.14)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both",
      },
    },
  },
  plugins: [],
};
