# Portfyl Clay — Stitch prompts

Stitch project: `projects/1812385682940836266` ("Portfyl Clay (Dashboard + Stock Detail)")
Design system: `assets/423192511151747367` ("Portfyl Clay", source: `.stitch/DESIGN.md`)
Device: DESKTOP. Prompts describe layout/content only; colours, fonts and shapes come from the design system.

## 1. Dashboard

Portfyl portfolio Dashboard: the main overview screen of an investor's portfolio analytics web app (Trading 212 / IBKR investor). Claymorphism look: soft inflated raised cards, pressed-in inset wells for nested tiles, pill buttons, generous spacing between cards.

**PLATFORM:** Web, Desktop-first (1440px wide)

**PAGE STRUCTURE:**
1. **Left sidebar (256px, floating raised slab):** Logo "Portfyl", grouped navigation with small uppercase group labels. PORTFOLIO: Dashboard (active), Allocation, Transactions, Cash. RESEARCH: Search, Watchlists. INSIGHTS: Dividends, Analytics. ASSISTANT: AI Assistant. SYSTEM: Import, Settings. Line icon per item. Bottom: portfolio switcher pill ("Main portfolio") and round user avatar.
2. **Page header:** Title "Dashboard", caption "Prices updated 2 min ago". Right: pill buttons "Customize" and "Refresh".
3. **Net Worth hero card (full width, largest):** eyebrow "NET WORTH", huge figure "CZK 2 486 310", green delta pill "▲ +12 480 (+0.51%) today", muted line "Positions CZK 2 301 120 · Cash CZK 185 190", faint smooth area sparkline behind the right half. Row of four inset KPI tiles: Invested CZK 1 910 000 · All-time P&L +CZK 391 120 (green) · Dividends CZK 48 760 · Holdings 23.
4. **Portfolio Performance card (full width):** title with trend icon; segmented toggle "Value | Growth %" (Growth % active); period selector 7D, MTD, 1M, 3M, YTD, 1Y, All (All active); five benchmark chips S&P 500, NASDAQ 100, Dow Jones, STOXX 50, Bitcoin (first two on); large smooth growth-% line chart with two benchmark lines, axes, soft grid, hover tooltip.
5. **Concentration (two cards, label "CONCENTRATION"):** "Heatmap" treemap of holdings by weight coloured by daily change with ticker + % (NVDA, MSFT, AAPL, CEZ, VWCE, ASML…); "Top 10 Holdings" rows with mono ticker, inset bar, weight %, CZK value (VWCE 18.4% CZK 457 600; NVDA 11.2% CZK 278 100; MSFT 9.7%; AAPL 8.1%; CEZ 6.3% …).
6. **Needs attention (two cards, label "NEEDS ATTENTION"):** "Attention signals" with 3 alert rows with icons (NVDA above 10% target; MSFT dividend expected 14 Oct; ASML earnings in 3 days); "Earnings Calendar" rows with ticker, company, date, time (BMO/AMC), EPS estimate.
7. **Top Movers card (full width):** "% | $" sort toggle, period selector "Today | Week | Month"; columns "Gainers" (green up arrow) and "Losers" (red down arrow), 5 rows each: ticker, name, period P&L in CZK, delta pill.
8. **Bottom:** collapsed disclosure row "Insider activity (1Y) ▸".

Interactions: cards lift slightly on hover, active toggles look raised, pressed controls look sunken.

## 2. Stock Detail (NVDA)

Portfyl Stock Detail page for ticker NVDA (NVIDIA Corporation) inside an investor's portfolio analytics web app. Claymorphism look: soft inflated raised cards, pressed-in inset wells for nested tiles, pill buttons, generous spacing.

**PLATFORM:** Web, Desktop-first (1440px wide)

**PAGE STRUCTURE:**
1. **Left sidebar (256px, floating raised slab):** same navigation as the rest of the app (no active item), portfolio switcher pill and user avatar at the bottom.
2. **Back link:** small "‹ Back" text button above the main card.
3. **Main stock card (one large raised card):**
   - **Identity header:** large mono ticker "NVDA" + "NVIDIA Corporation", meta "Technology · United States" with icons. Right: price "$132.48", green change "▲ +2.15 (+1.65%)", pill button with star "Add to watchlist".
   - **Tab bar:** inset trough, active raised pill: Overview (active), Financials, Valuation, Ownership, Filings.
   - **Quick stats row:** six inset tiles — Market Cap $3.26T, P/E (TTM) 54.2, 5Y Avg P/E 61.8, Dividend Yield 0.03%, Beta 1.74, Volume 212M.
   - **52-week range:** slim inset track with marker between low $86.62 and high $152.89.
   - **Two columns:** "One-year price history" smooth area chart with axes and range caption; "Your position" 3x2 grid — Shares 84, Average cost $98.40, Market value $11 128, Unrealized P&L +$2 862 (green), Unrealized P&L % +34.6% (green), Portfolio weight 11.2% — then divider and "Latest transaction: 3 Sep 2026 · Buy · 10 shares at $128.10".
   - **About:** inset panel with a 3–4 line company description.

Interactions: tabs switch with a soft sliding pill, watchlist button toggles to a filled star, chart shows hover tooltip.
