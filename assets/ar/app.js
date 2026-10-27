/**
 * Camera AR demo page. Connects the tested pure modules to the camera, the canvas and the DOM.
 *
 * Frames are analysed on this device only. They are not stored, uploaded or logged, and nothing here
 * decides what is drawn: the overlay shape comes from describeOverlay() and the panel from describeGuide().
 */

import { ImageTargetTracker } from './tracker.js';
import { GuideSession } from './session.js';
import { describeOverlay } from './overlay.js';
import { describeGuide, describeRefusal, refusalContext, refusalForTap } from './guide.js';
import { FrameBudget } from './budget.js';
import { describeCameraError, openCamera, stopStream } from './camera.js';
import { rgbaToGray } from './image.js';
import { buildMips, clutterGray, renderScene, simulatedPose } from './synthetic.js';

const SIM_FRAME = Object.freeze({ width: 288, height: 512 });
const SIM_SCALE = 0.5;
const SIM_NOISE = 2;
const MIN_INTERVAL_MS = 60;
const UI_TICK_MS = 250;
const HUD_INTERVAL_MS = 500;
const LONG_MISS_MS = 2000;
const REFUSAL_MS = 6000;
const METADATA_TIMEOUT_MS = 8000;
const MAX_ERRORS = 3;
const MAX_GRAY = 512 * 512;
const IMAGE_PATH = /^scenarios\/[a-z0-9-]+\.png$/;

const IDS = [
  'cam', 'stage', 'video', 'sim', 'overlay', 'placeholder', 'chip', 'badge', 'hud', 'startCamera', 'startSim', 'stopSource',
  'simRow', 'simTarget', 'prepare', 'error', 'heading', 'message', 'detail', 'overlayNote', 'sourceNote', 'alert',
  'refusal', 'confirmProduct', 'start', 'step', 'restart', 'manualRow', 'manualProduct', 'manual',
];
const els = {};
for (const id of IDS) els[id] = document.getElementById(id);

const tracker = new ImageTargetTracker();
const budget = new FrameBudget();
let session = null;

const state = {
  ready: false,
  source: 'none',
  starting: false,
  token: 0,
  stream: null,
  refs: new Map(),
  names: new Map(),
  frame: null,
  result: null,
  capture: null,
  grayBuffer: new Uint8Array(MAX_GRAY),
  sourceStartedAt: 0,
  lastTrackedAt: -Infinity,
  sim: { t: 0, lastAt: 0, targetId: null, background: null, mips: new Map(), frameIndex: 0, ctx: null, image: null },
  loop: { active: false, handle: null, kind: null, lastRun: 0 },
  errors: 0,
  stats: { ms: 0, fps: 0, lastAt: 0, hudAt: 0 },
  shownView: null,
  shownShape: null,
  ui: null,
  uiJson: '',
  refusalTimer: null,
  refusalContext: '',
};

const nameOf = (targetId) => state.names.get(targetId) || targetId;

function sizeOf(targetId) {
  const ref = state.refs.get(targetId);
  return ref ? { width: ref.width, height: ref.height } : null;
}

function setText(element, text) {
  element.textContent = text;
  element.hidden = text === '';
}

function setStatus(text) {
  setText(els.prepare, text);
}

function showError(text) {
  setText(els.error, text);
}

function showRefusal(text) {
  clearTimeout(state.refusalTimer);
  state.refusalContext = refusalContext(session ? session.view(performance.now()) : null);
  setText(els.refusal, text);
  // The pinned camera block can leave this line just below the fold on a small phone.
  els.refusal.scrollIntoView({ block: 'nearest' });
  state.refusalTimer = setTimeout(() => setText(els.refusal, ''), REFUSAL_MS);
}

function clearRefusal() {
  clearTimeout(state.refusalTimer);
  state.refusalContext = '';
  setText(els.refusal, '');
}

/* Registered targets ------------------------------------------------------------------------------------------ */

const yieldToUi = () => new Promise((resolve) => setTimeout(resolve, 0));

async function loadScenarios() {
  const response = await fetch('scenarios/catalog.json', { cache: 'no-cache' });
  if (!response.ok) throw new Error('catalog');
  const catalog = await response.json();
  if (catalog.demo !== true || !Array.isArray(catalog.scenarios) || catalog.scenarios.length !== 4) throw new Error('catalog');
  return catalog.scenarios;
}

