import { test } from 'node:test';
import assert from 'node:assert/strict';
import { centroid, isConvexClockwise, polygonArea, projectRect } from '../assets/ar/geometry.js';
import { describeOverlay } from '../assets/ar/overlay.js';
import { GuideSession, PHASE } from '../assets/ar/session.js';
import { poseHomography } from '../assets/ar/synthetic.js';
import { loadCatalog } from './support/scenarios.mjs';

const scenarios = loadCatalog().scenarios;
const [AIRCON, WASHER] = scenarios;
const REF = { width: 400, height: 640 };
const FRAME = { width: 288, height: 512 };
const sizeOf = (id) => (scenarios.some((s) => s.target_id === id) ? REF : null);

const pose = (options = {}) => poseHomography({
  refWidth: REF.width, refHeight: REF.height, frameWidth: FRAME.width, frameHeight: FRAME.height, scale: 0.55, ...options,
});

const resultFor = (scenario, H = pose()) => ({
  status: 'tracked', targetId: scenario.target_id, H, quad: projectRect(H, 0, 0, REF.width, REF.height),
});

class Clock {
  constructor() { this.t = 1000; }
  tick(ms = 100) { this.t += ms; return this.t; }
}

function sessionAt(phase, scenario = AIRCON) {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  const result = resultFor(scenario);
  const observe = (frames = 1) => { for (let i = 0; i < frames; i++) session.observe(result, clock.tick()); };
  observe(3);
  if (phase !== PHASE.CANDIDATE) {
    assert.equal(session.confirmProduct({ source: 'camera', scenarioId: scenario.id }, clock.t).ok, true);
  }
  if (phase === PHASE.GUIDING) {
    assert.equal(session.startGuidance().ok, true);
    observe();
  }
  return { session, clock, result, observe };
}

const draw = (session, clock, result) => describeOverlay(session.view(clock.t), result, sizeOf, FRAME);

test('nothing is drawn while scanning, even when a registered target is tracked', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  const result = resultFor(AIRCON);
  session.observe(result, clock.tick());
  const shape = draw(session, clock, result);
  assert.equal(shape.kind, 'none');
  assert.equal(shape.outline, null);
  assert.equal(shape.control, null);
});

test('a candidate is outlined along the tracked target and still needs the user to confirm', () => {
  const { session, clock, result } = sessionAt(PHASE.CANDIDATE);
  const shape = draw(session, clock, result);
  assert.equal(shape.kind, 'candidate');
  assert.deepEqual(shape.outline, result.quad);
  assert.match(shape.label, /확인 필요/);
  assert.match(shape.label, /합성/);
  assert.equal(shape.control, null);
  assert.equal(shape.confirmable, false);
});

test('after the product is confirmed the outline stays but there is no control highlight yet', () => {
  const { session, clock, result } = sessionAt(PHASE.SYMPTOM);
  const shape = draw(session, clock, result);
  assert.equal(shape.kind, 'confirmed');
  assert.deepEqual(shape.outline, result.quad);
  assert.equal(shape.control, null);
});

test('the control highlight is the catalog rectangle projected through the current homography', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const view = session.view(clock.t);
  const shape = draw(session, clock, result);
  assert.equal(shape.kind, 'guidance');
  const [l, t, r, b] = view.step.rect;
  const expected = projectRect(result.H, l * REF.width, t * REF.height, r * REF.width, b * REF.height);
  assert.equal(shape.control.length, 4);
  shape.control.forEach((corner, i) => {
    assert.ok(Math.abs(corner[0] - expected[i][0]) < 1e-9 && Math.abs(corner[1] - expected[i][1]) < 1e-9, `corner ${i}`);
  });
  assert.deepEqual(shape.outline, result.quad);
  assert.equal(shape.controlInFrame, true);
  assert.equal(shape.confirmable, true);
  assert.ok(shape.label.includes(view.step.label) && shape.label.includes(view.step.expected));
  assert.ok(shape.label.startsWith('1/3'));
});

test('the highlight moves and scales with the target instead of staying at a screen position', () => {
  const { session, clock } = sessionAt(PHASE.GUIDING);
  const poses = [pose(), pose({ scale: 0.42, cx: 100, cy: 200 }), pose({ rotDeg: 20, tiltYDeg: 15 })];
  const centers = poses.map((H) => {
    const result = resultFor(AIRCON, H);
    session.observe(result, clock.tick());
    const shape = draw(session, clock, result);
    assert.equal(shape.kind, 'guidance');
    return centroid(shape.control);
  });
  assert.notDeepEqual(centers[0], centers[1]);
  assert.notDeepEqual(centers[0], centers[2]);
  assert.notDeepEqual(centers[1], centers[2]);
});

