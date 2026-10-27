// Feature extraction: FAST-9 corners, intensity-centroid orientation and steered BRIEF-256 descriptors.
// Pure typed-array code with no DOM access so the same module runs in browsers and in Node tests.
import { blur7, intensityRange } from './image.js';

export const DESCRIPTOR_WORDS = 8;
export const FEATURE_MARGIN = 16;

const HALF_PATCH = 15;
const PATTERN_PAIRS = DESCRIPTOR_WORDS * 32;
const MAX_CANDIDATES = 40000;

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Fixed seeded Gaussian sampling pattern; the same pattern describes references and frames.
const PATTERN = (() => {
  const rng = mulberry32(0x5eed1234);
  const gaussian = () => Math.sqrt(-2 * Math.log(Math.max(rng(), 1e-12))) * Math.cos(2 * Math.PI * rng());
  const pattern = new Float32Array(PATTERN_PAIRS * 4);
  for (let i = 0; i < PATTERN_PAIRS; i++) {
    let x1, y1, x2, y2;
    do {
      x1 = gaussian() * 5.5; y1 = gaussian() * 5.5;
      x2 = gaussian() * 5.5; y2 = gaussian() * 5.5;
    } while (
      x1 * x1 + y1 * y1 > 13.5 * 13.5 || x2 * x2 + y2 * y2 > 13.5 * 13.5
      || (x1 - x2) * (x1 - x2) + (y1 - y2) * (y1 - y2) < 9
    );
    pattern.set([x1, y1, x2, y2], i * 4);
  }
  return pattern;
})();

const UMAX = (() => {
  const umax = new Int32Array(HALF_PATCH + 2);
  const vmax = Math.floor(HALF_PATCH * Math.SQRT1_2 + 1);
  const vmin = Math.ceil(HALF_PATCH * Math.SQRT1_2);
  for (let v = 0; v <= vmax; v++) umax[v] = Math.round(Math.sqrt(HALF_PATCH * HALF_PATCH - v * v));
  for (let v = HALF_PATCH, v0 = 0; v >= vmin; --v) {
    while (umax[v0] === umax[v0 + 1]) ++v0;
    umax[v] = v0;
    ++v0;
  }
  return umax;
})();

const CIRCLE = [
  [0, -3], [1, -3], [2, -2], [3, -1], [3, 0], [3, 1], [2, 2], [1, 3],
  [0, 3], [-1, 3], [-2, 2], [-3, 1], [-3, 0], [-3, -1], [-2, -2], [-1, -3],
];

function hasRunOfNine(mask) {
  const m = (mask | (mask << 16)) >>> 0;
  let r = m & (m >>> 1);
  r &= r >>> 2;
  r &= r >>> 4;
  r &= m >>> 8;
  return r !== 0;
}

export function autoThreshold(gray) {
  const { low, high } = intensityRange(gray);
  return Math.max(8, Math.min(28, Math.round(0.1 * (high - low))));
}

export class FeatureExtractor {
  constructor() {
    this.width = 0;
    this.height = 0;
  }

  ensure(width, height) {
    if (this.width === width && this.height === height) return;
    this.width = width;
    this.height = height;
    this.blurred = new Uint8Array(width * height);
    this.scratch = new Uint16Array(width * height);
    this.scoreMap = new Uint16Array(width * height);
    this.candidateIndex = new Int32Array(MAX_CANDIDATES);
    this.offsets = Int32Array.from(CIRCLE, ([dx, dy]) => dy * width + dx);
  }

  /**
   * Detect, orient and describe up to `maxKeypoints` corners of a grayscale image.
   * Keypoints are spread over `cellSize` cells (at most `perCell` each) so a textured background cannot
   * crowd out the tracked target.
   */
  extract(gray, width, height, options = {}) {
    const {
      maxKeypoints = 250, cellSize = 24, perCell = 5, threshold = 0, margin = FEATURE_MARGIN,
    } = options;
    this.ensure(width, height);
    const image = blur7(gray, width, height, this.blurred, this.scratch);
    const t = threshold > 0 ? threshold : autoThreshold(image);
    const candidates = this.detect(image, width, height, t, margin);
    const selected = this.select(candidates, width, height, maxKeypoints, cellSize, perCell);
    const count = selected.length;
    const xs = new Float32Array(count), ys = new Float32Array(count);
    const angles = new Float32Array(count), scores = new Uint16Array(count);
    const descriptors = new Uint32Array(count * DESCRIPTOR_WORDS);
    for (let k = 0; k < count; k++) {
      const c = selected[k];
      const x = candidates.xs[c], y = candidates.ys[c];
      const angle = intensityCentroidAngle(image, width, x, y);
      xs[k] = x; ys[k] = y; angles[k] = angle; scores[k] = candidates.scores[c];
      describe(image, width, x, y, Math.cos(angle), Math.sin(angle), descriptors, k * DESCRIPTOR_WORDS);
    }
    return { count, xs, ys, angles, scores, descriptors, threshold: t };
  }

