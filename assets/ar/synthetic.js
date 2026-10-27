// Synthetic camera frames for the in-page simulation and the Node tests. A registered target is drawn under a
// known homography over a cluttered background, then degraded like a camera would (blur, gain, noise).
// Pure typed-array code with no DOM access.
import { mulberry32 } from './features.js';
import { blur7, resizeGray } from './image.js';
import { invert3x3, multiply3x3, projectRect } from './geometry.js';

function gaussianSource(rng) {
  return () => Math.sqrt(-2 * Math.log(Math.max(rng(), 1e-12))) * Math.cos(2 * Math.PI * rng());
}

function addValueNoise(accumulator, width, height, rng, scale, weight) {
  const cols = Math.ceil(width / scale) + 2, rows = Math.ceil(height / scale) + 2;
  const grid = new Float32Array(cols * rows);
  for (let i = 0; i < grid.length; i++) grid[i] = rng();
  for (let y = 0; y < height; y++) {
    const gy = y / scale, y0 = Math.floor(gy), fy = gy - y0;
    for (let x = 0; x < width; x++) {
      const gx = x / scale, x0 = Math.floor(gx), fx = gx - x0;
      const a = grid[y0 * cols + x0], b = grid[y0 * cols + x0 + 1];
      const c = grid[(y0 + 1) * cols + x0], d = grid[(y0 + 1) * cols + x0 + 1];
      accumulator[y * width + x] += weight * ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy);
    }
  }
}

function fillRect(gray, width, height, x0, y0, w, h, value) {
  const xa = Math.max(0, Math.round(x0)), xb = Math.min(width, Math.round(x0 + w));
  const ya = Math.max(0, Math.round(y0)), yb = Math.min(height, Math.round(y0 + h));
  for (let y = ya; y < yb; y++) gray.fill(value, y * width + xa, y * width + xb);
}

