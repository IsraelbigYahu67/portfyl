import { lazy } from 'react';
import { TRACKER_HOME } from '../lib/routes';

const loadDashboard = () => import('../pages/Dashboard');
const loadAllocation = () => import('../pages/Allocation');
const loadTransactions = () => import('../pages/Transactions');
const loadImport = () => import('../pages/Import');
const loadDividends = () => import('../pages/Dividends');
const loadAnalytics = () => import('../pages/Analytics');
const loadSearch = () => import('../pages/Search');
export const loadStock = () => import('../pages/Stock');
const loadWatchlists = () => import('../pages/Watchlists');
const loadAssistant = () => import('../pages/Assistant');
const loadSettings = () => import('../pages/Settings');
const loadOnboarding = () => import('../pages/Onboarding');
export const LazyOnboarding = lazy(loadOnboarding);
export const LazyImport = lazy(loadImport);

export const SHARED_AUTHENTICATED_ROUTES = Object.freeze([
  [TRACKER_HOME, loadDashboard], ['/allocation', loadAllocation], ['/transactions', loadTransactions],
  ['/import', loadImport], ['/dividends', loadDividends], ['/analytics', loadAnalytics],
  ['/search', loadSearch], ['/stock/:ticker', loadStock], ['/watchlists', loadWatchlists],
  ['/assistant', loadAssistant], ['/settings', loadSettings],
].map(([path, preload]) => ({ path, preload, Component: path === '/import' ? LazyImport : lazy(preload) })));
