import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BUDGET_DEFAULTS, FrameBudget, LONG_EDGES } from '../assets/ar/budget.js';

function feed(budget, ms, count) {
  let last = { changed: false, edge: budget.edge };
  for (let i = 0; i < count; i++) last = budget.record(ms);
  return last;
}

test('the analysed frame keeps the aspect ratio, is capped at the long edge and is never enlarged', () => {
  const budget = new FrameBudget();
  assert.deepEqual(LONG_EDGES, [512, 416, 336]);
  assert.equal(budget.edge, 512);
  assert.deepEqual(budget.fit(1280, 720), { width: 512, height: 288 });
  assert.deepEqual(budget.fit(720, 1280), { width: 288, height: 512 });
  assert.deepEqual(budget.fit(320, 240), { width: 320, height: 240 }, 'a small video is not scaled up');
  assert.deepEqual(budget.fit(512, 512), { width: 512, height: 512 });
});

test('a video without a size has no analysis size', () => {
  const budget = new FrameBudget();
  for (const [w, h] of [[0, 0], [0, 720], [1280, 0], [-1, 720], [NaN, 720], [undefined, undefined]]) {
    assert.equal(budget.fit(w, h), null, `${w}x${h}`);
  }
});

test('a slow device steps down one size per full window and asks for a tracker restart', () => {
  const budget = new FrameBudget();
  const window = BUDGET_DEFAULTS.window;
  assert.equal(feed(budget, 300, window - 1).changed, false, 'a partial window never decides');
  const stepped = budget.record(300);
  assert.deepEqual(stepped, { changed: true, edge: 416 });
  assert.equal(budget.edge, 416);
  assert.equal(feed(budget, 300, window - 1).changed, false, 'the window starts over after a step');
  assert.deepEqual(budget.record(300), { changed: true, edge: 336 });
});

test('the smallest size is a floor, however slow the device is', () => {
  const budget = new FrameBudget();
  feed(budget, 900, BUDGET_DEFAULTS.window * 2);
  assert.equal(budget.edge, 336);
  const after = feed(budget, 900, BUDGET_DEFAULTS.window * 3);
  assert.deepEqual(after, { changed: false, edge: 336 });
});

test('a single slow frame does not step down', () => {
  const budget = new FrameBudget();
  feed(budget, 40, BUDGET_DEFAULTS.window - 1);
  assert.equal(budget.record(400).changed, false);
  assert.equal(budget.edge, 512);
});

test('a fast device goes back up only after a long run of fast frames', () => {
  const budget = new FrameBudget();
  feed(budget, 300, BUDGET_DEFAULTS.window);
  assert.equal(budget.edge, 416);

  // Between the two thresholds nothing happens, however long it lasts.
  feed(budget, 100, BUDGET_DEFAULTS.upAfter * 2);
  assert.equal(budget.edge, 416, 'a mean of 100 ms must not oscillate back up');

  // The first few windows after the change still contain slow samples, so the run is counted from the
  // frame whose window mean is fast; it cannot complete before `upAfter` frames.
  let frames = 0;
  let result = { changed: false };
  while (!result.changed && frames < 1000) {
    result = budget.record(30);
    frames++;
  }
  assert.equal(result.changed, true);
  assert.equal(result.edge, 512);
  assert.equal(budget.edge, 512);
  assert.ok(frames >= BUDGET_DEFAULTS.upAfter, `${frames} frames`);
  assert.ok(frames <= BUDGET_DEFAULTS.upAfter + BUDGET_DEFAULTS.window, `${frames} frames`);
});

test('it never goes back up into a size that is predicted to be too slow', () => {
  // Mean 85 ms is below fastMs, but costs about 85 * (512/416)^2 = 129 ms at 512, above 0.8 * slowMs = 80.
  const budget = new FrameBudget({ slowMs: 100, fastMs: 90, window: 4, upAfter: 5 });
  feed(budget, 300, 4);
  assert.equal(budget.edge, 416);
  const result = feed(budget, 85, 200);
  assert.equal(result.changed, false);
  assert.equal(budget.edge, 416);
});

test('a slow frame inside a fast run restarts the count', () => {
  const budget = new FrameBudget();
  feed(budget, 300, BUDGET_DEFAULTS.window);
  assert.equal(budget.edge, 416);
  feed(budget, 30, BUDGET_DEFAULTS.window + BUDGET_DEFAULTS.upAfter - 20);
  feed(budget, 150, BUDGET_DEFAULTS.window);
  feed(budget, 30, BUDGET_DEFAULTS.window + 30);
  assert.equal(budget.edge, 416);
});

test('invalid timings are ignored', () => {
  const budget = new FrameBudget();
  for (const bad of [NaN, Infinity, -1, undefined, null, '12']) {
    assert.deepEqual(budget.record(bad), { changed: false, edge: 512 });
  }
  feed(budget, 40, BUDGET_DEFAULTS.window - 1);
  budget.record(NaN);
  assert.equal(budget.record(40).changed, false, 'ignored values are not counted into the window');
});

test('edges must be positive and strictly decreasing', () => {
  for (const edges of [[], [512, 512], [336, 512], [0], [-5, -10], [512, NaN], 'wide', null]) {
    assert.throws(() => new FrameBudget({ edges }), TypeError, JSON.stringify(edges));
  }
  const single = new FrameBudget({ edges: [400] });
  assert.equal(feed(single, 900, 40).changed, false);
});
