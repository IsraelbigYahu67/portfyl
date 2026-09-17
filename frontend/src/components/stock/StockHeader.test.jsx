import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StockHeader } from './StockHeader';

it('exposes the persistent stock identity as the page heading for route focus', () => {
  render(<MemoryRouter><StockHeader data={{ ticker: 'AAPL', name: 'Apple', currency: 'USD', price: 200 }} /></MemoryRouter>);
  expect(screen.getByRole('heading', { level: 1, name: 'AAPL' })).toBeInTheDocument();
});
