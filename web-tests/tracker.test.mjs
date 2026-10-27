import test from 'node:test';
import assert from 'node:assert/strict';
import { mulberry32 } from '../assets/ar/features.js';
import { clutterGray, simulatedPose } from '../assets/ar/synthetic.js';
import { DEFAULT_OPTIONS } from '../assets/ar/tracker.js';
import { loadGrayPng, loadScenarioTargets } from './support/scenarios.mjs';
import { createTracker, median, Studio } from './support/studio.mjs';

// Every measurement here uses synthetic frames: registered scenario PNGs rendered into seeded clutter with a
// pinhole pose model. It checks the tracker's logic, not how it behaves with a real phone camera.
const targets = loadScenarioTargets();
const studio = new Studio(targets);
const { width: FW, height: FH } = studio;

test('registers every scenario target with a usable number of keypoints', () => {
  const tracker = createTracker(targets);
  assert.equal(tracker.targets.size, targets.length);
  for (const target of targets) {
    const model = tracker.targets.get(target.id);
    assert.ok(model.count >= 300 && model.count <= 1000, `${target.id} has ${model.count} keypoints`);
  }
});

test('acquires each registered product with accurate corners', () => {
  const tracker = createTracker(targets);
  for (const [index, target] of targets.entries()) {
    tracker.reset();
    const { gray, H } = studio.frame(target, { scale: 0.55, rotDeg: index * 9 }, {
      background: clutterGray(FW, FH, 40 + index), noise: 2, seed: index,
    });
    const result = tracker.process(gray, FW, FH);
    assert.equal(result.status, 'tracked', target.id);
    assert.equal(result.targetId, target.id);
    assert.equal(result.mode, 'scan');
    assert.ok(result.inliers >= DEFAULT_OPTIONS.minInliersAcquire, `${target.id} inliers ${result.inliers}`);
    assert.ok(studio.cornerError(H, target, result.quad) < 4, `${target.id} corner error`);
  }
});

test('seeded pose and camera-effect matrix is mostly recognised and never wrong', (t) => {
  const tracker = createTracker(targets);
  const rng = mulberry32(777);
  const outcome = { ok: 0, wrong: 0, none: 0, ambiguous: 0, inaccurate: 0 };
  const inliers = [];
  const trials = 80;
  for (let trial = 0; trial < trials; trial++) {
    const target = targets[trial % targets.length];
    const pose = {
      scale: 0.35 + rng() * 0.4,
      rotDeg: (rng() - 0.5) * 70,
      tiltXDeg: (rng() - 0.5) * 50,
      tiltYDeg: (rng() - 0.5) * 50,
    };
    const noise = [0, 4, 8][Math.floor(rng() * 3)];
    const blurPasses = Math.floor(rng() * 3);
    const gain = 0.6 + rng() * 0.8;
    const bias = (rng() - 0.5) * 60;
    pose.cx = FW * (0.4 + rng() * 0.2);
    pose.cy = FH * (0.4 + rng() * 0.2);
    const { gray, H } = studio.frame(target, pose, {
      background: clutterGray(FW, FH, 1000 + trial), blurPasses, gain, bias, noise, seed: trial,
    });
    tracker.reset();
    const result = tracker.process(gray, FW, FH);
    if (result.status === 'tracked' && result.targetId !== target.id) outcome.wrong++;
    else if (result.status === 'tracked') {
      if (studio.cornerError(H, target, result.quad) < 4) {
        outcome.ok++;
        inliers.push(result.inliers);
      } else outcome.inaccurate++;
    } else if (result.status === 'ambiguous') outcome.ambiguous++;
    else outcome.none++;
  }
  t.diagnostic(`matrix ${trials}: ${JSON.stringify(outcome)}, inliers min ${Math.min(...inliers)} median ${median(inliers)}`);
  assert.equal(outcome.wrong, 0, 'a wrong product must never be reported');
  assert.equal(outcome.inaccurate, 0, 'a reported pose must be accurate');
  assert.ok(outcome.ok >= Math.ceil(trials * 0.9), `recognised ${outcome.ok}/${trials}`);
});

