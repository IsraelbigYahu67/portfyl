import { CLAY_TOKENS } from "../../../lib/themeTokens";

// The CSS variables the app sets on <html> for its Clay look (the warm branch
// of applyAppearance() in App.jsx), scoped to one element so a mini demo on
// the flat landing page draws with the app's own tokens. Unlike CLAY_STYLE
// (the landing's palette) it carries the glass, blur and chart variables the
// real components read, and no --landing-paper. Built from CLAY_TOKENS only.
export const APP_CLAY_SCOPE = Object.freeze({
  "--brand": CLAY_TOKENS.brand,
  "--brand-hover": CLAY_TOKENS.brandHover,
  "--brand-light": CLAY_TOKENS.brandLight,
  "--bg": CLAY_TOKENS.bg,
  "--bg-subtle": CLAY_TOKENS.bgSubtle,
  "--sidebar-active": CLAY_TOKENS.brandLight,
  "--surface-card": CLAY_TOKENS.surfaceCard,
  "--surface-card-elevated": CLAY_TOKENS.surfaceCardElevated,
  "--border": CLAY_TOKENS.border,
  "--hairline": CLAY_TOKENS.hairline,
  "--ink": CLAY_TOKENS.ink,
  "--muted": CLAY_TOKENS.muted,
  "--gain": CLAY_TOKENS.gain,
  "--loss": CLAY_TOKENS.loss,
  "--glass-border-alpha": CLAY_TOKENS.glassBorderAlpha,
  "--glass-overlay-alpha": CLAY_TOKENS.glassOverlayAlpha,
  "--blur-card": CLAY_TOKENS.blurCard,
  "--blur-overlay": CLAY_TOKENS.blurOverlay,
  "--shadow-ambient": CLAY_TOKENS.shadowAmbient,
  "--shadow-inset": CLAY_TOKENS.shadowInset,
  "--radius-card": CLAY_TOKENS.radiusCard,
  ...Object.fromEntries(CLAY_TOKENS.chart.map((color, i) => [`--chart-${i + 1}`, color])),
});
