// Natural-feature image-target tracker. Registered targets are described by multi-scale ORB-like features;
// every frame is matched against them and a planar homography (reference pixels -> frame pixels) is fitted
// with RANSAC. Pure JavaScript with no DOM, WASM or network access.
import {
  DESCRIPTOR_WORDS, FEATURE_MARGIN, FeatureExtractor, mulberry32, popcount32,
} from './features.js';
import {
  estimateHomography, isConvexClockwise, polygonArea, projectRect,
} from './geometry.js';
import { resizeGray } from './image.js';

export const DEFAULT_OPTIONS = Object.freeze({
  seed: 20260511,
  levels: 7,
  levelRatio: 0.8,
  referenceKeypointsPerLevel: 110,
  frameKeypoints: 250,
  frameCellSize: 24,
  framePerCell: 5,
  minFrameKeypoints: 30,
  ratio: 0.8,
  maxDistance: 80,
  prefilterDistance: 24,
  sameLocation: 7,
  minMatches: 8,
  inlierThreshold: 3.5,
  scanIterations: 500,
  trackIterations: 150,
  minInliersAcquire: 16,
  minInliersTrack: 10,
  // Guided tracking is a fast path that must be confident: the pose has to explain this share of the reference
  // keypoints expected to be visible. A different product with the same panel layout explains up to ~0.19 in
  // synthetic measurements, the correct product at least ~0.22 even when blurred. Uncertain frames fall through to
  // a full scan, which decides identity.
  minFractionTrack: 0.25,
  guidedRadius: 18,
  guidedRatio: 0.9,
  guidedMaxDistance: 90,
  scaleTolerance: 1.35,
  ambiguityRatio: 0.7,
  maxTrackMisses: 2,
  minCoverage: 0.08,
  minAreaFraction: 0.04,
  maxAreaFraction: 6,
});

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

function countInliers(H, sx, sy, dx, dy, n, thresholdSquared, mask) {
  let count = 0;
  const h0 = H[0], h1 = H[1], h2 = H[2], h3 = H[3], h4 = H[4], h5 = H[5], h6 = H[6], h7 = H[7], h8 = H[8];
  for (let i = 0; i < n; i++) {
    const x = sx[i], y = sy[i];
    const w = h6 * x + h7 * y + h8;
    let inlier = 0;
    if (w > 1e-9) {
      const ex = (h0 * x + h1 * y + h2) / w - dx[i];
      const ey = (h3 * x + h4 * y + h5) / w - dy[i];
      if (ex * ex + ey * ey <= thresholdSquared) inlier = 1;
    }
    if (mask) mask[i] = inlier;
    count += inlier;
  }
  return count;
}

function cross(ax, ay, bx, by, cx, cy) {
  return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

const TRIPLES = [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]];

/** True when the four correspondences are well separated and keep the same orientation in both images. */
function validSample(sx, sy, dx, dy, s, minSource, minTarget) {
  for (let a = 0; a < 4; a++) {
    for (let b = a + 1; b < 4; b++) {
      if (Math.hypot(sx[s[a]] - sx[s[b]], sy[s[a]] - sy[s[b]]) < minSource) return false;
      if (Math.hypot(dx[s[a]] - dx[s[b]], dy[s[a]] - dy[s[b]]) < minTarget) return false;
    }
  }
  for (const [a, b, c] of TRIPLES) {
    const cs = cross(sx[s[a]], sy[s[a]], sx[s[b]], sy[s[b]], sx[s[c]], sy[s[c]]);
    const cd = cross(dx[s[a]], dy[s[a]], dx[s[b]], dy[s[b]], dx[s[c]], dy[s[c]]);
    if (Math.abs(cs) < 4 * minSource || Math.abs(cd) < 4 * minTarget || (cs > 0) !== (cd > 0)) return false;
  }
  return true;
}

export class ImageTargetTracker {
  constructor(options = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.extractor = new FeatureExtractor();
    this.referenceExtractor = new FeatureExtractor();
    this.targets = new Map();
    this.track = null;
    this.rng = mulberry32(this.options.seed);
  }