test('an unregistered product is never reported as one of the registered ones', () => {
  for (const [held, target] of targets.entries()) {
    const tracker = createTracker(targets.filter((_, index) => index !== held));
    for (let k = 0; k < 6; k++) {
      tracker.reset();
      const { gray } = studio.frame(target, { scale: 0.55, rotDeg: k * 7, tiltYDeg: k * 4 }, {
        background: clutterGray(FW, FH, 31337), blurPasses: 1, noise: 3, seed: k,
      });
      const result = tracker.process(gray, FW, FH);
      assert.notEqual(result.status, 'tracked', `${target.scenario.id} pose ${k} reported as ${result.targetId}`);
      assert.equal(result.quad, null);
      assert.equal(result.targetId, null);
    }
  }
});

test('clutter and an unregistered target never produce a recognition', () => {
  const tracker = createTracker(targets);
  for (let seed = 0; seed < 60; seed++) {
    tracker.reset();
    const result = tracker.process(clutterGray(FW, FH, 5000 + seed), FW, FH);
    assert.notEqual(result.status, 'tracked', `clutter ${seed}`);
  }
  const demo = loadGrayPng('demo-target.png');
  const demoStudio = new Studio([{ id: 'demo', ...demo }]);
  for (let i = 0; i < 20; i++) {
    tracker.reset();
    const { gray } = demoStudio.frame(demoStudio.targets[0], { scale: 0.4 + (i % 5) * 0.08, rotDeg: i * 3 }, {
      background: clutterGray(FW, FH, 6000 + i), noise: 3, seed: i,
    });
    const result = tracker.process(gray, FW, FH);
    assert.notEqual(result.status, 'tracked', `unregistered demo target ${i}`);
  }
});

test('two identical registrations are reported as ambiguous instead of guessing one', () => {
  const tracker = createTracker([]);
  const [first] = targets;
  tracker.addTarget('copy-a', first.gray, first.width, first.height);
  tracker.addTarget('copy-b', first.gray, first.width, first.height);
  const { gray } = studio.frame(first, { scale: 0.55 }, { background: clutterGray(FW, FH, 31337), blurPasses: 1, noise: 3, seed: 1 });
  const result = tracker.process(gray, FW, FH);
  assert.equal(result.status, 'ambiguous');
  assert.equal(result.targetId, null);
  assert.equal(result.quad, null);
  assert.equal(result.H, null);
});

test('switching the product at an unchanged pose never keeps the old identity', () => {
  const background = clutterGray(FW, FH, 31337);
  for (const from of targets) {
    for (const to of targets) {
      if (from === to) continue;
      const tracker = createTracker(targets);
      const show = (target, seed) => {
        const { gray } = studio.frame(target, { scale: 0.55 }, { background, blurPasses: 1, noise: 3, seed });
        return tracker.process(gray, FW, FH);
      };
      for (let i = 0; i < 3; i++) {
        const before = show(from, i);
        assert.equal(before.targetId, from.id, `${from.scenario.id} should be recognised first`);
      }
      const after = [];
      for (let i = 0; i < 4; i++) after.push(show(to, 10 + i));
      for (const [i, r] of after.entries()) {
        assert.ok(!(r.status === 'tracked' && r.targetId === from.id),
          `${from.scenario.id} -> ${to.scenario.id}: frame ${i} still reported ${r.targetId}`);
      }
      assert.ok(after.slice(0, 2).some((r) => r.status === 'tracked' && r.targetId === to.id),
        `${from.scenario.id} -> ${to.scenario.id}: new product not recognised within two frames`);
    }
  }
});

test('losing the target clears the pose and recognition resumes when it returns', () => {
  const tracker = createTracker(targets);
  const [target] = targets;
  const background = clutterGray(FW, FH, 31337);
  const show = (seed) => {
    const { gray } = studio.frame(target, { scale: 0.55 }, { background, blurPasses: 1, noise: 3, seed });
    return tracker.process(gray, FW, FH);
  };
  for (let i = 0; i < 3; i++) assert.equal(show(i).status, 'tracked');
  for (let i = 0; i < 4; i++) {
    const lost = tracker.process(background, FW, FH);
    assert.equal(lost.status, 'none', `background frame ${i}`);
    assert.equal(lost.H, null);
    assert.equal(lost.quad, null);
    assert.equal(lost.targetId, null);
  }
  const again = show(20);
  assert.equal(again.status, 'tracked');
  assert.equal(again.targetId, target.id);
  assert.equal(show(21).mode, 'track');
});