test('a smaller target gives a smaller highlight', () => {
  const { session, clock } = sessionAt(PHASE.GUIDING);
  const area = (scale) => {
    const result = resultFor(AIRCON, pose({ scale }));
    session.observe(result, clock.tick());
    const { control } = draw(session, clock, result);
    return Math.abs((control[1][0] - control[0][0]) * (control[3][1] - control[0][1]));
  };
  assert.ok(area(0.3) < area(0.55) / 2);
});

test('every step highlights its own catalog rectangle', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const seen = [];
  for (let i = 0; i < 3; i++) {
    const view = session.view(clock.t);
    const shape = draw(session, clock, result);
    assert.equal(shape.kind, 'guidance');
    assert.ok(shape.label.startsWith(`${i + 1}/3`));
    seen.push(shape.control.map((p) => p.map((v) => Math.round(v)).join(',')).join(' '));
    assert.equal(session.confirmStep({ stepId: view.stepId, generation: view.generation }, clock.t).ok, true);
    session.observe(result, clock.tick());
  }
  assert.equal(new Set(seen).size, 3, 'three different regions');
  const done = draw(session, clock, result);
  assert.equal(done.kind, 'none');
  assert.equal(done.reason, 'no-overlay-phase');
});

test('losing the target hides every shape at once', () => {
  for (const phase of [PHASE.CANDIDATE, PHASE.SYMPTOM, PHASE.GUIDING]) {
    const { session, clock } = sessionAt(phase);
    const lost = { status: 'none', targetId: null, H: null, quad: null };
    session.observe(lost, clock.tick());
    const shape = draw(session, clock, lost);
    assert.equal(shape.kind, 'none', phase);
    assert.equal(shape.outline, null);
    assert.equal(shape.control, null);
  }
});

test('an ambiguous result and a result without a pose draw nothing', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const view = session.view(clock.t);
  const variants = [
    { ...result, status: 'ambiguous', targetId: null, H: null, quad: null },
    { ...result, H: null },
    { ...result, quad: null },
    { ...result, quad: result.quad.slice(0, 3) },
    { ...result, quad: [[0, 0], [1, 1], [NaN, 2], [3, 3]] },
    { ...result, status: 'none' },
  ];
  for (const variant of variants) {
    const shape = describeOverlay(view, variant, sizeOf, FRAME);
    assert.equal(shape.kind, 'none');
    assert.equal(shape.reason, 'not-tracked');
  }
  assert.equal(describeOverlay(view, null, sizeOf, FRAME).reason, 'no-result');
  assert.equal(describeOverlay(null, result, sizeOf, FRAME).reason, 'no-result');
});

test('the shape is not drawn from an old observation or while paused', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const late = clock.t + 5000;
  const stale = describeOverlay(session.view(late), result, sizeOf, FRAME);
  assert.equal(stale.kind, 'none');
  assert.equal(stale.reason, 'stale');

  session.observe(result, clock.tick());
  session.pause();
  const paused = describeOverlay(session.view(clock.t), result, sizeOf, FRAME);
  assert.equal(paused.kind, 'none');
  session.resume();
  assert.equal(describeOverlay(session.view(clock.t), result, sizeOf, FRAME).kind, 'none', 'nothing is shown until a new frame is tracked');
  session.observe(result, clock.tick());
  assert.equal(describeOverlay(session.view(clock.t), result, sizeOf, FRAME).kind, 'guidance');
});

test('another product in view never receives the selected product highlight', () => {
  const { session, clock } = sessionAt(PHASE.GUIDING, AIRCON);
  const other = resultFor(WASHER);
  session.observe(other, clock.tick());
  const shape = draw(session, clock, other);
  assert.equal(shape.kind, 'none');
  assert.equal(shape.reason, 'other-target');

  // An observation of the selected product does not authorise a shape computed for a different one.
  const mismatch = describeOverlay(session.view(clock.t), resultFor(AIRCON), sizeOf, FRAME);
  assert.equal(mismatch.kind, 'none');
  assert.equal(mismatch.reason, 'stale');
});

test('after the product is confirmed another product in view gets no outline and no confirmed label', () => {
  const { session, clock } = sessionAt(PHASE.SYMPTOM, AIRCON);
  const other = resultFor(WASHER);
  session.observe(other, clock.tick());
  const shape = draw(session, clock, other);
  assert.equal(shape.kind, 'none');
  assert.equal(shape.reason, 'other-target');
  assert.equal(shape.label, null);
});

