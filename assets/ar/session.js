/**
 * Guided-session rules of the camera AR demo. Pure state machine: no DOM, camera or network access.
 *
 * Phases: scanning -> candidate -> symptom -> guiding -> completed.
 * Evidence rules:
 *  - a candidate needs several consecutive tracked frames of the same registered target;
 *  - every confirmation and every overlay needs a fresh observation of the selected target;
 *  - loss, ambiguity, a stale observation, pause or another target hides the overlay at once;
 *  - steps are confirmed manually, in order, once, against the generation that was shown.
 */

export const PHASE = Object.freeze({
  SCANNING: 'scanning',
  CANDIDATE: 'candidate',
  SYMPTOM: 'symptom',
  GUIDING: 'guiding',
  COMPLETED: 'completed',
});

export const DEFAULT_OPTIONS = Object.freeze({
  candidateFrames: 3,
  freshMs: 500,
});

const refuse = (reason) => ({ ok: false, reason });

export class GuideSession {
  constructor(scenarios, options = {}) {
    if (!Array.isArray(scenarios) || scenarios.length === 0) throw new TypeError('scenarios are required');
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.byId = new Map();
    this.byTarget = new Map();
    for (const scenario of scenarios) {
      const valid = scenario && typeof scenario.id === 'string' && typeof scenario.target_id === 'string'
        && Array.isArray(scenario.controls) && scenario.controls.length > 0
        && scenario.controls.every((control) => control && typeof control.id === 'string');
      if (!valid) throw new TypeError(`invalid scenario: ${scenario && scenario.id}`);
      if (this.byId.has(scenario.id) || this.byTarget.has(scenario.target_id)) {
        throw new TypeError(`duplicate scenario: ${scenario.id}`);
      }
      this.byId.set(scenario.id, scenario);
      this.byTarget.set(scenario.target_id, scenario);
    }
    this.generation = 0;
    this.paused = false;
    this.current = null;
    this.status = 'none';
    this.streak = { targetId: null, count: 0 };
    this.clear();
  }

  clear() {
    this.phase = PHASE.SCANNING;
    this.candidateId = null;
    this.selectedId = null;
    this.source = null;
    this.stepIndex = 0;
    this.completions = [];
    this.notice = null;
  }

  /** Back to target search. Anything shown before is no longer valid evidence. */
  restart() {
    this.generation++;
    this.clear();
  }

  /** The tracker result of one camera frame, or null when no frame could be analysed. */
  observe(result, now) {
    if (this.paused) return this.view(now);
    const tracked = Boolean(result) && result.status === 'tracked' && this.byTarget.has(result.targetId);
    this.status = tracked ? 'tracked' : (result && result.status === 'ambiguous' ? 'ambiguous' : 'none');
    if (tracked) {
      this.current = { targetId: result.targetId, at: now };
      this.streak = this.streak.targetId === result.targetId
        ? { targetId: result.targetId, count: this.streak.count + 1 }
        : { targetId: result.targetId, count: 1 };
    } else {
      this.current = null;
      this.streak = { targetId: null, count: 0 };
    }
    this.advance();
    return this.view(now);
  }

  advance() {
    const { candidateFrames } = this.options;
    if (this.phase === PHASE.SYMPTOM || this.phase === PHASE.GUIDING) {
      const selectedTarget = this.byId.get(this.selectedId).target_id;
      if (this.streak.targetId !== null && this.streak.targetId !== selectedTarget
        && this.streak.count >= candidateFrames) {
        this.generation++;
        this.clear();
        this.notice = 'target-changed';
      }
    }
    if (this.phase === PHASE.SCANNING || this.phase === PHASE.CANDIDATE) {
      const ready = this.streak.count >= candidateFrames ? this.streak.targetId : null;
      this.phase = ready ? PHASE.CANDIDATE : PHASE.SCANNING;
      this.candidateId = ready ? this.byTarget.get(ready).id : null;
    }
  }

  /** Page hidden or camera suspended: nothing observed before counts afterwards. */
  pause() {
    this.paused = true;
    this.current = null;
    this.status = 'none';
    this.streak = { targetId: null, count: 0 };
    if (this.phase === PHASE.CANDIDATE) this.advance();
  }

  resume() {
    this.paused = false;
  }

