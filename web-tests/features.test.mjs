import test from 'node:test';
import assert from 'node:assert/strict';
import {
  blur7, intensityRange, resizeGray, rgbaToGray,
} from '../assets/ar/image.js';
import {
  DESCRIPTOR_WORDS, FeatureExtractor, hamming, mulberry32, popcount32,
} from '../assets/ar/features.js';
import { clutterGray } from '../assets/ar/synthetic.js';
import { rotate90 } from './support/textures.mjs';

const noiseImage = (width, height, seed) => clutterGray(width, height, seed);

test('rgbaToGray weights green most and ignores alpha', () => {
  const rgba = Uint8Array.from([255, 0, 0, 7, 0, 255, 0, 7, 0, 0, 255, 7, 255, 255, 255, 0]);
  const gray = rgbaToGray(rgba, 4, 1);
  assert.deepEqual(Array.from(gray), [76, 149, 28, 255]);
});

test('rgbaToGray reuses a larger buffer but never returns its stale tail', () => {
  const reused = new Uint8Array(16).fill(99);
  const rgba = Uint8Array.from([255, 255, 255, 255, 0, 0, 0, 255, 255, 255, 255, 255]);
  const gray = rgbaToGray(rgba, 3, 1, reused);
  assert.equal(gray.length, 3);
  assert.equal(gray.buffer, reused.buffer);
  assert.deepEqual(Array.from(gray), [255, 0, 255]);
  assert.equal(reused[3], 99, 'bytes past the image are untouched');
  const fresh = rgbaToGray(rgba, 3, 1, new Uint8Array(2));
  assert.equal(fresh.length, 3, 'a buffer that is too small is replaced');
  assert.notEqual(fresh.buffer, reused.buffer);
});

test('resizeGray preserves flat images and averages blocks', () => {
  const flat = new Uint8Array(40 * 30).fill(120);
  assert.ok(resizeGray(flat, 40, 30, 32, 24).every((v) => v === 120));
  const source = Uint8Array.from([0, 100, 0, 100, 200, 40, 200, 40]);
  const half = resizeGray(source, 4, 2, 2, 1);
  assert.deepEqual(Array.from(half), [85, 85]);
  assert.throws(() => resizeGray(flat, 40, 30, 41, 30), RangeError);
});

test('blur7 keeps flat images and spreads an impulse without changing its mass much', () => {
  const flat = new Uint8Array(30 * 30).fill(200);
  assert.ok(blur7(flat, 30, 30).every((v) => v === 200));
  const impulse = new Uint8Array(31 * 31);
  impulse[15 * 31 + 15] = 255;
  const blurred = blur7(impulse, 31, 31);
  let sum = 0;
  for (const v of blurred) sum += v;
  assert.ok(Math.abs(sum - 255) <= 40, `mass ${sum}`);
  assert.ok(blurred[15 * 31 + 15] > blurred[15 * 31 + 17]);
});

test('intensityRange reports the 2nd and 98th percentile', () => {
  const gray = new Uint8Array(1000);
  for (let i = 0; i < gray.length; i++) gray[i] = Math.floor((i / 1000) * 200) + 20;
  const { low, high } = intensityRange(gray, 1);
  assert.ok(low >= 22 && low <= 30, `low ${low}`);
  assert.ok(high >= 208 && high <= 218, `high ${high}`);
});

test('popcount32 matches a naive bit count', () => {
  const rng = mulberry32(7);
  for (let i = 0; i < 2000; i++) {
    const value = Math.floor(rng() * 4294967296) >>> 0;
    let expected = 0;
    for (let b = 0; b < 32; b++) expected += (value >>> b) & 1;
    assert.equal(popcount32(value), expected);
  }
  assert.equal(popcount32(0xffffffff), 32);
  assert.equal(popcount32(0), 0);
});

test('feature extraction is deterministic and keeps keypoints away from the border', () => {
  const width = 320, height = 240;
  const gray = noiseImage(width, height, 11);
  const extractor = new FeatureExtractor();
  const first = extractor.extract(gray, width, height);
  const second = new FeatureExtractor().extract(gray, width, height);
  assert.ok(first.count >= 80, `keypoints ${first.count}`);
  assert.ok(first.count <= 250);
  assert.equal(first.count, second.count);
  assert.deepEqual(Array.from(first.descriptors), Array.from(second.descriptors));
  for (let k = 0; k < first.count; k++) {
    assert.ok(first.xs[k] >= 16 && first.xs[k] < width - 16);
    assert.ok(first.ys[k] >= 16 && first.ys[k] < height - 16);
  }
});

test('descriptors are spread out rather than degenerate', () => {
  const width = 320, height = 240;
  const features = new FeatureExtractor().extract(noiseImage(width, height, 21), width, height);
  const distances = [];
  for (let a = 0; a < features.count; a += 3) {
    for (let b = a + 1; b < features.count; b += 5) {
      distances.push(hamming(features.descriptors, a * DESCRIPTOR_WORDS, features.descriptors, b * DESCRIPTOR_WORDS));
    }
  }
  distances.sort((x, y) => x - y);
  const mean = distances.reduce((s, d) => s + d, 0) / distances.length;
  // Real patches are correlated (rectangle corners look alike), so the mean sits below the 128 of random bits.
  assert.ok(mean > 85 && mean < 150, `mean ${mean}`);
  assert.ok(distances[Math.floor(distances.length * 0.95)] > 130, 'descriptor bits should use their full range');
  assert.ok(distances[Math.floor(distances.length * 0.05)] > 30, 'most unrelated pairs should differ clearly');
});

test('descriptors are rotation invariant for a 90 degree turn', () => {
  const width = 320, height = 240;
  const gray = noiseImage(width, height, 31);
  const rotated = rotate90(gray, width, height);
  const a = new FeatureExtractor().extract(gray, width, height, { maxKeypoints: 200 });
  const b = new FeatureExtractor().extract(rotated.gray, rotated.width, rotated.height, { maxKeypoints: 200 });
  const index = new Map();
  for (let k = 0; k < b.count; k++) index.set(`${b.xs[k]},${b.ys[k]}`, k);
  let compared = 0, close = 0;
  for (let k = 0; k < a.count; k++) {
    const rx = height - 1 - a.ys[k], ry = a.xs[k];
    const j = index.get(`${rx},${ry}`);
    if (j === undefined) continue;
    compared++;
    if (hamming(a.descriptors, k * DESCRIPTOR_WORDS, b.descriptors, j * DESCRIPTOR_WORDS) <= 32) close++;
  }
  assert.ok(compared >= 40, `compared ${compared}`);
  assert.ok(close / compared >= 0.85, `close ${close}/${compared}`);
});

test('flat images produce no keypoints', () => {
  const flat = new Uint8Array(200 * 150).fill(90);
  assert.equal(new FeatureExtractor().extract(flat, 200, 150).count, 0);
});
