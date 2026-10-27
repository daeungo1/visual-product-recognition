import { test } from 'node:test';
import assert from 'node:assert/strict';
import { GuideSession, PHASE } from '../assets/ar/session.js';
import { loadCatalog } from './support/scenarios.mjs';

const scenarios = loadCatalog().scenarios;
const [AIRCON, WASHER] = scenarios;

const tracked = (scenario) => ({ status: 'tracked', targetId: scenario.target_id });
const lost = { status: 'none', targetId: null };
const ambiguous = { status: 'ambiguous', targetId: null };

class Clock {
  constructor() { this.t = 1000; }
  tick(ms = 100) { this.t += ms; return this.t; }
}

function drive(session, clock, result, frames = 1) {
  let view = null;
  for (let i = 0; i < frames; i++) view = session.observe(result, clock.tick());
  return view;
}

function toSymptom(session, clock, scenario = AIRCON) {
  drive(session, clock, tracked(scenario), 3);
  const outcome = session.confirmProduct({ source: 'camera', scenarioId: scenario.id }, clock.t);
  assert.equal(outcome.ok, true);
}

function toGuiding(session, clock, scenario = AIRCON) {
  toSymptom(session, clock, scenario);
  assert.equal(session.startGuidance().ok, true);
  return drive(session, clock, tracked(scenario));
}

test('a candidate needs three consecutive tracked frames of one target', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  assert.equal(drive(session, clock, tracked(AIRCON), 2).phase, PHASE.SCANNING);
  const ready = drive(session, clock, tracked(AIRCON));
  assert.equal(ready.phase, PHASE.CANDIDATE);
  assert.equal(ready.candidate.id, 'aircon');
  assert.equal(ready.canConfirmProduct, true);

  assert.equal(drive(session, clock, lost).phase, PHASE.SCANNING);
  assert.equal(session.view(clock.t).candidate, null);

  drive(session, clock, tracked(AIRCON), 2);
  drive(session, clock, tracked(WASHER), 2);
  assert.equal(drive(session, clock, tracked(AIRCON), 2).phase, PHASE.SCANNING, 'a target change restarts the streak');
  assert.equal(drive(session, clock, tracked(AIRCON)).phase, PHASE.CANDIDATE);
});

test('ambiguous, unknown and missing results never produce a candidate', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  const fuzzy = drive(session, clock, ambiguous, 5);
  assert.equal(fuzzy.phase, PHASE.SCANNING);
  assert.equal(fuzzy.status, 'ambiguous');
  const unknown = drive(session, clock, { status: 'tracked', targetId: 'unregistered-real-product' }, 5);
  assert.equal(unknown.phase, PHASE.SCANNING);
  assert.equal(unknown.status, 'none');
  assert.equal(drive(session, clock, null, 5).phase, PHASE.SCANNING);
});

test('camera confirmation needs the candidate and a fresh observation of it', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  assert.equal(session.confirmProduct({ source: 'camera', scenarioId: 'aircon' }, clock.t).reason, 'no-candidate');

  drive(session, clock, tracked(AIRCON), 3);
  assert.equal(session.confirmProduct({ source: 'camera', scenarioId: 'washer' }, clock.t).reason, 'no-candidate');
  assert.equal(session.confirmProduct({ source: 'auto', scenarioId: 'aircon' }, clock.t).reason, 'bad-source');
  assert.equal(session.confirmProduct({ source: 'camera', scenarioId: 'nope' }, clock.t).reason, 'unknown-scenario');

  const later = clock.t + 600;
  assert.equal(session.view(later).canConfirmProduct, false, 'a stale observation is not a candidate');
  assert.equal(session.confirmProduct({ source: 'camera', scenarioId: 'aircon' }, later).reason, 'not-tracking');
  assert.equal(session.phase, PHASE.CANDIDATE);

  drive(session, clock, tracked(AIRCON));
  const accepted = session.confirmProduct({ source: 'camera', scenarioId: 'aircon' }, clock.t);
  assert.deepEqual(accepted, { ok: true, reason: 'accepted' });
  const view = session.view(clock.t);
  assert.equal(view.phase, PHASE.SYMPTOM);
  assert.equal(view.source, 'camera');
  assert.equal(view.scenario.id, 'aircon');
  assert.equal(session.confirmProduct({ source: 'camera', scenarioId: 'aircon' }, clock.t).reason, 'wrong-phase');
});