async function registerTarget(scenario) {
  if (!IMAGE_PATH.test(scenario.image)) throw new Error('image');
  const image = new Image();
  image.src = scenario.image;
  await image.decode();
  const canvas = document.createElement('canvas');
  const width = image.naturalWidth, height = image.naturalHeight;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(image, 0, 0);
  const gray = rgbaToGray(ctx.getImageData(0, 0, width, height).data, width, height);
  tracker.addTarget(scenario.target_id, gray, width, height);
  state.refs.set(scenario.target_id, { gray, width, height });
}

function fillSelect(select, entries) {
  select.textContent = '';
  for (const [value, label] of entries) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }
}

async function prepare() {
  try {
    const scenarios = await loadScenarios();
    for (let i = 0; i < scenarios.length; i++) {
      setStatus(`타깃 등록 중 ${i + 1}/${scenarios.length}`);
      await yieldToUi();
      await registerTarget(scenarios[i]);
    }
    session = new GuideSession(scenarios);
    if (document.hidden) session.pause();
    for (const scenario of scenarios) state.names.set(scenario.target_id, scenario.product);
    fillSelect(els.manualProduct, scenarios.map((s) => [s.id, s.product]));
    fillSelect(els.simTarget, [...scenarios.map((s) => [s.target_id, `합성 ${s.product}`]), ['', '대상 없음 (추적 상실 시험)']]);
    state.sim.targetId = scenarios[0].target_id;
    els.simTarget.value = state.sim.targetId;
    state.ready = true;
    setStatus('');
  } catch (error) {
    setStatus('');
    showError('합성 타깃을 준비하지 못했습니다. 페이지를 새로고침해 주세요.');
  }
  renderSourceButtons();
  refresh();
}

/* Overlay canvas ---------------------------------------------------------------------------------------------- */

function sizeOverlay() {
  const rect = els.stage.getBoundingClientRect();
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  const width = Math.max(1, Math.round(rect.width * ratio));
  const height = Math.max(1, Math.round(rect.height * ratio));
  if (els.overlay.width !== width || els.overlay.height !== height) {
    els.overlay.width = width;
    els.overlay.height = height;
  }
  drawOverlay(state.shownShape);
}

function tracePath(ctx, points) {
  ctx.beginPath();
  points.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
  ctx.closePath();
}

function wrapLines(ctx, text, maxWidth) {
  const lines = [];
  let line = '';
  for (const word of text.split(' ')) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function drawLabel(ctx, text, quad, canvas, unit) {
  const size = Math.max(12, Math.round(unit * 6.5));
  const pad = Math.round(size * 0.5), gap = Math.round(size * 0.4), lineHeight = Math.round(size * 1.3);
  ctx.font = `600 ${size}px system-ui, -apple-system, "Noto Sans KR", "Malgun Gothic", sans-serif`;
  ctx.textBaseline = 'top';
  const lines = wrapLines(ctx, text, canvas.width * 0.9 - pad * 2);
  const boxWidth = Math.ceil(Math.max(...lines.map((line) => ctx.measureText(line).width))) + pad * 2;
  const boxHeight = lines.length * lineHeight + pad * 2;
  const xs = quad.map((p) => p[0]), ys = quad.map((p) => p[1]);
  let y = Math.min(...ys) - boxHeight - gap;
  if (y < gap) y = Math.max(...ys) + gap;
  y = Math.max(gap, Math.min(y, canvas.height - boxHeight - gap));
  const x = Math.max(gap, Math.min((Math.min(...xs) + Math.max(...xs)) / 2 - boxWidth / 2, canvas.width - boxWidth - gap));
  ctx.fillStyle = 'rgba(0,0,0,0.75)';
  ctx.fillRect(x, y, boxWidth, boxHeight);
  ctx.fillStyle = '#fff';
  lines.forEach((line, i) => ctx.fillText(line, x + pad, y + pad + i * lineHeight));
}

/** Draws exactly the shape that describeOverlay() allowed for the frame being shown. */
function drawOverlay(shape) {
  const canvas = els.overlay;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!shape || shape.kind === 'none' || !state.frame) return;
  const sx = canvas.width / state.frame.width, sy = canvas.height / state.frame.height;
  const scaled = (quad) => quad.map(([x, y]) => [x * sx, y * sy]);
  const unit = Math.max(1, canvas.width / 240);
  const outline = scaled(shape.outline);
  ctx.lineJoin = 'round';
  if (shape.kind === 'candidate') {
    ctx.setLineDash([unit * 5, unit * 3]);
    ctx.strokeStyle = '#ff9800';
    ctx.lineWidth = unit * 2;
  } else if (shape.kind === 'confirmed') {
    ctx.strokeStyle = '#2ecc71';
    ctx.lineWidth = unit * 2;
  } else {
    ctx.strokeStyle = '#4dd0e1';
    ctx.lineWidth = unit * 1.2;
  }
  tracePath(ctx, outline);
  ctx.stroke();
  ctx.setLineDash([]);
  let anchor = outline;
  if (shape.kind === 'guidance') {
    const control = scaled(shape.control);
    tracePath(ctx, control);
    ctx.fillStyle = 'rgba(255,214,0,0.35)';
    ctx.fill();
    ctx.strokeStyle = '#ffc000';
    ctx.lineWidth = unit * 2.4;
    ctx.stroke();
    anchor = control;
  }
  drawLabel(ctx, shape.label, anchor, canvas, unit);
}

