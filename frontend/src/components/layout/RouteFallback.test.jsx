import { render, screen } from '@testing-library/react';
import RouteFallback from './RouteFallback';
it('announces loading while a route chunk arrives', () => {
  render(<RouteFallback />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading page');
});