test('a manual selection is recorded as manual and shows guidance only while that target is tracked', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  assert.equal(session.confirmProduct({ source: 'manual', scenarioId: 'monitor' }, clock.t).ok, true);
  const monitor = scenarios.find((s) => s.id === 'monitor');
  let view = session.view(clock.t);
  assert.equal(view.source, 'manual');
  assert.equal(view.tracking, false);
  assert.equal(session.startGuidance().ok, true);
  view = session.view(clock.t);
  assert.deepEqual(view.overlay, { visible: false, reason: 'not-tracking' });
  assert.equal(view.canConfirmStep, false);

  view = drive(session, clock, tracked(monitor));
  assert.equal(view.overlay.visible, true);
  assert.equal(view.canConfirmStep, true);
  assert.equal(view.source, 'manual');
});

test('the overlay is hidden on loss, ambiguity, a stale observation and another target', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  let view = toGuiding(session, clock);
  assert.equal(view.overlay.visible, true);
  assert.equal(view.stepId, 'aircon/power');

  view = drive(session, clock, lost);
  assert.deepEqual(view.overlay, { visible: false, reason: 'not-tracking' });
  assert.equal(view.phase, PHASE.GUIDING, 'loss keeps the step');
  view = drive(session, clock, tracked(AIRCON));
  assert.equal(view.overlay.visible, true);
  assert.equal(view.stepIndex, 0);

  view = drive(session, clock, ambiguous);
  assert.equal(view.overlay.visible, false);
  drive(session, clock, tracked(AIRCON));
  assert.equal(session.view(clock.t + 600).overlay.visible, false, 'last-known pose is not tracking');
  assert.equal(session.view(clock.t + 600).status, 'none');

  view = drive(session, clock, tracked(WASHER));
  assert.deepEqual(view.overlay, { visible: false, reason: 'other-target' });
  assert.equal(view.phase, PHASE.GUIDING);
  view = drive(session, clock, tracked(WASHER));
  assert.equal(view.phase, PHASE.GUIDING);
  view = drive(session, clock, tracked(WASHER));
  assert.equal(view.phase, PHASE.CANDIDATE, 'a sustained different target ends the session');
  assert.equal(view.candidate.id, 'washer');
  assert.equal(view.scenario, null);
  assert.equal(view.notice, 'target-changed');
  assert.equal(view.overlay.visible, false);
});

test('steps are confirmed manually, in order, once, for the generation that was shown', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  let view = toGuiding(session, clock);
  const shown = view.generation;

  assert.equal(session.confirmStep({ stepId: 'aircon/mode', generation: shown }, clock.t).reason, 'wrong-step');
  assert.equal(session.confirmStep({ stepId: 'aircon/power', generation: shown - 1 }, clock.t).reason, 'stale');
  drive(session, clock, lost);
  assert.equal(session.confirmStep({ stepId: 'aircon/power', generation: shown }, clock.t).reason, 'not-tracking');
  view = drive(session, clock, tracked(AIRCON));
  assert.equal(view.canConfirmStep, true);
  assert.equal(
    session.confirmStep({ stepId: 'aircon/power', generation: shown }, clock.t + 600).reason,
    'not-tracking',
    'a stale observation cannot confirm a step',
  );
  const first = session.confirmStep({ stepId: 'aircon/power', generation: shown }, clock.t);
  assert.deepEqual(first, { ok: true, reason: 'accepted', completed: false });
  assert.equal(session.confirmStep({ stepId: 'aircon/power', generation: shown }, clock.t).reason, 'duplicate');
  assert.equal(session.confirmStep({ stepId: 'aircon/mode', generation: shown }, clock.t).reason, 'stale');

  view = session.view(clock.t);
  assert.equal(view.stepIndex, 1);
  assert.equal(view.stepId, 'aircon/mode');
  assert.ok(view.generation > shown);

  assert.equal(session.confirmStep({ stepId: 'aircon/mode', generation: view.generation }, clock.t).ok, true);
  drive(session, clock, tracked(AIRCON));
  const last = session.confirmStep({ stepId: 'aircon/temperature', generation: session.view(clock.t).generation }, clock.t);
  assert.deepEqual(last, { ok: true, reason: 'accepted', completed: true });

  view = session.view(clock.t);
  assert.equal(view.phase, PHASE.COMPLETED);
  assert.deepEqual(view.overlay, { visible: false, reason: 'not-guiding' });
  assert.deepEqual(view.completions.map((entry) => entry.source), ['manual', 'manual', 'manual']);
  assert.deepEqual(view.completions.map((entry) => entry.stepId), ['aircon/power', 'aircon/mode', 'aircon/temperature']);
  assert.equal(session.confirmStep({ stepId: 'aircon/temperature', generation: view.generation }, clock.t).reason, 'duplicate');
});