  /** Register a grayscale reference image. Coordinates of all poses are in this image's pixels. */
  addTarget(id, gray, width, height) {
    const o = this.options;
    const xs = [], ys = [], scales = [], words = [];
    for (let level = 0; level < o.levels; level++) {
      const w = Math.round(width * Math.pow(o.levelRatio, level));
      const h = Math.round(height * Math.pow(o.levelRatio, level));
      if (Math.min(w, h) < 64) break;
      const image = level === 0 ? gray : resizeGray(gray, width, height, w, h);
      const cellSize = Math.max(14, Math.round(Math.sqrt((w * h) / (o.referenceKeypointsPerLevel / 2))));
      const features = this.referenceExtractor.extract(image, w, h, {
        maxKeypoints: o.referenceKeypointsPerLevel, cellSize, perCell: 3,
      });
      for (let k = 0; k < features.count; k++) {
        xs.push((features.xs[k] + 0.5) * (width / w) - 0.5);
        ys.push((features.ys[k] + 0.5) * (height / h) - 0.5);
        scales.push(w / width);
        for (let b = 0; b < DESCRIPTOR_WORDS; b++) words.push(features.descriptors[k * DESCRIPTOR_WORDS + b]);
      }
    }
    const model = {
      id, width, height, count: xs.length,
      xs: Float32Array.from(xs), ys: Float32Array.from(ys), scales: Float32Array.from(scales),
      descriptors: Uint32Array.from(words),
    };
    this.targets.set(id, model);
    return model;
  }

  hasTarget(id) { return this.targets.has(id); }

  reset() { this.track = null; }

  /** Keypoints and descriptors of a camera frame, in the form every matching step consumes. */
  describeFrame(gray, width, height) {
    const o = this.options;
    return this.extractor.extract(gray, width, height, {
      maxKeypoints: o.frameKeypoints, cellSize: o.frameCellSize, perCell: o.framePerCell,
    });
  }

  process(gray, width, height) {
    const o = this.options;
    const timings = {};
    const t0 = now();
    const frame = this.describeFrame(gray, width, height);
    timings.features = now() - t0;
    const result = {
      status: 'none', targetId: null, H: null, quad: null, inliers: 0, matches: 0, fraction: 0,
      candidates: [], keypoints: frame.count, mode: 'scan', timings,
    };
    if (frame.count < o.minFrameKeypoints) {
      this.noteMiss();
      return result;
    }
    if (this.track && this.targets.has(this.track.id)) {
      const t1 = now();
      const model = this.targets.get(this.track.id);
      const pose = this.trackGuided(frame, model, width, height);
      timings.guided = now() - t1;
      if (pose) {
        this.track = { id: model.id, H: pose.H, misses: 0 };
        return this.accept(result, model, pose, 'track');
      }
      this.noteMiss();
    }
    const t2 = now();
    const candidates = this.scan(frame, width, height);
    timings.scan = now() - t2;
    result.candidates = candidates.map((c) => ({
      id: c.id, matches: c.matches, inliers: c.inliers, fraction: c.pose ? c.pose.fraction : 0,
    }));
    const best = candidates[0];
    if (!best || !best.pose || best.inliers < o.minInliersAcquire) return result;
    const rival = candidates[1];
    if (rival && rival.inliers >= Math.max(o.minInliersTrack, o.ambiguityRatio * best.inliers)) {
      result.status = 'ambiguous';
      return result;
    }
    this.track = { id: best.id, H: best.pose.H, misses: 0 };
    return this.accept(result, this.targets.get(best.id), best.pose, 'scan');
  }

  noteMiss() {
    if (!this.track) return;
    this.track.misses++;
    if (this.track.misses > this.options.maxTrackMisses) this.track = null;
  }

  accept(result, model, pose, mode) {
    result.status = 'tracked';
    result.targetId = model.id;
    result.H = pose.H;
    result.quad = pose.quad;
    result.inliers = pose.inliers;
    result.matches = pose.matches;
    result.fraction = pose.fraction;
    result.mode = mode;
    return result;
  }

  /** Match the frame against every registered target and fit a pose to each. Sorted by inlier count. */
  scan(frame, width, height) {
    const o = this.options;
    const candidates = [];
    for (const model of this.targets.values()) {
      const matches = this.matchGlobal(frame, model);
      const entry = { id: model.id, matches: matches.count, inliers: 0, pose: null };
      if (matches.count >= o.minMatches) {
        entry.pose = this.fit(matches, model, width, height, o.scanIterations);
        if (entry.pose) entry.inliers = entry.pose.inliers;
      }
      candidates.push(entry);
    }
    candidates.sort((a, b) => b.inliers - a.inliers);
    return candidates;
  }

