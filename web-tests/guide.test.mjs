import { test } from 'node:test';
import assert from 'node:assert/strict';
import { projectRect } from '../assets/ar/geometry.js';
import { describeGuide, describeRefusal, refusalContext, refusalForTap } from '../assets/ar/guide.js';
import { describeOverlay } from '../assets/ar/overlay.js';
import { GuideSession, PHASE } from '../assets/ar/session.js';
import { poseHomography } from '../assets/ar/synthetic.js';
import { loadCatalog } from './support/scenarios.mjs';

const scenarios = loadCatalog().scenarios;
const [AIRCON, WASHER] = scenarios;
const REF = { width: 400, height: 640 };
const FRAME = { width: 288, height: 512 };
const sizeOf = (id) => (scenarios.some((s) => s.target_id === id) ? REF : null);
const nameOf = (id) => {
  const scenario = scenarios.find((s) => s.target_id === id);
  return scenario ? scenario.product : id;
};

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

function setup(phase, { scenario = AIRCON, source = 'camera' } = {}) {
  const session = new GuideSession(scenarios);
  const clock = new Clock();
  let result = resultFor(scenario);
  const observe = (frames = 1, next = result) => {
    result = next;
    for (let i = 0; i < frames; i++) session.observe(result, clock.tick());
  };
  observe(3);
  if (phase !== PHASE.CANDIDATE) {
    const outcome = session.confirmProduct({ source, scenarioId: scenario.id }, clock.t);
    assert.equal(outcome.ok, true);
  }
  if (phase === PHASE.GUIDING || phase === PHASE.COMPLETED) {
    assert.equal(session.startGuidance().ok, true);
    observe();
  }
  if (phase === PHASE.COMPLETED) {
    for (let i = 0; i < scenario.controls.length; i++) {
      const view = session.view(clock.t);
      assert.equal(session.confirmStep({ stepId: view.stepId, generation: view.generation }, clock.t).ok, true);
      observe();
    }
  }
  return { session, clock, observe, get result() { return result; } };
}

function guide(state, extra = {}) {
  const view = state.session.view(state.clock.t);
  const shape = describeOverlay(view, state.result, sizeOf, FRAME);
  return { ui: describeGuide({ view, shape, source: 'camera', ready: true, nameOf, ...extra }), view, shape };
}

const visible = (ui) => Object.entries(ui.show).filter(([, on]) => on).map(([name]) => name).sort();

test('nothing is offered while the targets are still being prepared or no input is running', () => {
  const view = new GuideSession(scenarios).view(1000);
  const preparing = describeGuide({ view, source: 'camera', ready: false });
  assert.match(preparing.message, /준비하는 중/);
  assert.deepEqual(visible(preparing), []);
  const idle = describeGuide({ view, source: 'none', ready: true });
  assert.match(idle.message, /카메라를 시작/);
  assert.deepEqual(visible(idle), []);
  assert.deepEqual(Object.values(idle.enable), [false, false, false, false, false]);
  assert.equal(describeGuide({ view: null, source: 'camera', ready: true }).chip.tone, 'idle');
});

test('scanning asks for a closer, larger target and offers only the manual selection', () => {
  const session = new GuideSession(scenarios);
  const ui = describeGuide({ view: session.view(1000), source: 'camera', ready: true, nameOf });
  assert.match(ui.message, /1\/3 이상/);
  assert.equal(ui.chip.tone, 'search');
  assert.deepEqual(visible(ui), ['manual']);
  assert.equal(ui.enable.manual, true);
  assert.equal(ui.enable.confirmProduct, false);
});

test('a target seen for fewer than the required frames is not yet a candidate', () => {
  const fresh = new GuideSession(scenarios);
  fresh.observe(resultFor(AIRCON), 1100);
  const ui = describeGuide({ view: fresh.view(1100), source: 'camera', ready: true, nameOf });
  assert.match(ui.message, /확인하는 중/);
  assert.equal(ui.chip.tone, 'ok');
  assert.deepEqual(visible(ui), ['manual']);
});

