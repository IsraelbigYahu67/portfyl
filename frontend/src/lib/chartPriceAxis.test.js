import { buildPriceAxis } from './chartPriceAxis';

describe('buildPriceAxis', () => {
  it.each([
    [[100, 140], [100, 110, 120, 130, 140]],
    [[103, 137], [100, 110, 120, 130, 140]],
    [[100, 200], [100, 125, 150, 175, 200]],
    [[100, 300], [100, 150, 200, 250, 300]],
    [[1200, 1600], [1200, 1300, 1400, 1500, 1600]],
    [[102, 106], [102, 103, 104, 105, 106]],
    [[99, 101], [98, 99, 100, 101, 102]],
    [[100, 100], [98, 99, 100, 101, 102]],
    [[0.2, 0.9], [0, 1, 2, 3, 4]],
    [[11, 51], [0, 25, 50, 75, 100]],
  ])('covers prices %j with five equally spaced whole values %j', (prices, expected) => {
    const ticks = buildPriceAxis(prices);
    expect(ticks).toEqual(expected);
    expect(ticks).toHaveLength(5);
    expect(ticks.every(Number.isInteger)).toBe(true);
    expect(ticks[0]).toBeLessThanOrEqual(Math.min(...prices));
    expect(ticks[4]).toBeGreaterThanOrEqual(Math.max(...prices));
    const step = ticks[1] - ticks[0];
    expect(ticks.slice(1).map((tick, i) => tick - ticks[i])).toEqual([step, step, step, step]);
  });

  it('ignores absent and non-finite prices', () => {
    expect(buildPriceAxis([null, undefined, NaN, Infinity, 100, 140])).toEqual([100, 110, 120, 130, 140]);
    expect(buildPriceAxis([])).toEqual([0, 1, 2, 3, 4]);
  });
});
