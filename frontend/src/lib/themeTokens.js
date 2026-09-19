// Appearance tokens, moved out of App.jsx so both the app and its tests can
// import raw color values without pulling in React/router/auth context.

export const PALETTES = {
  blue: {
    brand: "#3B82F6", brandHover: "#2563EB", brandLight: "#DBEAFE", brandLightDark: "#1E3A5F",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(59,130,246,0.16)",
  },
  green: {
    brand: "#34D399", brandHover: "#10B981", brandLight: "#D1FAE5", brandLightDark: "#0F3D30",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(52,211,153,0.16)",
  },
  purple: {
    brand: "#A78BFA", brandHover: "#8B5CF6", brandLight: "#EDE9FE", brandLightDark: "#2E2555",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(167,139,250,0.16)",
  },
};

// Neutral dark surfaces shared across all hues (the brand stays vivid in dark mode).
// bgSubtle sits a step above the card so hover states / progress tracks stay visible.
export const DARK_SURFACES = {
  bg: "#020617", bgSubtle: "#0B1326", surfaceCard: "#131B2E", surfaceCardElevated: "#1F2435",
  border: "#2A3245", ink: "#DAE2FD", muted: "#8A93B3", hairline: "#2A3245",
};

export const LIGHT_TOKENS = {
  surfaceCard: "#FFFFFF", surfaceCardElevated: "#F7F9FD", border: "#DDE3F0",
  ink: "#10162B", muted: "#6B7592", hairline: "#DDE3F0",
};

// "Premium" — warm glassmorphism/neumorphism hybrid: soft dual shadows (the
// neumorphic half) layered on translucent, blurred surfaces (the glass half)
// over a warm mesh-gradient background (.theme-premium body in index.css).
// One fixed light appearance — ignores Light/Dark/System entirely, same as
// the historical Neumorphism style this replaces.
// See docs/superpowers/specs/2026-08-30-portfyl-premium-redesign-design.md.
export const NEU_TOKENS = {
  bg: "#F3E8DA", bgSubtle: "#ECE0CF",
  surfaceCard: "rgba(250,245,237,0.78)", surfaceCardElevated: "rgba(253,249,243,0.92)",
  border: "rgba(120,105,84,0.14)", hairline: "rgba(120,105,84,0.14)",
  ink: "#3A352C", muted: "#6B6353",
  brand: "#6D7048", brandHover: "#5C5F3C", brandLight: "#E4E5D3",
  gain: "#5B7A4C", loss: "#B8543A",
  glassBorderAlpha: "rgba(120,105,84,0.16)", glassOverlayAlpha: "rgba(255,252,247,0.55)",
  blurCard: "14px", blurOverlay: "22px",
  shadowAmbient: "7px 7px 18px rgba(190,172,146,0.5), -7px -7px 18px rgba(255,253,248,0.9)",
  shadowInset: "inset 3px 3px 8px rgba(190,172,146,0.45), inset -3px -3px 8px rgba(255,253,248,0.85)",
  radiusCard: "1.25rem",
  chart: ["#A9AB88", "#DBAA89", "#D4C3A1", "#B7AFA3", "#7C8A5A", "#C08457", "#9E8E6E", "#8A8478"],
};
// Classic's chart series previously lived only in index.css's :root block
// (--chart-1..8); pulled into this constant so applyAppearance() can reset
// them inline the same way both branches reset every other token, since an
// inline style always outranks a :root declaration.
export const GLASS_CHART = ["var(--brand)", "#4EDEA3", "#FFB95F", "#A78BFA", "#38BDF8", "#FB7185", "#FACC15", "#64748B"];

// --- Semantic accessible tokens -------------------------------------------
//
// Per-appearance colors for text and chart elements, resolved to opaque
// values so contrast can be computed directly (no runtime CSS-variable
// lookup). "Classic" light/dark are hue-independent for text/gain/loss/grid;
// only the focus ring follows the user's chosen brand hue, so it is
// expressed per-hue below.