test('an ambiguous or lost target is an explicit non-success state', () => {
  const session = new GuideSession(scenarios);
  session.observe({ status: 'ambiguous', targetId: null }, 1100);
  const ambiguous = describeGuide({ view: session.view(1100), source: 'camera', ready: true, nameOf });
  assert.match(ambiguous.message, /미확정/);
  assert.equal(ambiguous.chip.tone, 'warn');
  assert.deepEqual(visible(ambiguous), ['manual']);
  session.observe({ status: 'none', targetId: null }, 1200);
  const missing = describeGuide({ view: session.view(1200), source: 'camera', ready: true, longMiss: true, nameOf });
  assert.match(missing.message, /제품 확인 필요/);
  assert.doesNotMatch(missing.message, /합성 (에어컨|세탁기|냉장고|모니터)/);
});

test('a candidate needs the user to confirm and cannot be confirmed once it is no longer tracked', () => {
  const state = setup(PHASE.CANDIDATE);
  const { ui } = guide(state);
  assert.match(ui.message, /감지 후보: 합성 에어컨 · 확인 필요/);
  assert.match(ui.detail, /자동으로 확정하지 않습니다/);
  assert.deepEqual(visible(ui), ['confirmProduct', 'manual']);
  assert.equal(ui.enable.confirmProduct, true);
  assert.equal(ui.chip.text, '추적 중 · 합성 에어컨');
  state.clock.tick(900);
  const stale = guide(state).ui;
  assert.match(stale.message, /놓쳤습니다/);
  assert.equal(stale.enable.confirmProduct, false);
  assert.equal(stale.chip.tone, 'search');
});

test('after confirmation the camera source and a manual selection are told apart', () => {
  const fromCamera = guide(setup(PHASE.SYMPTOM)).ui;
  assert.equal(fromCamera.heading, '2. 증상 확인');
  assert.match(fromCamera.message, /합성 에어컨 · 시원한 바람이 나오지 않아요/);
  assert.match(fromCamera.sourceNote, /사용자가 확인/);
  assert.deepEqual(visible(fromCamera), ['restart', 'start']);
  assert.equal(fromCamera.enable.start, true);
  const manual = guide(setup(PHASE.SYMPTOM, { source: 'manual' })).ui;
  assert.match(manual.sourceNote, /인식 성공이 아닙니다/);
  assert.doesNotMatch(manual.sourceNote, /사용자가 확인/);
});

test('guiding shows the step, its instruction and enables the manual confirmation only while tracked', () => {
  const state = setup(PHASE.GUIDING);
  const { ui, shape } = guide(state);
  assert.equal(shape.kind, 'guidance');
  assert.equal(ui.heading, '3. Overlay 안내');
  assert.match(ui.message, /^단계 1\/3 · POWER$/);
  assert.equal(ui.detail, AIRCON.controls[0].instruction);
  assert.match(ui.overlayNote, /노란 영역/);
  assert.match(ui.overlayNote, /판정하지 않습니다/);
  assert.deepEqual(visible(ui), ['restart', 'step']);
  assert.equal(ui.enable.step, true);

  state.clock.tick(900);
  const lost = guide(state).ui;
  assert.equal(lost.enable.step, false);
  assert.match(lost.overlayNote, /추적 상실/);
  assert.equal(lost.chip.text, '추적 상실');
});

test('another target hides the guidance and disables the confirmation', () => {
  const state = setup(PHASE.GUIDING);
  state.observe(1, resultFor(WASHER));
  const { ui, shape } = guide(state);
  assert.equal(shape.kind, 'none');
  assert.equal(ui.enable.step, false);
  assert.match(ui.overlayNote, /다른 타깃/);
  assert.equal(ui.chip.tone, 'warn');
  assert.match(ui.chip.text, /다른 타깃 · 합성 세탁기/);
});

test('a control outside the frame cannot be confirmed', () => {
  const state = setup(PHASE.GUIDING);
  state.observe(1, resultFor(AIRCON, pose({ cx: FRAME.width + 400 })));
  const { ui, shape } = guide(state);
  assert.equal(shape.kind, 'guidance');
  assert.equal(shape.controlInFrame, false);
  assert.equal(ui.enable.step, false);
  assert.match(ui.overlayNote, /화면 밖/);
});

test('an unusable pose hides the overlay and says so', () => {
  const state = setup(PHASE.GUIDING);
  const view = state.session.view(state.clock.t);
  const ui = describeGuide({ view, shape: null, source: 'camera', ready: true, nameOf });
  assert.equal(ui.enable.step, false);
  assert.match(ui.overlayNote, /불안정/);
});