/* Panel ------------------------------------------------------------------------------------------------------- */

function render(ui) {
  const json = JSON.stringify(ui);
  if (json === state.uiJson) return;
  state.uiJson = json;
  els.chip.textContent = ui.chip.text;
  els.chip.dataset.tone = ui.chip.tone;
  els.heading.textContent = ui.heading;
  els.message.textContent = ui.message;
  for (const key of ['detail', 'overlayNote', 'sourceNote', 'alert']) setText(els[key], ui[key]);
  for (const key of ['confirmProduct', 'start', 'step', 'restart']) {
    els[key].hidden = !ui.show[key];
    els[key].disabled = !ui.enable[key];
  }
  els.manualRow.hidden = !ui.show.manual;
  els.manual.disabled = !ui.enable.manual;
  els.manualProduct.disabled = !ui.enable.manual;
}

function renderHud(now) {
  const stats = state.stats;
  if (now - stats.hudAt < HUD_INTERVAL_MS) return;
  stats.hudAt = now;
  if (state.source === 'none' || !state.frame) {
    els.hud.textContent = '';
    return;
  }
  const result = state.result;
  els.hud.textContent = `분석 ${state.frame.width}×${state.frame.height} · ${stats.fps.toFixed(0)}fps · ${stats.ms.toFixed(0)}ms`
    + ` · 특징점 ${result ? result.keypoints : 0} · 인라이어 ${result ? result.inliers : 0} · ${result ? result.mode : '-'}`;
}

function renderSourceButtons() {
  const active = state.source !== 'none';
  const free = state.ready && !state.starting;
  document.body.dataset.source = state.source;
  els.startCamera.hidden = active;
  els.startSim.hidden = active;
  els.stopSource.hidden = !active;
  els.startCamera.disabled = !free;
  els.startSim.disabled = !free;
}

/** Recomputes what the user sees from the session, the latest tracker result and the clock. */
function refresh() {
  const now = performance.now();
  const view = session ? session.view(now) : null;
  if (state.refusalContext && state.refusalContext !== refusalContext(view)) clearRefusal();
  const shape = view ? describeOverlay(view, state.result, sizeOf, state.frame) : null;
  const waited = state.source === 'none' ? 0 : now - Math.max(state.sourceStartedAt, state.lastTrackedAt);
  const ui = describeGuide({ view, shape, source: state.source, ready: state.ready, longMiss: waited >= LONG_MISS_MS, nameOf });
  state.shownView = view;
  state.shownShape = shape;
  state.ui = ui;
  drawOverlay(shape);
  render(ui);
  renderHud(now);
}

/* Frames ------------------------------------------------------------------------------------------------------ */

