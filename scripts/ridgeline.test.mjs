import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ridgeline } from '../src/lib/ridgeline.ts';

test('same seed gives the same ridgeline', () => {
  assert.deepEqual(ridgeline(7), ridgeline(7));
});

test('different seeds give different ridgelines', () => {
  assert.notDeepEqual(ridgeline(7), ridgeline(8));
});

test('returns the requested number of rows and samples', () => {
  const { rows } = ridgeline(7, { rows: 12, samples: 40 });
  assert.equal(rows.length, 12);
  for (const row of rows) assert.equal(row.length, 40);
});

test('every point stays inside the viewBox', () => {
  const { width, height, rows } = ridgeline(7, { width: 480, height: 360 });
  for (const row of rows) {
    for (const [x, y] of row) {
      assert.ok(x >= 0 && x <= width, `x ${x} outside 0..${width}`);
      assert.ok(y >= 0 && y <= height, `y ${y} outside 0..${height}`);
    }
  }
});

test('peaks are tallest near the centre of each row', () => {
  const { rows } = ridgeline(7, { rows: 10, samples: 61 });
  let centreWins = 0;
  for (const row of rows) {
    const base = Math.max(...row.map(([, y]) => y));
    const rise = (i) => base - row[i][1];
    const centre = Math.max(rise(28), rise(29), rise(30), rise(31), rise(32));
    const edge = Math.max(rise(0), rise(1), rise(2), rise(58), rise(59), rise(60));
    if (centre > edge) centreWins += 1;
  }
  assert.ok(centreWins >= 9, `centre taller in ${centreWins}/10 rows`);
});
