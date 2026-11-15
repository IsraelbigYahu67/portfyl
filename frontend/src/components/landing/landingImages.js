// Product screenshots on the landing page. English UI, one set for all three
// languages. A null entry is a picture that has not been shot yet: its figure
// is not rendered. Until the owner's new set arrives (plan Task 5) the
// 2026-09-11 captures stand in for hero, allocation and stock.
const live = (name, width, height) => ({ src: `/landing/${name}-live-20260911.png`, width, height });

export const LANDING_IMAGES = Object.freeze({
  hero: live("performance", 1004, 455),
  allocation: live("allocation", 1047, 365),
  sectors: null,
  dividends: null,
  stock: live("stock", 1047, 350),
  valuation: null,
  analytics: null,
  importPreview: null,
  onboardingBrokers: null,
  phoneDashboard: null,
  phoneAllocation: null,
});