  /** Brute-force matching with a Hamming prefilter, a location-aware ratio test and one-to-one filtering. */
  matchGlobal(frame, model) {
    const o = this.options;
    const fd = frame.descriptors, rd = model.descriptors;
    const rx = model.xs, ry = model.ys;
    const rCount = model.count;
    const owner = new Int32Array(rCount).fill(-1);
    const ownerDistance = new Int16Array(rCount);
    const matchedRef = new Int32Array(frame.count).fill(-1);
    const matchedDistance = new Int16Array(frame.count);
    const same = o.sameLocation;
    for (let f = 0; f < frame.count; f++) {
      const fo = f * DESCRIPTOR_WORDS;
      const f0 = fd[fo], f1 = fd[fo + 1], f2 = fd[fo + 2], f3 = fd[fo + 3];
      const f4 = fd[fo + 4], f5 = fd[fo + 5], f6 = fd[fo + 6], f7 = fd[fo + 7];
      let best = 1 << 20, second = 100, bestIndex = -1;
      for (let r = 0; r < rCount; r++) {
        const ro = r * DESCRIPTOR_WORDS;
        let d = popcount32((f0 ^ rd[ro]) >>> 0) + popcount32((f1 ^ rd[ro + 1]) >>> 0);
        if (d > o.prefilterDistance) continue;
        d += popcount32((f2 ^ rd[ro + 2]) >>> 0) + popcount32((f3 ^ rd[ro + 3]) >>> 0)
          + popcount32((f4 ^ rd[ro + 4]) >>> 0) + popcount32((f5 ^ rd[ro + 5]) >>> 0)
          + popcount32((f6 ^ rd[ro + 6]) >>> 0) + popcount32((f7 ^ rd[ro + 7]) >>> 0);
        if (d < best) {
          const near = bestIndex >= 0 && Math.abs(rx[r] - rx[bestIndex]) < same && Math.abs(ry[r] - ry[bestIndex]) < same;
          if (!near) second = Math.min(second, best);
          best = d;
          bestIndex = r;
        } else if (d < second) {
          if (!(Math.abs(rx[r] - rx[bestIndex]) < same && Math.abs(ry[r] - ry[bestIndex]) < same)) second = d;
        }
      }
      if (bestIndex < 0 || best > o.maxDistance || !(best < o.ratio * second)) continue;
      matchedRef[f] = bestIndex;
      matchedDistance[f] = best;
      if (owner[bestIndex] < 0 || best < ownerDistance[bestIndex]) {
        owner[bestIndex] = f;
        ownerDistance[bestIndex] = best;
      }
    }
    return this.collect(frame, model, matchedRef, matchedDistance, owner);
  }

  /** Match only reference points predicted near each frame keypoint by the previous pose. */
  matchGuided(frame, model, H, width, height, radius) {
    const o = this.options;
    const fd = frame.descriptors, rd = model.descriptors;
    const rx = model.xs, ry = model.ys;
    const keep = [];
    const px = [], py = [];
    for (let r = 0; r < model.count; r++) {
      const x = rx[r], y = ry[r];
      const w = H[6] * x + H[7] * y + H[8];
      if (!(w > 1e-9)) continue;
      const u = (H[0] * x + H[1] * y + H[2]) / w, v = (H[3] * x + H[4] * y + H[5]) / w;
      if (u < -radius || u > width + radius || v < -radius || v > height + radius) continue;
      const a = (H[0] - u * H[6]) / w, b = (H[1] - u * H[7]) / w;
      const c = (H[3] - v * H[6]) / w, d = (H[4] - v * H[7]) / w;
      const ratio = Math.sqrt(Math.abs(a * d - b * c)) / model.scales[r];
      if (ratio < 1 / o.scaleTolerance || ratio > o.scaleTolerance) continue;
      keep.push(r); px.push(u); py.push(v);
    }
    const radiusSquared = radius * radius;
    const same = o.sameLocation;
    const owner = new Int32Array(model.count).fill(-1);
    const ownerDistance = new Int16Array(model.count);
    const matchedRef = new Int32Array(frame.count).fill(-1);
    const matchedDistance = new Int16Array(frame.count);
    for (let f = 0; f < frame.count; f++) {
      const fx = frame.xs[f], fy = frame.ys[f], fo = f * DESCRIPTOR_WORDS;
      let best = 1 << 20, second = 1 << 20, bestIndex = -1;
      for (let k = 0; k < keep.length; k++) {
        const ex = px[k] - fx, ey = py[k] - fy;
        if (ex * ex + ey * ey > radiusSquared) continue;
        const r = keep[k], ro = r * DESCRIPTOR_WORDS;
        let dist = 0;
        for (let w = 0; w < DESCRIPTOR_WORDS; w++) dist += popcount32((fd[fo + w] ^ rd[ro + w]) >>> 0);
        if (dist < best) {
          const near = bestIndex >= 0 && Math.abs(rx[r] - rx[bestIndex]) < same && Math.abs(ry[r] - ry[bestIndex]) < same;
          if (!near) second = best;
          best = dist;
          bestIndex = r;
        } else if (dist < second
          && !(Math.abs(rx[r] - rx[bestIndex]) < same && Math.abs(ry[r] - ry[bestIndex]) < same)) {
          second = dist;
        }
      }
      if (bestIndex < 0 || best > o.guidedMaxDistance) continue;
      if (second < (1 << 20) && !(best < o.guidedRatio * second)) continue;
      matchedRef[f] = bestIndex;
      matchedDistance[f] = best;
      if (owner[bestIndex] < 0 || best < ownerDistance[bestIndex]) {
        owner[bestIndex] = f;
        ownerDistance[bestIndex] = best;
      }
    }
    return this.collect(frame, model, matchedRef, matchedDistance, owner);
  }