function grabCameraFrame() {
  const video = els.video;
  if (video.readyState < 2) return null;
  const size = budget.fit(video.videoWidth, video.videoHeight);
  if (!size) return null;
  let capture = state.capture;
  if (!capture || capture.width !== size.width || capture.height !== size.height) {
    const canvas = capture ? capture.canvas : document.createElement('canvas');
    canvas.width = size.width;
    canvas.height = size.height;
    capture = { canvas, ctx: canvas.getContext('2d', { willReadFrequently: true }), width: size.width, height: size.height };
    state.capture = capture;
    tracker.reset();
  }
  const capturedAt = performance.now();
  capture.ctx.drawImage(video, 0, 0, size.width, size.height);
  const rgba = capture.ctx.getImageData(0, 0, size.width, size.height).data;
  return { gray: rgbaToGray(rgba, size.width, size.height, state.grayBuffer), width: size.width, height: size.height, capturedAt };
}

function paintGray(gray, width, height) {
  const sim = state.sim;
  if (!sim.ctx) {
    els.sim.width = width;
    els.sim.height = height;
    sim.ctx = els.sim.getContext('2d');
    sim.image = sim.ctx.createImageData(width, height);
  }
  const data = sim.image.data;
  for (let i = 0, p = 0; i < gray.length; i++, p += 4) {
    const value = gray[i];
    data[p] = value;
    data[p + 1] = value;
    data[p + 2] = value;
    data[p + 3] = 255;
  }
  sim.ctx.putImageData(sim.image, 0, 0);
}

function grabSimFrame(dt) {
  const sim = state.sim;
  const { width, height } = SIM_FRAME;
  sim.t += dt;
  if (!sim.background) sim.background = clutterGray(width, height, 7);
  const layers = [];
  const ref = sim.targetId ? state.refs.get(sim.targetId) : null;
  if (ref) {
    if (!sim.mips.has(sim.targetId)) sim.mips.set(sim.targetId, buildMips(ref.gray, ref.width, ref.height));
    const H = simulatedPose(sim.t, { refWidth: ref.width, refHeight: ref.height, frameWidth: width, frameHeight: height, scale: SIM_SCALE });
    layers.push({ mips: sim.mips.get(sim.targetId), refWidth: ref.width, refHeight: ref.height, H });
  }
  sim.frameIndex++;
  const capturedAt = performance.now();
  const gray = renderScene({ width, height, background: sim.background, layers, noise: SIM_NOISE, seed: sim.frameIndex });
  paintGray(gray, width, height);
  return { gray, width, height, capturedAt };
}

function noteStats(cost, at) {
  const stats = state.stats;
  stats.ms = stats.ms ? stats.ms * 0.8 + cost * 0.2 : cost;
  if (stats.lastAt) {
    const fps = 1000 / Math.max(1, at - stats.lastAt);
    stats.fps = stats.fps ? stats.fps * 0.8 + fps * 0.2 : fps;
  }
  stats.lastAt = at;
}

function analyse({ gray, width, height, capturedAt }) {
  const result = tracker.process(gray, width, height);
  state.result = result;
  state.frame = { width, height };
  if (result.status === 'tracked') state.lastTrackedAt = capturedAt;
  session.observe(result, capturedAt);
  const cost = performance.now() - capturedAt;
  if (state.source === 'camera' && budget.record(cost).changed) tracker.reset();
  noteStats(cost, capturedAt);
}

/** One analysis cycle: grab a frame, track, feed the session, redraw. `dt` only matters for the simulation. */
function step(dt) {
  if (!session || state.source === 'none') return;
  try {
    const frame = state.source === 'sim' ? grabSimFrame(dt) : grabCameraFrame();
    if (frame) analyse(frame);
    state.errors = 0;
  } catch (error) {
    state.errors++;
    state.result = null;
    session.observe(null, performance.now());
    if (state.errors >= MAX_ERRORS) {
      setSource('none');
      showError('영상을 분석하지 못해 멈췄습니다. 다시 시작해 주세요.');
      return;
    }
  }
  refresh();
}

/* Frame loop -------------------------------------------------------------------------------------------------- */

function schedule() {
  const loop = state.loop;
  if (!loop.active) return;
  if (state.source === 'camera' && typeof els.video.requestVideoFrameCallback === 'function') {
    loop.kind = 'video';
    loop.handle = els.video.requestVideoFrameCallback(onFrame);
  } else {
    loop.kind = 'raf';
    loop.handle = requestAnimationFrame(onFrame);
  }
}

function stopLoop() {
  const loop = state.loop;
  loop.active = false;
  if (loop.handle === null) return;
  if (loop.kind === 'video' && typeof els.video.cancelVideoFrameCallback === 'function') els.video.cancelVideoFrameCallback(loop.handle);
  else cancelAnimationFrame(loop.handle);
  loop.handle = null;
}