test('pausing hides guidance and discards earlier observations', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  drive(session, clock, tracked(AIRCON), 3);
  session.pause();
  assert.equal(session.phase, PHASE.SCANNING);
  assert.equal(drive(session, clock, tracked(AIRCON), 5).tracking, false, 'frames are ignored while paused');
  assert.equal(session.confirmProduct({ source: 'manual', scenarioId: 'aircon' }, clock.t).reason, 'paused');
  session.resume();
  assert.equal(drive(session, clock, tracked(AIRCON), 2).phase, PHASE.SCANNING);
  assert.equal(drive(session, clock, tracked(AIRCON)).phase, PHASE.CANDIDATE);

  const guiding = new GuideSession(scenarios);
  const guidingClock = new Clock();
  toGuiding(guiding, guidingClock);
  guiding.pause();
  assert.deepEqual(guiding.view(guidingClock.t).overlay, { visible: false, reason: 'paused' });
  guiding.resume();
  assert.deepEqual(guiding.view(guidingClock.t).overlay, { visible: false, reason: 'not-tracking' });
  assert.equal(drive(guiding, guidingClock, tracked(AIRCON)).overlay.visible, true);
  assert.equal(guiding.view(guidingClock.t).phase, PHASE.GUIDING);
});

test('restart drops progress and invalidates what was shown before', () => {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  const view = toGuiding(session, clock);
  const shown = view.generation;
  assert.equal(session.confirmStep({ stepId: 'aircon/power', generation: shown }, clock.t).ok, true);
  session.restart();
  const after = session.view(clock.t);
  assert.equal(after.phase, PHASE.SCANNING);
  assert.equal(after.scenario, null);
  assert.deepEqual(after.completions, []);
  assert.equal(session.confirmStep({ stepId: 'aircon/mode', generation: shown + 1 }, clock.t).reason, 'not-guiding');
});

test('every catalog scenario completes through the camera path with manual confirmations', () => {
  for (const scenario of scenarios) {
    const session = new GuideSession(scenarios);
    const clock = new Clock();
    let view = toGuiding(session, clock, scenario);
    assert.equal(view.scenario.id, scenario.id);
    assert.equal(view.source, 'camera');
    scenario.controls.forEach((control, index) => {
      view = drive(session, clock, tracked(scenario));
      assert.equal(view.stepIndex, index);
      assert.equal(view.step.id, control.id);
      assert.equal(view.stepId, `${scenario.id}/${control.id}`);
      assert.equal(view.overlay.visible, true);
      const [left, top, right, bottom] = control.rect;
      assert.ok(left >= 0 && top >= 0 && right <= 1 && bottom <= 1 && left < right && top < bottom, `${scenario.id}/${control.id} rect`);
      const outcome = session.confirmStep({ stepId: view.stepId, generation: view.generation }, clock.t);
      assert.equal(outcome.ok, true, `${scenario.id}/${control.id}: ${outcome.reason}`);
    });
    view = session.view(clock.t);
    assert.equal(view.phase, PHASE.COMPLETED);
    assert.equal(view.completions.length, scenario.controls.length);
    assert.ok(view.completions.every((entry) => entry.source === 'manual'));
  }
});

test('invalid catalogs are rejected', () => {
  assert.throws(() => new GuideSession([]), TypeError);
  assert.throws(() => new GuideSession([AIRCON, AIRCON]), TypeError);
  assert.throws(() => new GuideSession([{ ...AIRCON, controls: [] }]), TypeError);
  assert.throws(() => new GuideSession([{ ...AIRCON, target_id: undefined }]), TypeError);
});
