import { Component } from 'react';
import { reportError } from '../../errorMonitoring';

export default class RouteBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error, info) {
    // A no-op when Sentry isn't configured (no VITE_SENTRY_DSN) -- see errorMonitoring.js.
    reportError(error, { extra: { componentStack: info?.componentStack } });
  }
  render() {
    if (this.state.failed) return <div role="alert" className="card my-4 space-y-3">
      <h1 className="text-lg font-semibold">This page could not load</h1>
      <p className="text-sm text-muted">Reload to try again.</p>
      <button type="button" className="btn-primary min-h-11" onClick={() => window.location.reload()}>Reload page</button>
    </div>;
    return this.props.children;
  }
}
