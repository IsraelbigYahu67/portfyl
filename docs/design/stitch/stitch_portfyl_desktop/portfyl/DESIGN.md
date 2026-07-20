---
name: Portfyl
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#ffb95f'
  on-tertiary: '#472a00'
  tertiary-container: '#ca8100'
  on-tertiary-container: '#3e2400'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  numeric-data:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 20px
  margin-mobile: 16px
  margin-desktop: 40px
  max-width: 1440px
---

## Brand & Style

The design system is engineered for a high-performance investment and portfolio analytics environment. The brand personality is rooted in **precision, transparency, and institutional-grade reliability**. It aims to evoke a sense of calm control amidst complex data landscapes, prioritizing clarity and rapid information processing for the modern investor.

The visual style is **Corporate Modern with Glassmorphism accents**. It utilizes a sophisticated dark-mode-first approach, employing subtle depth through translucent layers and refined background blurs. This creates a focused environment where data visualizations remain the primary focus while the interface recedes into the background.

Key characteristics include:
- **Data-Centricity:** Every element is optimized for density without sacrificing legibility.
- **Precision:** Mathematical alignment and a strict grid system to reinforce trustworthiness.
- **Luminance Management:** Careful use of vibrant accents against a muted, deep canvas to guide user attention to critical financial metrics.

## Colors

The palette is optimized for a high-contrast dark environment to reduce eye strain during long-form data analysis.

- **Primary Canvas:** A deep, obsidian blue-black (`#020617`) serves as the base.
- **Surface Elevation:** Cards and containers use a navy charcoal (`#0F172A`) to create distinct structural zones.
- **Functional Accents:**
    - **Action Blue:** Used exclusively for primary interactive elements, buttons, and selection states.
    - **Growth Emerald:** Reserved for positive ROI, upward trends, and "success" states.
    - **Warning/Negative:** High-saturation red for portfolio losses or critical alerts.
- **Translucency:** Glassmorphic overlays use a white-wash alpha (2-4%) to create "sheen" on surface headers.

## Typography

This design system utilizes a dual-font strategy to balance character with utility.

- **Plus Jakarta Sans** is used for headlines and display metrics. Its slightly wider apertures and modern geometric feel provide a fresh, professional look.
- **Inter** is the workhorse for all body text, data tables, and labels. It is specifically chosen for its exceptional legibility at small sizes and its neutral, systematic tone.
- **Numerical Treatment:** For all financial data, the `tnum` (tabular figures) OpenType feature must be enabled to ensure numbers align vertically in tables and lists.
- **Hierarchy:** Use `label-md` for secondary metadata and table headers to create clear vertical separation from the primary data points.

## Layout & Spacing

The layout philosophy follows a **Fluid Grid with Fixed Constraints**. This ensures a responsive experience that preserves information density on ultra-wide monitors while remaining accessible on tablets.

- **Grid System:** A 12-column grid for desktop with 20px gutters. On mobile, this collapses to a single-column layout with 16px margins.
- **Density:** The system uses a 4px baseline rhythm. For data-heavy views (Portfolio Tables, Asset Lists), use the "Compact" spacing model (8px padding). For marketing or high-level dashboard overviews, use the "Standard" spacing model (16px padding).
- **Z-Axis Reflow:** Dashboard widgets should reflow based on priority, with critical KPIs always anchored to the top-left in the reading path.

## Elevation & Depth

Elevation in this design system is communicated through **Tonal Layering and Glassmorphism** rather than heavy shadows.

- **Level 0 (Canvas):** Background (`#020617`).
- **Level 1 (Base Cards):** Surface (`#0F172A`) with a 1px border (`#1E293B`).
- **Level 2 (Active/Hover):** Surface with a subtle outer glow using the primary color at 10% opacity and a backdrop-blur of 12px.
- **Overlays (Modals/Dropdowns):** Semi-transparent surfaces (70% opacity) with a 20px backdrop-blur and a 1px border to simulate a glass pane.
- **Shadows:** Use only one shadow style: a soft, ultra-diffused "Ambient" shadow (`0px 4px 20px rgba(0, 0, 0, 0.5)`) for floating elements like tooltips and dropdowns.

## Shapes

The shape language is **Refined and Structured**.

- **Standard Elements:** Buttons, input fields, and cards utilize a `0.5rem` (8px) radius. This provides a modern, approachable feel while maintaining a professional, "squared" posture.
- **Interactive Indicators:** Small elements like status tags or "chips" use a fully rounded (pill-shaped) style to distinguish them from structural containers.
- **Charts:** Line charts should use a slight smoothing (Catmull-Rom) to avoid jagged transitions, reinforcing the "refined" brand aesthetic.

## Components

- **Buttons:**
  - **Primary:** Solid `#3B82F6` with white text. High-contrast.
  - **Secondary:** Transparent background with a `#1E293B` border. Subtle hover state with a 5% white overlay.
- **Data Tables:**
  - No vertical borders. Use horizontal dividers (`#1E293B`) only. 
  - Row height: 48px for standard, 40px for compact.
  - Hover state: Change background to `#1E293B` to highlight the entire data row.
- **Cards (Widgets):**
  - Must include a `label-md` header.
  - Content should have 20px internal padding.
  - Use a subtle linear gradient from top-left to bottom-right for the background (2% lighter at the top).
- **Input Fields:**
  - Dark-filled background (`#020617`) with a 1px border. 
  - Focus state: Border color changes to `#3B82F6` with a 2px blue outer glow.
- **Status Chips:**
  - Use a "ghost" style: 10% opacity background of the status color (Green/Red) with 100% opacity text. This ensures readability without overwhelming the dashboard with color.
- **Portfolio Analytics:**
  - Use sparklines within table rows for 7-day trends.
  - Use bold, high-contrast typography for the "Total Balance" display.