// The original #10B981 Classic-light gain green only reaches 2.54:1 against
// a white card (below the 3:1 non-text floor); #0E9E70 is the same hue
// darkened just enough to clear it. Also reused for the green focus ring,
// since the raw green brand/hover swatches (1.92:1 / 2.54:1) fail too.
const CLASSIC_LIGHT_GAIN = "#0E9E70";
const CLASSIC_LIGHT_LOSS = "#EF4444";
const CLASSIC_DARK_GAIN = "#34D399";
const CLASSIC_DARK_LOSS = "#F87171";

export const SEMANTIC_THEME_TOKENS = {
  premium: {
    background: NEU_TOKENS.bg,
    textPrimary: NEU_TOKENS.ink,
    textSecondary: NEU_TOKENS.muted,
    textTertiary: NEU_TOKENS.muted,
    chartAxis: NEU_TOKENS.muted,
    chartGrid: NEU_TOKENS.muted,
    focus: NEU_TOKENS.brand,
    gain: NEU_TOKENS.gain,
    loss: NEU_TOKENS.loss,
  },
  classicLight: {
    background: LIGHT_TOKENS.surfaceCard,
    textPrimary: LIGHT_TOKENS.ink,
    textSecondary: LIGHT_TOKENS.muted,
    textTertiary: LIGHT_TOKENS.muted,
    chartAxis: LIGHT_TOKENS.muted,
    chartGrid: LIGHT_TOKENS.muted,
    gain: CLASSIC_LIGHT_GAIN,
    loss: CLASSIC_LIGHT_LOSS,
    // Focus rings need a 3:1 non-text minimum. The raw brand swatch clears
    // it for blue (3.68:1) but not green (1.92:1) or purple (2.72:1), so
    // those two use a darker variant instead of the literal brand hue.
    focusByHue: {
      blue: PALETTES.blue.brand,
      green: CLASSIC_LIGHT_GAIN,
      purple: PALETTES.purple.brandHover,
    },
  },
  classicDark: {
    background: DARK_SURFACES.surfaceCard,
    textPrimary: DARK_SURFACES.ink,
    textSecondary: DARK_SURFACES.muted,
    textTertiary: DARK_SURFACES.muted,
    chartAxis: DARK_SURFACES.muted,
    chartGrid: DARK_SURFACES.muted,
    gain: CLASSIC_DARK_GAIN,
    loss: CLASSIC_DARK_LOSS,
    focusByHue: {
      blue: PALETTES.blue.brand,
      green: PALETTES.green.brand,
      purple: PALETTES.purple.brand,
    },
  },
};

function pair(theme, name, kind, foreground, background, minimum) {
  return { theme, name, kind, foreground, background, minimum };
}

