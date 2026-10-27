/**
 * What the AR layer may draw for one analysed frame. Pure: no DOM or canvas.
 *
 * Every shape is projected through the homography of the current tracked frame and is returned in
 * analysed-frame pixels. There is no fixed screen position, no remembered pose and no overlay for a
 * target that is not tracked in the frame being shown.
 */

import { centroid, isConvexClockwise, polygonArea, projectRect } from './geometry.js';
import { PHASE } from './session.js';

const MIN_OUTLINE_AREA = 64;
const MIN_CONTROL_AREA = 16;

const NONE = Object.freeze({
  kind: 'none', reason: 'none', outline: null, control: null, label: null, controlInFrame: false, confirmable: false,
});

const hidden = (reason) => ({ ...NONE, reason });

const isQuad = (quad) => Array.isArray(quad) && quad.length === 4
  && quad.every((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]));

/** A quadrilateral worth drawing: four finite points, walked top-left to bottom-left, convex and not a speck. */
const isDrawable = (quad, minArea) => isQuad(quad) && isConvexClockwise(quad) && polygonArea(quad) >= minArea;

const isRect = (rect) => Array.isArray(rect) && rect.length === 4 && rect.every((v) => Number.isFinite(v));

const insideFrame = (point, frame) => Boolean(frame) && frame.width > 0 && frame.height > 0
  && point[0] >= 0 && point[0] <= frame.width && point[1] >= 0 && point[1] <= frame.height;

/**
 * @param view   GuideSession.view() taken at the time of drawing
 * @param result tracker result of the latest analysed frame
 * @param sizeOf (targetId) => { width, height } of the registered reference image
 * @param frame  { width, height } of the analysed frame
 * @returns { kind: 'none'|'candidate'|'confirmed'|'guidance', reason, outline, control, label, controlInFrame, confirmable }
 */
export function describeOverlay(view, result, sizeOf, frame) {
  if (!view || !result) return hidden('no-result');
  if (result.status !== 'tracked' || !result.H || !isQuad(result.quad)) return hidden('not-tracked');
  if (!isDrawable(result.quad, MIN_OUTLINE_AREA)) return hidden('bad-pose');
  if (!view.tracking || result.targetId !== view.trackedTargetId) return hidden('stale');
  const outline = result.quad;

  if (view.phase === PHASE.CANDIDATE) {
    if (!view.candidate || view.candidate.target_id !== result.targetId) return hidden('no-candidate');
    return { ...NONE, kind: 'candidate', reason: 'candidate', outline, label: `감지 후보 · 합성 ${view.candidate.product} · 확인 필요` };
  }

  const scenario = view.scenario;
  if (view.phase !== PHASE.SYMPTOM && view.phase !== PHASE.GUIDING) return hidden('no-overlay-phase');
  if (!scenario || scenario.target_id !== result.targetId) return hidden('other-target');

  if (view.phase === PHASE.SYMPTOM) {
    return { ...NONE, kind: 'confirmed', reason: 'confirmed', outline, label: `합성 ${scenario.product} · 사용자 확인` };
  }

  if (!view.overlay.visible || !view.step) return hidden(view.overlay.reason);
  const size = sizeOf(result.targetId);
  if (!size || !(size.width > 0) || !(size.height > 0)) return hidden('unknown-target');
  if (!isRect(view.step.rect)) return hidden('bad-step');
  const [left, top, right, bottom] = view.step.rect;
  const control = projectRect(result.H, left * size.width, top * size.height, right * size.width, bottom * size.height);
  if (!isDrawable(control, MIN_CONTROL_AREA)) return hidden('bad-pose');
  const controlInFrame = insideFrame(centroid(control), frame);
  return {
    kind: 'guidance',
    reason: 'visible',
    outline,
    control,
    label: `${view.stepIndex + 1}/${view.stepCount} ${view.step.label} → ${view.step.expected}`,
    controlInFrame,
    confirmable: controlInFrame,
  };
}
