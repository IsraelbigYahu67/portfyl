import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TickerLink } from './TickerLink';
const intent = vi.hoisted(() => ({ onMouseEnter: vi.fn(), onMouseLeave: vi.fn(), onFocus: vi.fn(), onBlur: vi.fn() }));
vi.mock('../hooks/useStockIntentPrefetch', () => ({ useStockIntentPrefetch: () => intent }));
it('keeps a real encoded uppercase anchor and forwards props and intent', () => {
  const extra = vi.fn();
  render(<MemoryRouter><TickerLink ticker="brk/b" target="_blank" aria-label="Company" onFocus={extra}><strong>Research</strong></TickerLink></MemoryRouter>);
  const anchor = screen.getByRole('link', { name: 'Company' });
  expect(anchor).toHaveAttribute('href', '/stock/BRK%2FB');
  expect(anchor).toHaveAttribute('target', '_blank');
  fireEvent.focus(anchor);
  expect(intent.onFocus).toHaveBeenCalled();
  expect(extra).toHaveBeenCalled();
});