  collect(frame, model, matchedRef, matchedDistance, owner) {
    const order = [];
    for (let f = 0; f < frame.count; f++) {
      const r = matchedRef[f];
      if (r >= 0 && owner[r] === f) order.push(matchedDistance[f] * 65536 + f);
    }
    order.sort((a, b) => a - b);
    const count = order.length;
    const sx = new Float32Array(count), sy = new Float32Array(count);
    const dx = new Float32Array(count), dy = new Float32Array(count), distance = new Uint16Array(count);
    for (let i = 0; i < count; i++) {
      const f = order[i] % 65536;
      const r = matchedRef[f];
      sx[i] = model.xs[r]; sy[i] = model.ys[r];
      dx[i] = frame.xs[f]; dy[i] = frame.ys[f];
      distance[i] = matchedDistance[f];
    }
    return { count, sx, sy, dx, dy, distance };
  }

  trackGuided(frame, model, width, height) {
    const o = this.options;
    const matches = this.matchGuided(frame, model, this.track.H, width, height, o.guidedRadius);
    if (matches.count < o.minInliersTrack) return null;
    const pose = this.fit(matches, model, width, height, o.trackIterations);
    return pose && pose.inliers >= o.minInliersTrack && pose.fraction >= o.minFractionTrack ? pose : null;
  }

  /** RANSAC with progressively growing sample pool, local least-squares refinement and geometric checks. */
  fit(matches, model, frameWidth, frameHeight, maxIterations) {
    const o = this.options;
    const n = matches.count;
    const { sx, sy, dx, dy } = matches;
    const thresholdSquared = o.inlierThreshold * o.inlierThreshold;
    const sample = new Int32Array(4);
    const H = new Float64Array(9);
    let bestH = null, bestCount = 3;
    let limit = maxIterations;
    const minSource = 0.04 * Math.min(model.width, model.height);
    for (let iteration = 0; iteration < limit; iteration++) {
      const pool = Math.min(n, 8 + Math.floor(((n - 8) * iteration) / (0.7 * maxIterations)));
      if (pool < 4) break;
      for (let k = 0; k < 4; k++) {
        let candidate, tries = 0;
        do { candidate = Math.floor(this.rng() * pool); tries++; } while (tries < 12 && sample.subarray(0, k).includes(candidate));
        sample[k] = candidate;
      }
      if (new Set(sample).size < 4) continue;
      if (!validSample(sx, sy, dx, dy, sample, minSource, 3)) continue;
      if (!estimateHomography(sx, sy, dx, dy, sample, 4, H)) continue;
      if (!this.plausible(H, model, frameWidth, frameHeight)) continue;
      const count = countInliers(H, sx, sy, dx, dy, n, thresholdSquared, null);
      if (count > bestCount) {
        bestCount = count;
        bestH = Float64Array.from(H);
        const w = count / n;
        const needed = w >= 1 ? 1 : Math.ceil(Math.log(0.005) / Math.log(1 - Math.pow(w, 4)));
        limit = Math.min(limit, Math.max(40, needed));
      }
    }
    if (!bestH) return null;
    const mask = new Uint8Array(n);
    const refined = this.refine(bestH, matches, thresholdSquared, mask);
    if (!refined) return null;
    const quad = this.plausible(refined.H, model, frameWidth, frameHeight);
    if (!quad || !this.covered(matches, mask, model)) return null;
    const visible = this.expectedVisible(refined.H, model, frameWidth, frameHeight);
    return {
      H: refined.H, quad, inliers: refined.count, matches: n, visible, fraction: refined.count / Math.max(visible, 1),
    };
  }

