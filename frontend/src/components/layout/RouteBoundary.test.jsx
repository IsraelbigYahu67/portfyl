import { render, screen } from '@testing-library/react';
import { reportError } from '../../errorMonitoring';
import RouteBoundary from './RouteBoundary';

vi.mock('../../errorMonitoring', () => ({ reportError: vi.fn() }));

it('renders a recoverable route error when a chunk fails', () => {
  const log = vi.spyOn(console, 'error').mockImplementation(() => {});
  const suppressExpected = event => event.preventDefault();
  window.addEventListener('error', suppressExpected);
  const Broken = () => { throw new Error('chunk unavailable'); };
  render(<RouteBoundary><Broken /></RouteBoundary>);
  expect(screen.getByRole('alert')).toHaveTextContent('This page could not load');
  expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument();
  expect(reportError).toHaveBeenCalledWith(expect.any(Error), expect.objectContaining({
    extra: expect.objectContaining({ componentStack: expect.any(String) }),
  }));
  window.removeEventListener('error', suppressExpected);
  log.mockRestore();
});
