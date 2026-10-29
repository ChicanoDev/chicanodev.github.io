export type Point = [number, number];

export interface Ridgeline {
  width: number;
  height: number;
  rows: Point[][];
}

export interface RidgelineOptions {
  rows?: number;
  samples?: number;
  width?: number;
  height?: number;
}

// mulberry32: tiny seeded PRNG so the build output is stable.
function random(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round = (value: number) => Math.round(value * 10) / 10;

// Stacked pulse rows with spikes bunched toward the middle. Row 0 is the
// back (top) row, so later rows can be filled to hide the ones behind them.
export function ridgeline(seed: number, options: RidgelineOptions = {}): Ridgeline {
  const { rows = 18, samples = 60, width = 480, height = 360 } = options;
  const next = random(seed);
  const top = height * 0.12;
  const step = (height - top - 4) / Math.max(1, rows - 1);
  const maxRise = height * 0.3;
  const sigma = width * 0.17;

  const out: Point[][] = [];
  for (let r = 0; r < rows; r += 1) {
    const base = top + r * step;
    const rise = Math.min(maxRise, base);
    const row: Point[] = [];
    for (let s = 0; s < samples; s += 1) {
      const x = (s / (samples - 1)) * width;
      const envelope = Math.exp(-(((x - width / 2) / sigma) ** 2) / 2);
      const noise = 0.35 + 0.65 * next();
      row.push([round(x), round(base - rise * envelope * noise)]);
    }
    out.push(row);
  }
  return { width, height, rows: out };
}