// Flattened { theme, name, kind, foreground, background, minimum } rows
// consumed by contrast.test.js's it.each matrix. "text" rows (real glyphs:
// body copy, numeric values, axis/legend labels) require 4.5:1; "nonText"
// rows (gain/loss pills, grid lines, focus rings) require 3:1.
export const THEME_CONTRAST_PAIRS = [
  pair("premium", "textPrimary", "text", SEMANTIC_THEME_TOKENS.premium.textPrimary, SEMANTIC_THEME_TOKENS.premium.background, 4.5),
  pair("premium", "textSecondary", "text", SEMANTIC_THEME_TOKENS.premium.textSecondary, SEMANTIC_THEME_TOKENS.premium.background, 4.5),
  pair("premium", "textTertiary", "text", SEMANTIC_THEME_TOKENS.premium.textTertiary, SEMANTIC_THEME_TOKENS.premium.background, 4.5),
  pair("premium", "chartAxis", "text", SEMANTIC_THEME_TOKENS.premium.chartAxis, SEMANTIC_THEME_TOKENS.premium.background, 4.5),
  pair("premium", "chartGrid", "nonText", SEMANTIC_THEME_TOKENS.premium.chartGrid, SEMANTIC_THEME_TOKENS.premium.background, 3),
  pair("premium", "focus", "nonText", SEMANTIC_THEME_TOKENS.premium.focus, SEMANTIC_THEME_TOKENS.premium.background, 3),
  pair("premium", "gain", "nonText", SEMANTIC_THEME_TOKENS.premium.gain, SEMANTIC_THEME_TOKENS.premium.background, 3),
  pair("premium", "loss", "nonText", SEMANTIC_THEME_TOKENS.premium.loss, SEMANTIC_THEME_TOKENS.premium.background, 3),

  pair("classicLight", "textPrimary", "text", SEMANTIC_THEME_TOKENS.classicLight.textPrimary, SEMANTIC_THEME_TOKENS.classicLight.background, 4.5),
  pair("classicLight", "textSecondary", "text", SEMANTIC_THEME_TOKENS.classicLight.textSecondary, SEMANTIC_THEME_TOKENS.classicLight.background, 4.5),
  pair("classicLight", "textTertiary", "text", SEMANTIC_THEME_TOKENS.classicLight.textTertiary, SEMANTIC_THEME_TOKENS.classicLight.background, 4.5),
  pair("classicLight", "chartAxis", "text", SEMANTIC_THEME_TOKENS.classicLight.chartAxis, SEMANTIC_THEME_TOKENS.classicLight.background, 4.5),
  pair("classicLight", "chartGrid", "nonText", SEMANTIC_THEME_TOKENS.classicLight.chartGrid, SEMANTIC_THEME_TOKENS.classicLight.background, 3),
  pair("classicLight", "gain", "nonText", SEMANTIC_THEME_TOKENS.classicLight.gain, SEMANTIC_THEME_TOKENS.classicLight.background, 3),
  pair("classicLight", "loss", "nonText", SEMANTIC_THEME_TOKENS.classicLight.loss, SEMANTIC_THEME_TOKENS.classicLight.background, 3),
  pair("classicLight", "focus-blue", "nonText", SEMANTIC_THEME_TOKENS.classicLight.focusByHue.blue, SEMANTIC_THEME_TOKENS.classicLight.background, 3),
  pair("classicLight", "focus-green", "nonText", SEMANTIC_THEME_TOKENS.classicLight.focusByHue.green, SEMANTIC_THEME_TOKENS.classicLight.background, 3),
  pair("classicLight", "focus-purple", "nonText", SEMANTIC_THEME_TOKENS.classicLight.focusByHue.purple, SEMANTIC_THEME_TOKENS.classicLight.background, 3),

  pair("classicDark", "textPrimary", "text", SEMANTIC_THEME_TOKENS.classicDark.textPrimary, SEMANTIC_THEME_TOKENS.classicDark.background, 4.5),
  pair("classicDark", "textSecondary", "text", SEMANTIC_THEME_TOKENS.classicDark.textSecondary, SEMANTIC_THEME_TOKENS.classicDark.background, 4.5),
  pair("classicDark", "textTertiary", "text", SEMANTIC_THEME_TOKENS.classicDark.textTertiary, SEMANTIC_THEME_TOKENS.classicDark.background, 4.5),
  pair("classicDark", "chartAxis", "text", SEMANTIC_THEME_TOKENS.classicDark.chartAxis, SEMANTIC_THEME_TOKENS.classicDark.background, 4.5),
  pair("classicDark", "chartGrid", "nonText", SEMANTIC_THEME_TOKENS.classicDark.chartGrid, SEMANTIC_THEME_TOKENS.classicDark.background, 3),
  pair("classicDark", "gain", "nonText", SEMANTIC_THEME_TOKENS.classicDark.gain, SEMANTIC_THEME_TOKENS.classicDark.background, 3),
  pair("classicDark", "loss", "nonText", SEMANTIC_THEME_TOKENS.classicDark.loss, SEMANTIC_THEME_TOKENS.classicDark.background, 3),
  pair("classicDark", "focus-blue", "nonText", SEMANTIC_THEME_TOKENS.classicDark.focusByHue.blue, SEMANTIC_THEME_TOKENS.classicDark.background, 3),
  pair("classicDark", "focus-green", "nonText", SEMANTIC_THEME_TOKENS.classicDark.focusByHue.green, SEMANTIC_THEME_TOKENS.classicDark.background, 3),
  pair("classicDark", "focus-purple", "nonText", SEMANTIC_THEME_TOKENS.classicDark.focusByHue.purple, SEMANTIC_THEME_TOKENS.classicDark.background, 3),
];
