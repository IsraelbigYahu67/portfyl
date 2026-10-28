import { CLAY_TOKENS } from "./themeTokens";

// The public pages (landing, /terms, /privacy) render outside App.jsx, so
// applyAppearance() never runs there. They scope the same Clay variables to
// their root instead of retyping values; the theme-clay class then resolves
// index.css's --clay-* shadows. See DESIGN.md section 10.
export const CLAY_STYLE = {
  "--brand": CLAY_TOKENS.brand,
  "--brand-hover": CLAY_TOKENS.brandHover,
  "--brand-light": CLAY_TOKENS.brandLight,
  "--bg": CLAY_TOKENS.bg,
  "--bg-subtle": CLAY_TOKENS.bgSubtle,
  "--surface-card": CLAY_TOKENS.surfaceCard,
  "--surface-card-elevated": CLAY_TOKENS.surfaceCardElevated,
  "--border": CLAY_TOKENS.border,
  "--hairline": CLAY_TOKENS.hairline,
  "--ink": CLAY_TOKENS.ink,
  "--muted": CLAY_TOKENS.muted,
  "--gain": CLAY_TOKENS.gain,
  "--loss": CLAY_TOKENS.loss,
  "--shadow-ambient": CLAY_TOKENS.shadowAmbient,
  "--shadow-inset": CLAY_TOKENS.shadowInset,
  "--radius-card": CLAY_TOKENS.radiusCard,
  ...Object.fromEntries(CLAY_TOKENS.chart.map((color, i) => [`--chart-${i + 1}`, color])),
};