test('completion says that the practice was only a displayed state, not a fix', () => {
  const ui = guide(setup(PHASE.COMPLETED)).ui;
  assert.equal(ui.heading, '완료');
  assert.match(ui.message, /실제 고장 해결 미판정/);
  assert.deepEqual(visible(ui), ['restart']);
  assert.equal(ui.enable.restart, true);
  assert.equal(ui.enable.step, false);
});

test('a target change shows an alert and returns to the search', () => {
  const state = setup(PHASE.GUIDING);
  state.observe(3, resultFor(WASHER));
  const { ui, view } = guide(state);
  assert.equal(view.phase, PHASE.CANDIDATE);
  assert.match(ui.alert, /처음부터 다시/);
  assert.match(ui.message, /감지 후보: 합성 세탁기/);
});

test('pausing offers nothing and does not claim any tracking', () => {
  const state = setup(PHASE.GUIDING);
  state.session.pause();
  const { ui } = guide(state);
  assert.match(ui.message, /일시정지/);
  assert.equal(ui.chip.text, '일시정지');
  assert.deepEqual(visible(ui), []);
  assert.deepEqual(Object.values(ui.enable), [false, false, false, false, false]);
});

test('the panel never enables what the session forbids, even for a stale shape or an odd view', () => {
  const candidate = setup(PHASE.CANDIDATE);
  const candidateView = candidate.session.view(candidate.clock.t);
  const forbidConfirm = describeGuide({ view: { ...candidateView, canConfirmProduct: false }, source: 'camera', ready: true, nameOf });
  assert.equal(forbidConfirm.show.confirmProduct, true);
  assert.equal(forbidConfirm.enable.confirmProduct, false);

  const symptom = setup(PHASE.SYMPTOM);
  const symptomView = symptom.session.view(symptom.clock.t);
  const forbidStart = describeGuide({ view: { ...symptomView, canStart: false }, source: 'camera', ready: true, nameOf });
  assert.equal(forbidStart.show.start, true);
  assert.equal(forbidStart.enable.start, false);

  const guiding = setup(PHASE.GUIDING);
  const shownShape = guide(guiding).shape;
  assert.equal(shownShape.kind, 'guidance');
  const view = guiding.session.view(guiding.clock.t);
  const forbidStep = describeGuide({ view: { ...view, canConfirmStep: false }, shape: shownShape, source: 'camera', ready: true, nameOf });
  assert.equal(forbidStep.show.step, true);
  assert.equal(forbidStep.enable.step, false);

  guiding.clock.tick(900);
  const later = describeGuide({ view: guiding.session.view(guiding.clock.t), shape: shownShape, source: 'camera', ready: true, nameOf });
  assert.equal(later.enable.step, false, 'a shape drawn earlier must not enable a confirmation after tracking was lost');

  const odd = describeGuide({
    view: { ...view, overlay: { visible: false, reason: 'constructor' } }, shape: shownShape, source: 'camera', ready: true, nameOf,
  });
  assert.equal(odd.overlayNote, 'Overlay를 숨겼습니다.');
});

test('refusals have a Korean message and unknown reasons never echo the raw value', () => {
  const reasons = ['not-tracking', 'other-target', 'paused', 'no-candidate', 'stale', 'wrong-step', 'duplicate', 'out-of-frame', 'unstable'];
  for (const reason of reasons) {
    assert.match(describeRefusal(reason), /[가-힣]/);
    assert.notEqual(describeRefusal(reason), describeRefusal('unknown-reason'));
  }
  const unknown = describeRefusal('<script>alert(1)</script>');
  assert.match(unknown, /확인할 수 없습니다/);
  assert.doesNotMatch(unknown, /script/);
  assert.match(describeRefusal(undefined), /확인할 수 없습니다/);
  assert.match(describeRefusal('constructor'), /확인할 수 없습니다/);
});