function startLoop() {
  stopLoop();
  if (state.source === 'none' || document.hidden) return;
  state.loop.active = true;
  state.loop.lastRun = 0;
  state.sim.lastAt = performance.now();
  schedule();
}

function onFrame() {
  state.loop.handle = null;
  if (!state.loop.active) return;
  const now = performance.now();
  if (now - state.loop.lastRun >= MIN_INTERVAL_MS) {
    state.loop.lastRun = now;
    const dt = Math.min(0.25, Math.max(0, (now - state.sim.lastAt) / 1000));
    state.sim.lastAt = now;
    step(dt);
  }
  schedule();
}

/* Sources ----------------------------------------------------------------------------------------------------- */

function syncAspect() {
  let aspect = 9 / 16;
  if (state.source === 'camera' && els.video.videoWidth > 0 && els.video.videoHeight > 0) {
    aspect = els.video.videoWidth / els.video.videoHeight;
  } else if (state.source === 'sim') {
    aspect = SIM_FRAME.width / SIM_FRAME.height;
  }
  els.stage.style.setProperty('--aspect', String(aspect));
}

/** On a phone the camera block pins to the top; bring it there so the guidance below stays reachable. */
function revealStage() {
  const phone = typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 859px)').matches;
  if (phone && typeof els.cam.scrollIntoView === 'function') els.cam.scrollIntoView({ block: 'start' });
}

/** Switching the input forgets everything seen so far: earlier frames are not evidence for the new source. */
function setSource(kind, stream = null) {
  stopLoop();
  if (state.stream && state.stream !== stream) stopStream(state.stream);
  state.stream = stream;
  if (kind !== 'camera') {
    els.video.srcObject = null;
    els.video.hidden = true;
  }
  state.source = kind;
  state.result = null;
  state.frame = null;
  state.capture = null;
  state.errors = 0;
  state.lastTrackedAt = -Infinity;
  state.sourceStartedAt = performance.now();
  state.stats = { ms: 0, fps: 0, lastAt: 0, hudAt: 0 };
  if (session) session.restart();
  tracker.reset();
  clearRefusal();
  els.video.hidden = kind !== 'camera';
  els.sim.hidden = kind !== 'sim';
  els.placeholder.hidden = kind !== 'none';
  els.badge.hidden = kind === 'none';
  els.badge.textContent = kind === 'sim' ? '시뮬레이션 · 실제 카메라 아님' : '카메라 · 영상은 이 기기에서만 분석';
  els.simRow.hidden = kind !== 'sim';
  syncAspect();
  sizeOverlay();
  renderSourceButtons();
  if (kind !== 'none') revealStage();
  startLoop();
  refresh();
}

function whenSized(video) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      video.removeEventListener('loadedmetadata', onMetadata);
      reject(new Error('timeout'));
    }, METADATA_TIMEOUT_MS);
    function onMetadata() {
      clearTimeout(timer);
      resolve();
    }
    video.addEventListener('loadedmetadata', onMetadata, { once: true });
  });
}

function watchTrack(stream) {
  const track = stream.getVideoTracks()[0];
  if (!track) return;
  track.addEventListener('ended', () => {
    if (state.stream !== stream) return;
    setSource('none');
    showError('카메라 연결이 끊겼습니다. 다시 시작해 주세요.');
  });
}

/** A pending camera start or a source change makes every earlier asynchronous step stale. */
function cancelPending() {
  state.token++;
  state.starting = false;
}

async function startCamera() {
  if (!state.ready || state.starting) return;
  showError('');
  const secure = window.isSecureContext === true;
  const devices = navigator.mediaDevices;
  const hasApi = Boolean(devices) && typeof devices.getUserMedia === 'function';
  if (!secure || !hasApi) {
    showError(describeCameraError(null, { secure, hasApi }).message);
    return;
  }
  const token = ++state.token;
  state.starting = true;
  renderSourceButtons();
  setStatus('카메라를 여는 중입니다. 권한 요청이 나오면 허용해 주세요.');
  let stream = null;
  try {
    stream = await openCamera(devices);
    if (token !== state.token) {
      stopStream(stream);
      return;
    }
    const video = els.video;
    video.hidden = false;
    video.srcObject = stream;
    await video.play();
    if (!(video.videoWidth > 0)) await whenSized(video);
    if (token !== state.token) {
      stopStream(stream);
      return;
    }
    watchTrack(stream);
    setSource('camera', stream);
  } catch (error) {
    stopStream(stream);
    if (token === state.token) {
      setSource('none');
      showError(describeCameraError(error, { secure, hasApi }).message);
    }
  } finally {
    if (token === state.token) {
      state.starting = false;
      setStatus('');
      renderSourceButtons();
    }
  }
}

