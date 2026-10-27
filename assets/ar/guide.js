/**
 * What the guide panel of the camera AR demo says and which buttons it offers. Pure: no DOM or timers.
 *
 * Everything is derived from the session view, the overlay shape that is being drawn and the state of the input.
 * Unknown, ambiguous and lost targets are always shown as explicit non-success states.
 */

import { PHASE } from './session.js';

const REFUSALS = Object.freeze({
  'not-tracking': '대상이 보이지 않아 확인하지 못했습니다. 타깃을 다시 비춘 뒤 눌러 주세요.',
  'other-target': '다른 타깃이 보여 확인하지 못했습니다. 선택한 제품의 타깃을 비춰 주세요.',
  paused: '일시정지 중에는 확인할 수 없습니다.',
  'no-candidate': '후보가 바뀌었습니다. 화면의 안내를 다시 확인해 주세요.',
  stale: '화면이 바뀌었습니다. 현재 단계를 다시 확인해 주세요.',
  'wrong-step': '화면이 바뀌었습니다. 현재 단계를 다시 확인해 주세요.',
  duplicate: '이미 확인한 단계입니다.',
  'out-of-frame': '조작 영역이 화면 밖에 있어 확인하지 못했습니다. 타깃 전체가 보이게 비춰 주세요.',
  unstable: '추적 결과가 불안정해 확인하지 못했습니다. 타깃을 천천히 비춰 주세요.',
});

/** Korean message for a refused confirmation. Unknown reasons get a generic text, never the raw reason. */
export function describeRefusal(reason) {
  return Object.prototype.hasOwnProperty.call(REFUSALS, reason) ? REFUSALS[reason] : '지금은 확인할 수 없습니다.';
}

const HIDDEN_OVERLAY_REASONS = Object.freeze(['not-tracking', 'other-target', 'paused']);

/**
 * Refusal reason for a tap on the confirm button when the overlay that was drawn does not allow a confirmation:
 * the reason the session hid the overlay, else out-of-frame for a drawn control, else an unusable pose.
 */
export function refusalForTap(view, shape) {
  const hiddenBy = view && view.overlay ? view.overlay.reason : null;
  if (HIDDEN_OVERLAY_REASONS.includes(hiddenBy)) return hiddenBy;
  return shape && shape.kind === 'guidance' ? 'out-of-frame' : 'unstable';
}

/** Names the session state a refused tap belongs to, so the message can be dropped once the session moves on. */
export function refusalContext(view) {
  return view ? `${view.phase}:${view.generation}` : '';
}

const OVERLAY_NOTES = Object.freeze({
  'not-tracking': '추적 상실 · Overlay를 숨겼습니다. 타깃을 다시 비춰 주세요.',
  'other-target': '다른 타깃이 보입니다 · Overlay를 숨겼습니다. 선택한 제품의 타깃을 비춰 주세요.',
  paused: '일시정지 · Overlay를 숨겼습니다.',
});

const HEADINGS = Object.freeze({
  [PHASE.SCANNING]: '1. 제품 찾기',
  [PHASE.CANDIDATE]: '1. 제품 찾기',
  [PHASE.SYMPTOM]: '2. 증상 확인',
  [PHASE.GUIDING]: '3. Overlay 안내',
  [PHASE.COMPLETED]: '완료',
});

const flags = () => ({ confirmProduct: false, manual: false, start: false, step: false, restart: false });

function describeChip(view, nameOf) {
  if (view.tracking) {
    const name = nameOf(view.trackedTargetId);
    const inGuide = view.phase === PHASE.SYMPTOM || view.phase === PHASE.GUIDING || view.phase === PHASE.COMPLETED;
    const expected = inGuide && view.scenario ? view.scenario.target_id : view.trackedTargetId;
    return expected === view.trackedTargetId
      ? { tone: 'ok', text: `추적 중 · 합성 ${name}` }
      : { tone: 'warn', text: `다른 타깃 · 합성 ${name}` };
  }
  if (view.status === 'ambiguous') return { tone: 'warn', text: '여러 타깃이 비슷하게 보임 · 미확정' };
  if (view.phase === PHASE.SYMPTOM || view.phase === PHASE.GUIDING) return { tone: 'warn', text: '추적 상실' };
  return { tone: 'search', text: '타깃 찾는 중' };
}

function describeScanning(view, longMiss, ui) {
  ui.show.manual = true;
  ui.enable.manual = true;
  if (view.status === 'ambiguous') {
    ui.message = '등록 타깃이 둘 이상 비슷하게 보입니다. 타깃 하나가 화면에 온전히 들어오게 비춰 주세요. (제품 미확정)';
  } else if (view.tracking) {
    ui.message = '타깃을 확인하는 중입니다. 잠시 그대로 비춰 주세요.';
  } else if (longMiss) {
    ui.message = '등록된 타깃을 찾지 못했습니다. 미등록 제품이거나 추적이 불확실합니다. 제품 확인 필요 · 타깃 전체가 보이게 거리를 조절해 보세요.';
  } else {
    ui.message = '등록된 합성 타깃을 찾는 중입니다. 타깃 전체가 보이고 화면의 1/3 이상 차지하도록 비춰 주세요.';
  }
}

