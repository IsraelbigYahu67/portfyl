/** @type {import('tailwindcss').Config} */
import defaultTheme from "tailwindcss/defaultTheme";

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        display: ['"Space Grotesk Variable"', '"Space Grotesk"', ...defaultTheme.fontFamily.sans],
        sans: ['"Inter Variable"', "Inter", ...defaultTheme.fontFamily.sans],
        mono: ['"JetBrains Mono Variable"', '"JetBrains Mono"', ...defaultTheme.fontFamily.mono],
      },
      colors: {
        surface: {
          DEFAULT: "var(--bg)",
          card: "var(--surface-card)",
          hover: "var(--bg-subtle)",
          border: "var(--border)",
        },
        brand: {
          DEFAULT: "var(--brand)",
          dim: "var(--brand-hover)",
          light: "var(--brand-light)",
        },
        ink: "var(--ink)",
        muted: "var(--muted)",
        hairline: "var(--hairline)",
        gain: "var(--gain)",
        loss: "var(--loss)",
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
