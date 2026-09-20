import { buildPercentAxis } from './chartPercentAxis';

describe('buildPercentAxis', () => {
  it('uses a compact scale for a balanced thirty-percent range', () => {
    expect(buildPercentAxis([-15, 15])).toEqual({
      domain: [-20, 20],
      ticks: [-20, -10, 0, 10, 20],
    });
  });

  it.each([
    [[-12, 14], [-20, -10, 0, 10, 20]],
    [[0, 17], [0, 5, 10, 15, 20]],
    [[-20, -10], [-20, -15, -10, -5, 0]],
    [[2.1, 4.2], [0, 2, 4, 6]],
  ])('rounds %j to uniform whole-percent ticks %j', (values, ticks) => {
    const axis = buildPercentAxis(values);

    expect(axis.ticks).toEqual(ticks);
    expect(axis.domain).toEqual([ticks[0], ticks.at(-1)]);
    expect(axis.ticks.every(Number.isInteger)).toBe(true);
  });

  it('has a readable default scale when no growth data is available', () => {
    expect(buildPercentAxis([null, undefined, NaN, Infinity])).toEqual({
      domain: [-1, 1],
      ticks: [-1, 0, 1],
    });
  });
});
