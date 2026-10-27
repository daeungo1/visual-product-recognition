import { mulberry32 } from '../../assets/ar/features.js';

/** Multi-scale value noise in [0, 255], similar in character to the synthetic scenario backgrounds. */
export function noiseImage(width, height, seed, scales = [64, 32, 16, 8], contrast = 2.2) {
  const rng = mulberry32(seed);
  const out = new Float32Array(width * height);
  let weightSum = 0;
  scales.forEach((scale, level) => {
    const cols = Math.ceil(width / scale) + 2, rows = Math.ceil(height / scale) + 2;
    const grid = new Float32Array(cols * rows);
    for (let i = 0; i < grid.length; i++) grid[i] = rng();
    const weight = 1 / (1 + level * 0.35);
    weightSum += weight;
    for (let y = 0; y < height; y++) {
      const gy = y / scale, y0 = Math.floor(gy), fy = gy - y0;
      for (let x = 0; x < width; x++) {
        const gx = x / scale, x0 = Math.floor(gx), fx = gx - x0;
        const a = grid[y0 * cols + x0], b = grid[y0 * cols + x0 + 1];
        const c = grid[(y0 + 1) * cols + x0], d = grid[(y0 + 1) * cols + x0 + 1];
        out[y * width + x] += weight * ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy);
      }
    }
  });
  const gray = new Uint8Array(width * height);
  for (let i = 0; i < gray.length; i++) {
    const v = (out[i] / weightSum - 0.5) * contrast + 0.5;
    gray[i] = Math.max(0, Math.min(255, Math.round(v * 255)));
  }
  return gray;
}

export function rotate90(gray, width, height) {
  const out = new Uint8Array(width * height);
  // Clockwise: source (x, y) lands at (height - 1 - y, x) in an image of size height x width.
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) out[x * height + (height - 1 - y)] = gray[y * width + x];
  }
  return { gray: out, width: height, height: width };
}