function describeCandidate(view, ui) {
  ui.show.confirmProduct = true;
  ui.show.manual = true;
  ui.enable.manual = true;
  if (view.candidate) {
    ui.enable.confirmProduct = view.canConfirmProduct;
    ui.message = `감지 후보: 합성 ${view.candidate.product} · 확인 필요`;
    ui.detail = '맞으면 아래 버튼으로 확인하세요. 자동으로 확정하지 않습니다.';
  } else {
    ui.message = '후보를 놓쳤습니다. 타깃을 다시 비춰 주세요.';
  }
}

function describeSymptom(view, ui) {
  const scenario = view.scenario;
  ui.show.start = true;
  ui.enable.start = view.canStart;
  ui.show.restart = true;
  ui.enable.restart = true;
  ui.message = `합성 ${scenario.product} · ${scenario.issue}`;
  ui.detail = scenario.summary;
  ui.sourceNote = view.source === 'camera'
    ? '카메라가 찾은 후보를 사용자가 확인했습니다.'
    : '수동 선택입니다. 인식 성공이 아닙니다. 이 제품의 타깃을 비추면 윤곽이 표시됩니다.';
}

function describeGuiding(view, shape, ui) {
  ui.show.step = true;
  ui.show.restart = true;
  ui.enable.restart = true;
  ui.message = `단계 ${view.stepIndex + 1}/${view.stepCount}${view.step ? ` · ${view.step.label}` : ''}`;
  ui.detail = view.step ? view.step.instruction : '';
  const guidance = Boolean(shape) && shape.kind === 'guidance';
  ui.enable.step = view.canConfirmStep && guidance && shape.confirmable;
  if (!view.overlay.visible) {
    ui.overlayNote = Object.prototype.hasOwnProperty.call(OVERLAY_NOTES, view.overlay.reason)
      ? OVERLAY_NOTES[view.overlay.reason] : 'Overlay를 숨겼습니다.';
  } else if (!guidance) {
    ui.overlayNote = '추적 결과가 불안정해 Overlay를 숨겼습니다. 타깃을 천천히 비춰 주세요.';
  } else if (!shape.confirmable) {
    ui.overlayNote = '조작 영역이 화면 밖입니다. 타깃 전체가 보이게 비춰 주세요.';
  } else {
    ui.overlayNote = '노란 영역이 현재 단계 위치입니다. 화면 표시를 직접 확인한 뒤 누르세요. 앱이 상태를 판정하지 않습니다.';
  }
}

function describeCompleted(ui) {
  ui.show.restart = true;
  ui.enable.restart = true;
  ui.message = '표시 상태 실습 완료 · 실제 고장 해결 미판정';
  ui.detail = '합성 화면의 표시만 확인했습니다. 실제 제품의 안전·성능·고장 해결을 보증하지 않습니다.';
}

/**
 * @param view     GuideSession.view() taken at the time of drawing
 * @param shape    describeOverlay() result for the same moment
 * @param source   'none' | 'camera' | 'sim'
 * @param ready    registered targets are available
 * @param longMiss nothing registered has been seen for a while
 * @param nameOf   (targetId) => product name used in the chip
 */
export function describeGuide({
  view, shape = null, source = 'none', ready = false, longMiss = false, nameOf = (id) => id,
}) {
  const ui = {
    chip: { tone: 'idle', text: '대기 중' },
    heading: HEADINGS[PHASE.SCANNING],
    message: '',
    detail: '',
    overlayNote: '',
    sourceNote: '',
    alert: view && view.notice === 'target-changed' ? '다른 타깃이 감지되어 처음부터 다시 시작했습니다.' : '',
    show: flags(),
    enable: flags(),
  };
  if (!ready) {
    ui.message = '합성 타깃 4종을 이 기기에서 준비하는 중입니다.';
    return ui;
  }
  if (!view || source === 'none') {
    ui.message = '카메라를 시작하거나 합성 영상으로 확인해 보세요.';
    return ui;
  }
  ui.heading = HEADINGS[view.phase] || HEADINGS[PHASE.SCANNING];
  if (view.paused) {
    ui.chip = { tone: 'warn', text: '일시정지' };
    ui.message = '일시정지됨. 화면으로 돌아오면 다시 찾습니다.';
    return ui;
  }
  ui.chip = describeChip(view, nameOf);
  if (view.phase === PHASE.CANDIDATE) describeCandidate(view, ui);
  else if (view.phase === PHASE.SYMPTOM) describeSymptom(view, ui);
  else if (view.phase === PHASE.GUIDING) describeGuiding(view, shape, ui);
  else if (view.phase === PHASE.COMPLETED) describeCompleted(ui);
  else describeScanning(view, longMiss, ui);
  return ui;
}