/** Seeded room-like clutter: soft gradients, paper-like rectangles, text-like dashes, discs and thin lines. */
export function clutterGray(width, height, seed, { rectangles = 60, lines = 12, discs = 25, textRows = 8 } = {}) {
  const rng = mulberry32(seed);
  const accumulator = new Float32Array(width * height);
  addValueNoise(accumulator, width, height, rng, 96, 1);
  addValueNoise(accumulator, width, height, rng, 40, 0.6);
  const gray = new Uint8Array(width * height);
  for (let i = 0; i < gray.length; i++) gray[i] = Math.max(0, Math.min(255, 70 + (accumulator[i] / 1.6) * 120));
  const short = Math.min(width, height);
  for (let i = 0; i < rectangles; i++) {
    const w = 0.04 * short + rng() * 0.32 * short, h = 0.03 * short + rng() * 0.22 * short;
    fillRect(gray, width, height, rng() * width - w / 2, rng() * height - h / 2, w, h, 20 + Math.floor(rng() * 215));
  }
  for (let i = 0; i < discs; i++) {
    const cx = rng() * width, cy = rng() * height, r = 0.012 * short + rng() * 0.07 * short;
    const value = 20 + Math.floor(rng() * 215);
    for (let y = Math.max(0, Math.floor(cy - r)); y < Math.min(height, Math.ceil(cy + r)); y++) {
      for (let x = Math.max(0, Math.floor(cx - r)); x < Math.min(width, Math.ceil(cx + r)); x++) {
        if ((x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r) gray[y * width + x] = value;
      }
    }
  }
  for (let i = 0; i < lines; i++) {
    const x0 = rng() * width, y0 = rng() * height, angle = rng() * Math.PI, length = 0.15 * short + rng() * 0.6 * short;
    const thickness = 1 + Math.floor(rng() * 3), value = 15 + Math.floor(rng() * 225);
    for (let s = 0; s < length; s += 0.5) {
      fillRect(gray, width, height, x0 + Math.cos(angle) * s, y0 + Math.sin(angle) * s, thickness, thickness, value);
    }
  }
  for (let row = 0; row < textRows; row++) {
    let x = rng() * width * 0.5;
    const y = rng() * height, size = 0.012 * short + rng() * 0.012 * short, value = 25 + Math.floor(rng() * 80);
    while (x < width) {
      const glyph = size * (0.5 + rng());
      fillRect(gray, width, height, x, y, glyph, size * 1.6, value);
      x += glyph + size * (0.3 + rng() * 0.9);
    }
  }
  return gray;
}

/**
 * Homography from reference pixels to frame pixels for a plane seen by a pinhole camera.
 * `scale` is frame pixels per reference pixel at the target centre; `rotDeg` is the in-plane roll and the
 * tilt angles turn the plane away from the camera. (cx, cy) is where the target centre appears in the frame.
 */
export function poseHomography({
  refWidth, refHeight, frameWidth, frameHeight, scale = 0.5, rotDeg = 0, tiltXDeg = 0, tiltYDeg = 0,
  cx = frameWidth / 2, cy = frameHeight / 2, focal = 0.85 * Math.max(frameWidth, frameHeight),
}) {
  const rad = Math.PI / 180;
  const [cz, sz] = [Math.cos(rotDeg * rad), Math.sin(rotDeg * rad)];
  const [cxr, sxr] = [Math.cos(tiltXDeg * rad), Math.sin(tiltXDeg * rad)];
  const [cyr, syr] = [Math.cos(tiltYDeg * rad), Math.sin(tiltYDeg * rad)];
  const Rz = new Float64Array([cz, -sz, 0, sz, cz, 0, 0, 0, 1]);
  const Rx = new Float64Array([1, 0, 0, 0, cxr, -sxr, 0, sxr, cxr]);
  const Ry = new Float64Array([cyr, 0, syr, 0, 1, 0, -syr, 0, cyr]);
  const R = multiply3x3(Rz, multiply3x3(Rx, Ry));
  const z = focal / scale;
  const tx = ((cx - frameWidth / 2) * z) / focal, ty = ((cy - frameHeight / 2) * z) / focal;
  const pose = new Float64Array([R[0], R[1], tx, R[3], R[4], ty, R[6], R[7], z]);
  const K = new Float64Array([focal, 0, frameWidth / 2, 0, focal, frameHeight / 2, 0, 0, 1]);
  const center = new Float64Array([1, 0, -refWidth / 2, 0, 1, -refHeight / 2, 0, 0, 1]);
  return multiply3x3(K, multiply3x3(pose, center));
}

/** Mip chain with area-averaged levels at 1, 1/2, 1/4, ... for alias-free minification. */
export function buildMips(gray, width, height, levels = 5) {
  const mips = [{ gray, width, height }];
  for (let level = 1; level < levels; level++) {
    const w = Math.max(8, Math.round(width / 2 ** level)), h = Math.max(8, Math.round(height / 2 ** level));
    if (w >= mips[level - 1].width && h >= mips[level - 1].height) break;
    mips.push({ gray: resizeGray(gray, width, height, w, h), width: w, height: h });
  }
  return mips;
}

function sampleBilinear(mip, x, y) {
  const { gray, width, height } = mip;
  const xc = Math.min(Math.max(x, 0), width - 1), yc = Math.min(Math.max(y, 0), height - 1);
  const x0 = Math.floor(xc), y0 = Math.floor(yc);
  const x1 = Math.min(x0 + 1, width - 1), y1 = Math.min(y0 + 1, height - 1);
  const fx = xc - x0, fy = yc - y0;
  const top = gray[y0 * width + x0] * (1 - fx) + gray[y0 * width + x1] * fx;
  const bottom = gray[y1 * width + x0] * (1 - fx) + gray[y1 * width + x1] * fx;
  return top * (1 - fy) + bottom * fy;
}

/**
 * Draw `layers` (each `{ mips, refWidth, refHeight, H }`) over `background`, then apply camera effects.
 * Returns the grayscale frame. Everything is seeded, so a frame is reproducible from its parameters.
 */
export function renderScene({
  width, height, background, layers, blurPasses = 0, gain = 1, bias = 0, noise = 0, seed = 1,
}) {
  let frame = Uint8Array.from(background);
  for (const layer of layers) {
    const { mips, refWidth, refHeight, H } = layer;
    const inverse = invert3x3(H);
    const corners = projectRect(H, 0, 0, refWidth, refHeight);
    if (!inverse || !corners) continue;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x, y] of corners) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
    const u0 = Math.max(0, Math.floor(minX)), u1 = Math.min(width - 1, Math.ceil(maxX));
    const v0 = Math.max(0, Math.floor(minY)), v1 = Math.min(height - 1, Math.ceil(maxY));
    const [i0, i1, i2, i3, i4, i5, i6, i7, i8] = inverse;
    const [h0, h1, , h3, h4, , h6, h7] = H;
    for (let v = v0; v <= v1; v++) {
      for (let u = u0; u <= u1; u++) {
        const w = i6 * u + i7 * v + i8;
        if (!(w > 0)) continue;
        const x = (i0 * u + i1 * v + i2) / w, y = (i3 * u + i4 * v + i5) / w;
        if (x < 0 || y < 0 || x > refWidth - 1 || y > refHeight - 1) continue;
        // Local frame-pixels-per-reference-pixel from the forward Jacobian picks the mip level.
        const hw = h6 * x + h7 * y + H[8];
        const a = (h0 - u * h6) / hw, b = (h1 - u * h7) / hw, c = (h3 - v * h6) / hw, d = (h4 - v * h7) / hw;
        const local = Math.sqrt(Math.abs(a * d - b * c));
        const level = Math.min(mips.length - 1, Math.max(0, Math.floor(Math.log2(1 / Math.max(local, 1e-6)) + 0.25)));
        const mip = mips[level];
        const sx = ((x + 0.5) * mip.width) / refWidth - 0.5, sy = ((y + 0.5) * mip.height) / refHeight - 0.5;
        frame[v * width + u] = Math.round(sampleBilinear(mip, sx, sy));
      }
    }
  }
  for (let pass = 0; pass < blurPasses; pass++) frame = blur7(frame, width, height);
  if (gain !== 1 || bias !== 0 || noise > 0) {
    const gaussian = gaussianSource(mulberry32(seed));
    for (let i = 0; i < frame.length; i++) {
      const value = gain * frame[i] + bias + (noise > 0 ? noise * gaussian() : 0);
      frame[i] = value < 0 ? 0 : value > 255 ? 255 : Math.round(value);
    }
  }
  return frame;
}

/** A smooth, repeatable hand-held-like camera path used by the in-page simulation and the tests. */
export function simulatedPose(t, { refWidth, refHeight, frameWidth, frameHeight, scale = 0.55 }) {
  return poseHomography({
    refWidth, refHeight, frameWidth, frameHeight,
    scale: scale * (1 + 0.1 * Math.sin(t * 0.5)),
    rotDeg: 10 * Math.sin(t * 0.7),
    tiltXDeg: 16 * Math.sin(t * 0.43),
    tiltYDeg: 18 * Math.sin(t * 0.31 + 1),
    cx: frameWidth * (0.5 + 0.06 * Math.sin(t * 0.37)),
    cy: frameHeight * (0.5 + 0.04 * Math.sin(t * 0.53 + 2)),
  });
}