  isTracking(targetId, now) {
    if (this.paused || this.current === null || this.current.targetId !== targetId) return false;
    const age = now - this.current.at;
    return age >= 0 && age <= this.options.freshMs;
  }

  /** `source` is `camera` (candidate confirmed by the user) or `manual` (selected without recognition). */
  confirmProduct({ source, scenarioId }, now) {
    if (this.paused) return refuse('paused');
    const scenario = this.byId.get(scenarioId);
    if (!scenario) return refuse('unknown-scenario');
    if (this.phase !== PHASE.SCANNING && this.phase !== PHASE.CANDIDATE) return refuse('wrong-phase');
    if (source === 'camera') {
      if (this.phase !== PHASE.CANDIDATE || this.candidateId !== scenario.id) return refuse('no-candidate');
      if (!this.isTracking(scenario.target_id, now)) return refuse('not-tracking');
    } else if (source !== 'manual') {
      return refuse('bad-source');
    }
    this.generation++;
    this.clear();
    this.phase = PHASE.SYMPTOM;
    this.selectedId = scenario.id;
    this.source = source;
    return { ok: true, reason: 'accepted' };
  }

  startGuidance() {
    if (this.phase !== PHASE.SYMPTOM) return refuse('wrong-phase');
    this.generation++;
    this.phase = PHASE.GUIDING;
    this.stepIndex = 0;
    this.completions = [];
    return { ok: true, reason: 'accepted' };
  }

  stepIdAt(index) {
    const scenario = this.byId.get(this.selectedId);
    return scenario && scenario.controls[index] ? `${scenario.id}/${scenario.controls[index].id}` : null;
  }

  /** Manual confirmation of the step the user was shown. Automatic completion does not exist in this demo. */
  confirmStep({ stepId, generation }, now) {
    if (this.completions.some((entry) => entry.stepId === stepId)) return refuse('duplicate');
    if (this.phase !== PHASE.GUIDING) return refuse('not-guiding');
    if (stepId !== this.stepIdAt(this.stepIndex)) return refuse('wrong-step');
    if (generation !== this.generation) return refuse('stale');
    if (!this.isTracking(this.byId.get(this.selectedId).target_id, now)) return refuse('not-tracking');
    this.completions.push({ stepId, source: 'manual', generation, at: now });
    this.generation++;
    this.stepIndex++;
    this.notice = null;
    if (this.stepIndex >= this.byId.get(this.selectedId).controls.length) this.phase = PHASE.COMPLETED;
    return { ok: true, reason: 'accepted', completed: this.phase === PHASE.COMPLETED };
  }

  view(now) {
    const scenario = this.selectedId ? this.byId.get(this.selectedId) : null;
    const candidate = this.candidateId ? this.byId.get(this.candidateId) : null;
    const fresh = this.current !== null && now - this.current.at >= 0 && now - this.current.at <= this.options.freshMs;
    const trackedTargetId = !this.paused && fresh ? this.current.targetId : null;
    const selectedTracked = scenario !== null && trackedTargetId === scenario.target_id;
    const guiding = this.phase === PHASE.GUIDING;
    let reason = 'visible';
    if (!guiding) reason = 'not-guiding';
    else if (this.paused) reason = 'paused';
    else if (trackedTargetId === null) reason = 'not-tracking';
    else if (!selectedTracked) reason = 'other-target';
    const step = scenario && guiding ? scenario.controls[this.stepIndex] : null;
    return {
      phase: this.phase,
      paused: this.paused,
      status: trackedTargetId === null && this.status === 'tracked' ? 'none' : this.status,
      tracking: trackedTargetId !== null,
      trackedTargetId,
      candidate: this.phase === PHASE.CANDIDATE && trackedTargetId === candidate.target_id ? candidate : null,
      scenario,
      source: this.source,
      generation: this.generation,
      stepIndex: this.stepIndex,
      stepCount: scenario ? scenario.controls.length : 0,
      step,
      stepId: guiding ? this.stepIdAt(this.stepIndex) : null,
      canConfirmProduct: this.phase === PHASE.CANDIDATE && trackedTargetId === candidate.target_id,
      canStart: this.phase === PHASE.SYMPTOM,
      canConfirmStep: guiding && selectedTracked,
      overlay: { visible: reason === 'visible', reason },
      completions: this.completions.map((entry) => ({ ...entry })),
      notice: this.notice,
    };
  }
}