  detect(image, width, height, t, margin) {
    const { scoreMap, offsets, candidateIndex: idx } = this;
    scoreMap.fill(0);
    let n = 0;
    const o = offsets;
    const o0 = o[0], o4 = o[4], o8 = o[8], o12 = o[12];
    for (let y = margin; y < height - margin; y++) {
      const row = y * width;
      for (let x = margin; x < width - margin; x++) {
        const i = row + x;
        const p = image[i];
        const hi = p + t, lo = p - t;
        const a = image[i + o0], b = image[i + o4], c = image[i + o8], d = image[i + o12];
        const bright = (a > hi ? 1 : 0) + (b > hi ? 1 : 0) + (c > hi ? 1 : 0) + (d > hi ? 1 : 0);
        const dark = (a < lo ? 1 : 0) + (b < lo ? 1 : 0) + (c < lo ? 1 : 0) + (d < lo ? 1 : 0);
        if (bright < 2 && dark < 2) continue;
        let bm = 0, dm = 0, sb = 0, sd = 0;
        for (let k = 0; k < 16; k++) {
          const v = image[i + o[k]];
          if (v > hi) { bm |= 1 << k; sb += v - hi; } else if (v < lo) { dm |= 1 << k; sd += lo - v; }
        }
        let score = 0;
        if (bright >= 2 && hasRunOfNine(bm)) score = sb;
        if (dark >= 2 && hasRunOfNine(dm) && sd > score) score = sd;
        if (score > 0 && n < MAX_CANDIDATES) {
          scoreMap[i] = Math.min(65535, score + 1);
          idx[n++] = i;
        }
      }
    }
    // 3x3 non-maximum suppression; ties resolve toward the earlier pixel in scan order.
    const xs = new Int16Array(n), ys = new Int16Array(n), scores = new Uint16Array(n);
    let kept = 0;
    for (let q = 0; q < n; q++) {
      const i = idx[q];
      const s = scoreMap[i];
      if (s <= scoreMap[i - 1] || s <= scoreMap[i - width] || s <= scoreMap[i - width - 1]
        || s <= scoreMap[i - width + 1]) continue;
      if (s < scoreMap[i + 1] || s < scoreMap[i + width] || s < scoreMap[i + width - 1]
        || s < scoreMap[i + width + 1]) continue;
      xs[kept] = i % width; ys[kept] = (i / width) | 0; scores[kept] = s - 1;
      kept++;
    }
    return { count: kept, xs, ys, scores };
  }

  select(candidates, width, height, maxKeypoints, cellSize, perCell) {
    const n = candidates.count;
    const packed = new Uint32Array(n);
    for (let c = 0; c < n; c++) packed[c] = Math.min(4095, candidates.scores[c]) * 1048576 + c;
    packed.sort();
    const cols = Math.ceil(width / cellSize);
    const cells = new Uint8Array(cols * Math.ceil(height / cellSize));
    const selected = [];
    for (let q = n - 1; q >= 0 && selected.length < maxKeypoints; q--) {
      const c = packed[q] & 0xfffff;
      const cell = ((candidates.ys[c] / cellSize) | 0) * cols + ((candidates.xs[c] / cellSize) | 0);
      if (cells[cell] >= perCell) continue;
      cells[cell]++;
      selected.push(c);
    }
    return selected;
  }
}

function intensityCentroidAngle(image, width, x, y) {
  const center = y * width + x;
  let m01 = 0, m10 = 0;
  for (let u = -HALF_PATCH; u <= HALF_PATCH; u++) m10 += u * image[center + u];
  for (let v = 1; v <= HALF_PATCH; v++) {
    let vsum = 0;
    const d = UMAX[v];
    for (let u = -d; u <= d; u++) {
      const plus = image[center + u + v * width], minus = image[center + u - v * width];
      vsum += plus - minus;
      m10 += u * (plus + minus);
    }
    m01 += v * vsum;
  }
  return Math.atan2(m01, m10);
}

function describe(image, width, x, y, cos, sin, out, offset) {
  for (let word = 0; word < DESCRIPTOR_WORDS; word++) {
    let bits = 0;
    for (let bit = 0; bit < 32; bit++) {
      const p = (word * 32 + bit) * 4;
      const ax = PATTERN[p], ay = PATTERN[p + 1], bx = PATTERN[p + 2], by = PATTERN[p + 3];
      const ia = image[((y + sin * ax + cos * ay + 0.5) | 0) * width + ((x + cos * ax - sin * ay + 0.5) | 0)];
      const ib = image[((y + sin * bx + cos * by + 0.5) | 0) * width + ((x + cos * bx - sin * by + 0.5) | 0)];
      if (ia < ib) bits |= 1 << bit;
    }
    out[offset + word] = bits >>> 0;
  }
}

export function popcount32(value) {
  let v = value - ((value >>> 1) & 0x55555555);
  v = (v & 0x33333333) + ((v >>> 2) & 0x33333333);
  return Math.imul((v + (v >>> 4)) & 0x0f0f0f0f, 0x01010101) >>> 24;
}

export function hamming(a, offsetA, b, offsetB) {
  let sum = 0;
  for (let w = 0; w < DESCRIPTOR_WORDS; w++) sum += popcount32((a[offsetA + w] ^ b[offsetB + w]) >>> 0);
  return sum;
}
