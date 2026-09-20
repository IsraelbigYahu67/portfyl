import { splitGrowthLineSegments } from './growthLineSegments';

describe('splitGrowthLineSegments', () => {
  it('keeps lines above and below zero in their respective colors', () => {
    expect(splitGrowthLineSegments([
      { x: 0, y: 30, value: 4 },
      { x: 10, y: 50, value: 2 },
      { x: 20, y: 140, value: -3 },
    ], 100)).toEqual([
      { x1: 0, y1: 30, x2: 10, y2: 50, isGain: true },
      { x1: 10, y1: 50, x2: 14, y2: 100, isGain: true },
      { x1: 14, y1: 100, x2: 20, y2: 140, isGain: false },
    ]);
  });

  it('breaks rather than joining across missing values', () => {
    expect(splitGrowthLineSegments([
      { x: 0, y: 50, value: 2 },
      { x: 10, y: 100, value: null },
      { x: 20, y: 130, value: -2 },
    ], 100)).toEqual([]);
  });
});
