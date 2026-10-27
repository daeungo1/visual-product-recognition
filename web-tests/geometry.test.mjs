import assert from 'node:assert/strict';
import test from 'node:test';
import {
  depth, estimateHomography, invert3x3, isConvexClockwise, multiply3x3, pointInPolygon,
  polygonArea, project, projectRect,
} from '../assets/ar/geometry.js';

function lcg(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

const TRUTH = new Float64Array([0.82, -0.31, 140, 0.27, 0.91, 60, 0.0004, -0.0002, 1]);

function mapPoints(H, xs, ys) {
  const dx = new Float64Array(xs.length), dy = new Float64Array(xs.length), out = [0, 0];
  for (let i = 0; i < xs.length; i++) {
    assert.ok(project(H, xs[i], ys[i], out));
    dx[i] = out[0]; dy[i] = out[1];
  }
  return [dx, dy];
}

test('four exact correspondences recover the homography', () => {
  const sx = new Float64Array([0, 400, 400, 0]), sy = new Float64Array([0, 0, 640, 640]);
  const [dx, dy] = mapPoints(TRUTH, sx, sy);
  const H = new Float64Array(9);
  assert.ok(estimateHomography(sx, sy, dx, dy, null, 4, H));
  const check = [[30, 40], [370, 600], [200, 320]];
  for (const [x, y] of check) {
    const a = [0, 0], b = [0, 0];
    project(TRUTH, x, y, a); project(H, x, y, b);
    assert.ok(Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6);
  }
});

test('least squares over noisy points stays within sub-pixel error', () => {
  const rng = lcg(7), count = 120;
  const sx = new Float64Array(count), sy = new Float64Array(count);
  for (let i = 0; i < count; i++) { sx[i] = rng() * 400; sy[i] = rng() * 640; }
  const [dx, dy] = mapPoints(TRUTH, sx, sy);
  for (let i = 0; i < count; i++) { dx[i] += (rng() - 0.5) * 1.2; dy[i] += (rng() - 0.5) * 1.2; }
  const H = new Float64Array(9);
  assert.ok(estimateHomography(sx, sy, dx, dy, null, count, H));
  let worst = 0;
  for (const [x, y] of [[0, 0], [400, 0], [400, 640], [0, 640], [200, 320]]) {
    const a = [0, 0], b = [0, 0];
    project(TRUTH, x, y, a); project(H, x, y, b);
    worst = Math.max(worst, Math.hypot(a[0] - b[0], a[1] - b[1]));
  }
  assert.ok(worst < 1.5, `worst corner error ${worst}`);
});

test('degenerate input is refused', () => {
  const same = new Float64Array([5, 5, 5, 5]);
  assert.equal(estimateHomography(same, same, same, same, null, 4, new Float64Array(9)), false);
  const line = new Float64Array([0, 1, 2, 3]);
  assert.equal(estimateHomography(line, line, line, line, null, 4, new Float64Array(9)), false);
  assert.equal(estimateHomography(line, line, line, line, null, 3, new Float64Array(9)), false);
});

test('inverse and product are consistent', () => {
  const inverse = invert3x3(TRUTH);
  const identity = multiply3x3(TRUTH, inverse);
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) assert.ok(Math.abs(identity[r * 3 + c] - (r === c ? 1 : 0)) < 1e-9);
  }
  assert.equal(invert3x3(new Float64Array(9)), null);
});

test('rect projection rejects points behind the camera and keeps winding', () => {
  const rect = projectRect(TRUTH, 40, 100, 360, 220);
  assert.equal(rect.length, 4);
  assert.ok(polygonArea(rect) > 0);
  assert.ok(isConvexClockwise(rect));
  assert.ok(depth(TRUTH, 10, 10) > 0);
  const behind = new Float64Array([1, 0, 0, 0, 1, 0, 0, 0, -1]);
  assert.equal(projectRect(behind, 0, 0, 10, 10), null);
});

test('convexity and containment helpers', () => {
  const square = [[0, 0], [10, 0], [10, 10], [0, 10]];
  assert.ok(isConvexClockwise(square));
  assert.equal(isConvexClockwise([[0, 0], [0, 10], [10, 10], [10, 0]]), false);
  assert.equal(isConvexClockwise([[0, 0], [10, 0], [2, 2], [0, 10]]), false);
  assert.ok(pointInPolygon([5, 5], square));
  assert.equal(pointInPolygon([15, 5], square), false);
});