test('guided tracking follows a hand-held-like motion without losing the target', (t) => {
  const tracker = createTracker(targets);
  const [target] = targets;
  const background = clutterGray(FW, FH, 4242);
  const frames = 90;
  let tracked = 0, scans = 0;
  let worst = 0;
  const guidedMs = [], scanMs = [];
  for (let i = 0; i < frames; i++) {
    const H = simulatedPose(i / 15, { refWidth: target.width, refHeight: target.height, frameWidth: FW, frameHeight: FH });
    const gray = studio.renderWith(target, H, { background, blurPasses: 1, noise: 3, seed: i });
    const start = performance.now();
    const result = tracker.process(gray, FW, FH);
    const elapsed = performance.now() - start;
    if (result.status !== 'tracked') continue;
    tracked++;
    worst = Math.max(worst, studio.cornerError(H, target, result.quad));
    if (result.mode === 'scan') {
      scans++;
      scanMs.push(elapsed);
    } else guidedMs.push(elapsed);
  }
  t.diagnostic(`sequence ${tracked}/${frames} tracked, ${scans} scan frames, worst corner error ${worst.toFixed(2)} px, `
    + `guided median ${median(guidedMs).toFixed(1)} ms, scan median ${median(scanMs).toFixed(1)} ms (desktop, one run)`);
  assert.equal(tracked, frames);
  assert.ok(scans <= 2, `scan frames ${scans}`);
  assert.ok(worst < 4, `worst corner error ${worst}`);
});

test('guided matching accepts the right product and rejects a same-layout product by fraction', (t) => {
  const tracker = createTracker(targets);
  const rng = mulberry32(2468);
  const right = [], wrong = [];
  let rightMissing = 0;
  for (let trial = 0; trial < 120; trial++) {
    const a = trial % targets.length;
    const b = (a + 1 + Math.floor(rng() * 3)) % targets.length;
    const base = {
      scale: 0.35 + rng() * 0.4, rotDeg: (rng() - 0.5) * 60, tiltXDeg: (rng() - 0.5) * 40, tiltYDeg: (rng() - 0.5) * 40,
    };
    const blurPasses = Math.floor(rng() * 3);
    const noise = [0, 4, 8][Math.floor(rng() * 3)];
    const gain = 0.7 + rng() * 0.6;
    const bias = (rng() - 0.5) * 40;
    const previous = {
      ...base,
      scale: base.scale * (1 + (rng() - 0.5) * 0.08),
      rotDeg: base.rotDeg + (rng() - 0.5) * 4,
      cx: FW * 0.5 + (rng() - 0.5) * 12,
      cy: FH * 0.5 + (rng() - 0.5) * 12,
    };
    const current = { ...base, cx: FW * 0.5, cy: FH * 0.5 };
    const previousH = studio.homography(targets[a], previous);
    const background = clutterGray(FW, FH, 8000 + trial);
    const effects = { background, blurPasses, gain, bias, noise };
    const model = tracker.targets.get(targets[a].id);
    const probe = (shown, seed) => {
      const { gray } = studio.frame(shown, current, { ...effects, seed });
      const matches = tracker.matchGuided(tracker.describeFrame(gray, FW, FH), model, previousH, FW, FH, tracker.options.guidedRadius);
      return tracker.fit(matches, model, FW, FH, tracker.options.trackIterations);
    };
    const rightPose = probe(targets[a], trial);
    if (rightPose) right.push({ fraction: rightPose.fraction, blurPasses });
    else rightMissing++;
    const wrongPose = probe(targets[b], trial + 1000);
    if (wrongPose) wrong.push(wrongPose.fraction);
  }
  const wrongMax = Math.max(...wrong);
  const rightLow = Math.min(...right.filter((r) => r.blurPasses <= 1).map((r) => r.fraction));
  t.diagnostic(`guided fraction: wrong max ${wrongMax.toFixed(3)} (n=${wrong.length}), right min ${rightLow.toFixed(3)} `
    + `with at most one blur pass, right pose missing ${rightMissing}/120, gate ${DEFAULT_OPTIONS.minFractionTrack}`);
  assert.equal(rightMissing, 0);
  assert.ok(wrongMax < DEFAULT_OPTIONS.minFractionTrack, `wrong-product fraction ${wrongMax}`);
  assert.ok(rightLow >= DEFAULT_OPTIONS.minFractionTrack, `right-product fraction ${rightLow}`);
});