  /** Reference keypoints a correct pose should be able to match: inside the usable frame area at a compatible scale. */
  expectedVisible(H, model, width, height) {
    const tolerance = this.options.scaleTolerance;
    let count = 0;
    for (let r = 0; r < model.count; r++) {
      const x = model.xs[r], y = model.ys[r];
      const w = H[6] * x + H[7] * y + H[8];
      if (!(w > 1e-9)) continue;
      const u = (H[0] * x + H[1] * y + H[2]) / w, v = (H[3] * x + H[4] * y + H[5]) / w;
      if (u < FEATURE_MARGIN || u > width - FEATURE_MARGIN || v < FEATURE_MARGIN || v > height - FEATURE_MARGIN) continue;
      const a = (H[0] - u * H[6]) / w, b = (H[1] - u * H[7]) / w;
      const c = (H[3] - v * H[6]) / w, d = (H[4] - v * H[7]) / w;
      const ratio = Math.sqrt(Math.abs(a * d - b * c)) / model.scales[r];
      if (ratio >= 1 / tolerance && ratio <= tolerance) count++;
    }
    return count;
  }

  refine(H, matches, thresholdSquared, mask) {
    const { sx, sy, dx, dy, count: n } = matches;
    let current = H;
    let currentCount = countInliers(current, sx, sy, dx, dy, n, thresholdSquared, mask);
    for (let pass = 0; pass < 3; pass++) {
      const indices = new Int32Array(currentCount);
      for (let i = 0, k = 0; i < n; i++) if (mask[i]) indices[k++] = i;
      const next = new Float64Array(9);
      if (currentCount < 4 || !estimateHomography(sx, sy, dx, dy, indices, currentCount, next)) break;
      const nextMask = new Uint8Array(n);
      const nextCount = countInliers(next, sx, sy, dx, dy, n, thresholdSquared, nextMask);
      if (nextCount < currentCount) break;
      const improved = nextCount > currentCount;
      current = next; currentCount = nextCount; mask.set(nextMask);
      if (!improved) break;
    }
    return { H: current, count: currentCount };
  }

  covered(matches, mask, model) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (let i = 0; i < matches.count; i++) {
      if (!mask[i]) continue;
      minX = Math.min(minX, matches.sx[i]); maxX = Math.max(maxX, matches.sx[i]);
      minY = Math.min(minY, matches.sy[i]); maxY = Math.max(maxY, matches.sy[i]);
    }
    return (maxX - minX) * (maxY - minY) >= this.options.minCoverage * model.width * model.height;
  }

  /** Returns the projected target quad when the pose is geometrically plausible, otherwise null. */
  plausible(H, model, frameWidth, frameHeight) {
    const o = this.options;
    const quad = projectRect(H, 0, 0, model.width, model.height);
    if (!quad || !isConvexClockwise(quad)) return null;
    const area = polygonArea(quad);
    const frameArea = frameWidth * frameHeight;
    if (area < o.minAreaFraction * frameArea || area > o.maxAreaFraction * frameArea) return null;
    for (const [x, y] of quad) {
      if (x < -1.5 * frameWidth || x > 2.5 * frameWidth || y < -1.5 * frameHeight || y > 2.5 * frameHeight) return null;
    }
    const edge = (a, b) => Math.hypot(quad[a][0] - quad[b][0], quad[a][1] - quad[b][1]);
    const top = edge(0, 1), bottom = edge(3, 2), left = edge(0, 3), right = edge(1, 2);
    if (top > 3 * bottom || bottom > 3 * top || left > 3 * right || right > 3 * left) return null;
    return quad;
  }
}
