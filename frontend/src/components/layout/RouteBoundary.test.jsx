import { render, screen } from '@testing-library/react';
import RouteBoundary from './RouteBoundary';
it('renders a recoverable route error when a chunk fails', () => {
  const log = vi.spyOn(console, 'error').mockImplementation(() => {});
  const suppressExpected = event => event.preventDefault();
  window.addEventListener('error', suppressExpected);
  const Broken = () => { throw new Error('chunk unavailable'); };
  render(<RouteBoundary><Broken /></RouteBoundary>);
  expect(screen.getByRole('alert')).toHaveTextContent('This page could not load');
  expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument();
  window.removeEventListener('error', suppressExpected);
  log.mockRestore();
});
