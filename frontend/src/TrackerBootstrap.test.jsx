import source from './main.jsx?raw';
import bootstrap from './TrackerBootstrap.jsx?raw';
import root from './Root.jsx?raw';

it('keeps private router and query providers with the tracker instead of the public entry', () => {
  expect(source).not.toMatch(/react-router-dom|@tanstack\/react-query/);
  expect(root).not.toMatch(/react-router-dom|@tanstack\/react-query/);
  expect(bootstrap).toMatch(/BrowserRouter/);
  expect(bootstrap).toMatch(/QueryClientProvider/);
});