test('a target that is not in the reference database cannot be drawn', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const shape = describeOverlay(session.view(clock.t), result, () => null, FRAME);
  assert.equal(shape.kind, 'none');
  assert.equal(shape.reason, 'unknown-target');
});

test('a pose that flips or collapses the target is rejected instead of drawn', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const view = session.view(clock.t);
  const H = pose();
  // Mirror the image horizontally: x' = W - x, so row 0 becomes W * row 2 - row 0.
  const flipped = Float64Array.from(H);
  for (let c = 0; c < 3; c++) flipped[c] = FRAME.width * H[6 + c] - H[c];
  const [l, t, r, b] = view.step.rect;
  const mirrored = projectRect(flipped, l * REF.width, t * REF.height, r * REF.width, b * REF.height);
  assert.ok(mirrored, 'the mirrored pose still projects');
  assert.equal(isConvexClockwise(mirrored), false, 'precondition: a mirrored quad is counter-clockwise');
  const flippedResult = { ...result, H: flipped, quad: projectRect(flipped, 0, 0, REF.width, REF.height) };
  assert.equal(describeOverlay(view, flippedResult, sizeOf, FRAME).reason, 'bad-pose');

  const behind = { ...result, H: new Float64Array([1, 0, 0, 0, 1, 0, 0, 0, -1]) };
  assert.equal(describeOverlay(view, behind, sizeOf, FRAME).reason, 'bad-pose');

  const tiny = { ...result, H: pose({ scale: 0.004 }) };
  assert.equal(describeOverlay(view, tiny, sizeOf, FRAME).reason, 'bad-pose', 'a speck is not a highlight');
});

test('a concave outline from the tracker is not drawn', () => {
  const { session, clock, result } = sessionAt(PHASE.CANDIDATE);
  const view = session.view(clock.t);
  const dart = [[40, 40], [240, 40], [80, 90], [40, 300]];
  assert.ok(polygonArea(dart) > 64, 'precondition: the area alone would accept this outline');
  assert.equal(isConvexClockwise(dart), false);
  const shape = describeOverlay(view, { ...result, quad: dart }, sizeOf, FRAME);
  assert.equal(shape.kind, 'none');
  assert.equal(shape.reason, 'bad-pose');
});

test('a candidate that is not the target in the frame is never outlined', () => {
  const { session, clock, result } = sessionAt(PHASE.CANDIDATE);
  const view = session.view(clock.t);
  assert.equal(describeOverlay(view, result, sizeOf, FRAME).kind, 'candidate');
  assert.equal(describeOverlay({ ...view, candidate: null }, result, sizeOf, FRAME).reason, 'no-candidate');
  const wrong = { ...view.candidate, target_id: WASHER.target_id };
  assert.equal(describeOverlay({ ...view, candidate: wrong }, result, sizeOf, FRAME).reason, 'no-candidate');
});

test('the session has the last word: a vetoed overlay is not drawn even when the frame looks fine', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const view = session.view(clock.t);
  assert.equal(describeOverlay(view, result, sizeOf, FRAME).kind, 'guidance');
  const vetoed = describeOverlay({ ...view, overlay: { visible: false, reason: 'paused' } }, result, sizeOf, FRAME);
  assert.equal(vetoed.kind, 'none');
  assert.equal(vetoed.reason, 'paused');
  assert.equal(describeOverlay({ ...view, step: null }, result, sizeOf, FRAME).kind, 'none');
});

test('a step without a usable rectangle is not drawn', () => {
  const { session, clock, result } = sessionAt(PHASE.GUIDING);
  const view = session.view(clock.t);
  for (const rect of [null, [0.1, 0.1, 0.5], [0.1, 0.1, 0.5, Number.NaN]]) {
    const shape = describeOverlay({ ...view, step: { ...view.step, rect } }, result, sizeOf, FRAME);
    assert.equal(shape.kind, 'none');
    assert.equal(shape.reason, 'bad-step');
  }
});

test('a highlight whose centre is outside the frame on any side cannot be confirmed', () => {
  const shifts = {
    above: { cy: -400 },
    below: { cy: FRAME.height + 400 },
    left: { cx: -400 },
    right: { cx: FRAME.width + 400 },
  };
  for (const [side, shift] of Object.entries(shifts)) {
    const { session, clock } = sessionAt(PHASE.GUIDING);
    const result = resultFor(AIRCON, pose(shift));
    session.observe(result, clock.tick());
    const shape = draw(session, clock, result);
    assert.equal(shape.kind, 'guidance', side);
    assert.equal(shape.controlInFrame, false, side);
    assert.equal(shape.confirmable, false, side);
  }
});