function startSim() {
  if (!state.ready) return;
  cancelPending();
  showError('');
  state.sim.t = 0;
  setSource('sim');
}

function stopSource() {
  cancelPending();
  setSource('none');
}

function setSimTarget(targetId) {
  state.sim.targetId = targetId ? String(targetId) : null;
  els.simTarget.value = state.sim.targetId || '';
}

/* Events ------------------------------------------------------------------------------------------------------ */

function settle(outcome) {
  if (outcome && outcome.ok) clearRefusal();
  else showRefusal(describeRefusal(outcome ? outcome.reason : null));
  refresh();
}

els.startCamera.addEventListener('click', startCamera);
els.startSim.addEventListener('click', startSim);
els.stopSource.addEventListener('click', stopSource);
els.simTarget.addEventListener('change', () => setSimTarget(els.simTarget.value));

// Confirmations use what was last drawn for the user; the session still checks generation and freshness.
els.confirmProduct.addEventListener('click', () => {
  const view = state.shownView;
  if (!session || !view || !view.candidate) {
    settle({ ok: false, reason: 'no-candidate' });
    return;
  }
  settle(session.confirmProduct({ source: 'camera', scenarioId: view.candidate.id }, performance.now()));
});

els.manual.addEventListener('click', () => {
  if (!session) return;
  settle(session.confirmProduct({ source: 'manual', scenarioId: els.manualProduct.value }, performance.now()));
});

els.start.addEventListener('click', () => {
  if (session) settle(session.startGuidance());
});

els.step.addEventListener('click', () => {
  const view = state.shownView, shape = state.shownShape;
  if (!session || !view || !view.stepId) {
    settle({ ok: false, reason: 'wrong-step' });
    return;
  }
  if (!shape || shape.kind !== 'guidance' || !shape.confirmable) {
    settle({ ok: false, reason: refusalForTap(view, shape) });
    return;
  }
  settle(session.confirmStep({ stepId: view.stepId, generation: view.generation }, performance.now()));
});

els.restart.addEventListener('click', () => {
  if (!session) return;
  session.restart();
  clearRefusal();
  refresh();
});

els.video.addEventListener('resize', () => {
  syncAspect();
  sizeOverlay();
  tracker.reset();
});

document.addEventListener('visibilitychange', () => {
  if (!session) return;
  if (document.hidden) {
    session.pause();
    stopLoop();
  } else {
    session.resume();
    tracker.reset();
    state.lastTrackedAt = -Infinity;
    state.sourceStartedAt = performance.now();
    startLoop();
  }
  refresh();
});

window.addEventListener('pagehide', () => {
  cancelPending();
  stopLoop();
  stopStream(state.stream);
  state.stream = null;
});

if (typeof ResizeObserver === 'function') new ResizeObserver(sizeOverlay).observe(els.stage);
else window.addEventListener('resize', sizeOverlay);

setInterval(refresh, UI_TICK_MS);

/* Test hook: one synchronous cycle and a plain-data snapshot, so tests do not depend on animation timers. */

function snapshot() {
  const result = state.result;
  return JSON.parse(JSON.stringify({
    source: state.source,
    ready: state.ready,
    edge: budget.edge,
    frame: state.frame,
    view: state.shownView,
    shape: state.shownShape,
    ui: state.ui,
    result: result && {
      status: result.status, targetId: result.targetId, inliers: result.inliers, fraction: result.fraction,
      mode: result.mode, keypoints: result.keypoints, quad: result.quad,
    },
  }));
}

window.arDemo = {
  get session() { return session; },
  tracker,
  budget,
  snapshot,
  setSimTarget,
  stepOnce(dt = 1 / 15) {
    step(dt);
    return snapshot();
  },
};

sizeOverlay();
renderSourceButtons();
refresh();
prepare();