test('a refused tap names the reason the overlay was hidden, else why the drawn control cannot be confirmed', () => {
  const view = (reason) => ({ overlay: { visible: reason === 'visible', reason } });
  const drawn = { kind: 'guidance', reason: 'visible', confirmable: false };
  for (const reason of ['not-tracking', 'other-target', 'paused']) {
    assert.equal(refusalForTap(view(reason), { kind: 'none', reason: 'stale' }), reason);
    assert.equal(refusalForTap(view(reason), null), reason);
    assert.equal(refusalForTap(view(reason), drawn), reason);
  }
  assert.equal(refusalForTap(view('visible'), drawn), 'out-of-frame');
  assert.equal(refusalForTap({}, drawn), 'out-of-frame');
  assert.equal(refusalForTap(view('visible'), { kind: 'none', reason: 'bad-pose' }), 'unstable');
  assert.equal(refusalForTap(view('visible'), null), 'unstable');
  assert.equal(refusalForTap(view('not-guiding'), null), 'unstable');
  assert.equal(refusalForTap(view('constructor'), null), 'unstable');
  assert.equal(refusalForTap(null, null), 'unstable');
  assert.equal(refusalForTap(undefined, undefined), 'unstable');
});

test('the refusal follows the real session and overlay in each situation that blocks the confirmation', () => {
  const reasonOf = (state) => {
    const { view, shape } = guide(state);
    assert.equal(guide(state).ui.enable.step, false, 'the button is disabled in every one of these situations');
    return refusalForTap(view, shape);
  };

  const lost = setup(PHASE.GUIDING);
  lost.clock.tick(900);
  assert.equal(reasonOf(lost), 'not-tracking');
  assert.match(describeRefusal('not-tracking'), /대상이 보이지 않아/);

  const other = setup(PHASE.GUIDING);
  other.observe(1, resultFor(WASHER));
  assert.equal(reasonOf(other), 'other-target');
  assert.match(describeRefusal('other-target'), /다른 타깃/);

  const paused = setup(PHASE.GUIDING);
  paused.session.pause();
  assert.equal(reasonOf(paused), 'paused');

  const outside = setup(PHASE.GUIDING);
  outside.observe(1, resultFor(AIRCON, pose({ cx: FRAME.width + 400 })));
  assert.equal(reasonOf(outside), 'out-of-frame');

  const speck = setup(PHASE.GUIDING);
  speck.observe(1, { ...resultFor(AIRCON), quad: [[5, 5], [5, 5], [5, 5], [5, 5]] });
  assert.equal(reasonOf(speck), 'unstable');
});

test('a refusal stays tied to the phase and generation it was issued in', () => {
  assert.equal(refusalContext(null), '');
  assert.equal(refusalContext(undefined), '');
  assert.notEqual(refusalContext({ phase: PHASE.GUIDING, generation: 3 }), refusalContext({ phase: PHASE.SCANNING, generation: 3 }));
  assert.notEqual(refusalContext({ phase: PHASE.GUIDING, generation: 3 }), refusalContext({ phase: PHASE.GUIDING, generation: 4 }));
  assert.equal(refusalContext({ phase: PHASE.GUIDING, generation: 3 }), refusalContext({ phase: PHASE.GUIDING, generation: 3, tracking: false }));

  // Losing the target does not change the context, so the refusal keeps explaining the tap that was refused.
  const lost = setup(PHASE.GUIDING);
  const issued = refusalContext(lost.session.view(lost.clock.t));
  lost.clock.tick(900);
  assert.equal(refusalContext(lost.session.view(lost.clock.t)), issued);

  // Another target restarts the session: the old refusal no longer applies.
  const other = setup(PHASE.GUIDING);
  const before = refusalContext(other.session.view(other.clock.t));
  other.observe(3, resultFor(WASHER));
  assert.equal(other.session.view(other.clock.t).notice, 'target-changed');
  assert.notEqual(refusalContext(other.session.view(other.clock.t)), before);

  // A manual restart and a confirmed step also move on.
  const manual = setup(PHASE.GUIDING);
  const guiding = refusalContext(manual.session.view(manual.clock.t));
  manual.session.restart();
  assert.notEqual(refusalContext(manual.session.view(manual.clock.t)), guiding);

  const step = setup(PHASE.GUIDING);
  const first = step.session.view(step.clock.t);
  const stepContext = refusalContext(first);
  assert.equal(step.session.confirmStep({ stepId: first.stepId, generation: first.generation }, step.clock.t).ok, true);
  assert.notEqual(refusalContext(step.session.view(step.clock.t)), stepContext);
});
