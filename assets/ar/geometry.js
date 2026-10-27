// Planar geometry helpers for the image-target tracker. Pure functions, no DOM.
// Homographies are row-major 3x3 matrices stored in a Float64Array(9).

const normalMatrix = new Float64Array(64);
const normalRhs = new Float64Array(8);
const row1 = new Float64Array(8);
const row2 = new Float64Array(8);

/** Solve the 8x8 system a*x=b by Gaussian elimination; the solution is left in b. */
function solve8(a, b) {
  const n = 8;
  for (let col = 0; col < n; col++) {
    let pivot = col;
    let best = Math.abs(a[col * n + col]);
    for (let row = col + 1; row < n; row++) {
      const value = Math.abs(a[row * n + col]);
      if (value > best) { best = value; pivot = row; }
    }
    if (!(best > 1e-12)) return false;
    if (pivot !== col) {
      for (let k = 0; k < n; k++) {
        const t = a[col * n + k]; a[col * n + k] = a[pivot * n + k]; a[pivot * n + k] = t;
      }
      const t = b[col]; b[col] = b[pivot]; b[pivot] = t;
    }
    const inverse = 1 / a[col * n + col];
    for (let row = col + 1; row < n; row++) {
      const factor = a[row * n + col] * inverse;
      if (factor === 0) continue;
      for (let k = col; k < n; k++) a[row * n + k] -= factor * a[col * n + k];
      b[row] -= factor * b[col];
    }
  }
  for (let row = n - 1; row >= 0; row--) {
    let sum = b[row];
    for (let k = row + 1; k < n; k++) sum -= a[row * n + k] * b[k];
    b[row] = sum / a[row * n + row];
  }
  return true;
}

/**
 * Least-squares homography from normalised DLT (h22 fixed to 1 in normalised space).
 * Maps (sx, sy) to (dx, dy). `indices` selects `count` points; null uses the first `count`.
 * Writes the row-major result into `out` and returns false for degenerate input.
 */
export function estimateHomography(sx, sy, dx, dy, indices, count, out) {
  if (count < 4) return false;
  let mxs = 0, mys = 0, mxd = 0, myd = 0;
  for (let n = 0; n < count; n++) {
    const i = indices ? indices[n] : n;
    mxs += sx[i]; mys += sy[i]; mxd += dx[i]; myd += dy[i];
  }
  mxs /= count; mys /= count; mxd /= count; myd /= count;
  let ds = 0, dd = 0;
  for (let n = 0; n < count; n++) {
    const i = indices ? indices[n] : n;
    ds += Math.hypot(sx[i] - mxs, sy[i] - mys);
    dd += Math.hypot(dx[i] - mxd, dy[i] - myd);
  }
  ds /= count; dd /= count;
  if (!(ds > 1e-9) || !(dd > 1e-9)) return false;
  const ss = Math.SQRT2 / ds;
  const sd = Math.SQRT2 / dd;
  normalMatrix.fill(0);
  normalRhs.fill(0);
  for (let n = 0; n < count; n++) {
    const i = indices ? indices[n] : n;
    const x = (sx[i] - mxs) * ss, y = (sy[i] - mys) * ss;
    const u = (dx[i] - mxd) * sd, v = (dy[i] - myd) * sd;
    row1[0] = x; row1[1] = y; row1[2] = 1; row1[3] = 0; row1[4] = 0; row1[5] = 0; row1[6] = -u * x; row1[7] = -u * y;
    row2[0] = 0; row2[1] = 0; row2[2] = 0; row2[3] = x; row2[4] = y; row2[5] = 1; row2[6] = -v * x; row2[7] = -v * y;
    for (let r = 0; r < 8; r++) {
      const a1 = row1[r], a2 = row2[r];
      normalRhs[r] += a1 * u + a2 * v;
      for (let c = 0; c < 8; c++) normalMatrix[r * 8 + c] += a1 * row1[c] + a2 * row2[c];
    }
  }
  if (!solve8(normalMatrix, normalRhs)) return false;
  const h = normalRhs;
  // H = Td^-1 * Hn * Ts where Ts and Td translate to the centroid and scale to mean distance sqrt(2).
  const tx = -ss * mxs, ty = -ss * mys;
  const r00 = h[0] * ss, r01 = h[1] * ss, r02 = h[0] * tx + h[1] * ty + h[2];
  const r10 = h[3] * ss, r11 = h[4] * ss, r12 = h[3] * tx + h[4] * ty + h[5];
  const r20 = h[6] * ss, r21 = h[7] * ss, r22 = h[6] * tx + h[7] * ty + 1;
  const inverseScale = 1 / sd;
  out[0] = inverseScale * r00 + mxd * r20; out[1] = inverseScale * r01 + mxd * r21; out[2] = inverseScale * r02 + mxd * r22;
  out[3] = inverseScale * r10 + myd * r20; out[4] = inverseScale * r11 + myd * r21; out[5] = inverseScale * r12 + myd * r22;
  out[6] = r20; out[7] = r21; out[8] = r22;
  for (let k = 0; k < 9; k++) if (!Number.isFinite(out[k])) return false;
  return true;
}

/** Projective depth term of (x, y); positive when the point is in front of the camera. */
export function depth(H, x, y) {
  return H[6] * x + H[7] * y + H[8];
}

/** Project (x, y) through H into out[offset..offset+1]. Returns false on the plane at infinity. */
export function project(H, x, y, out, offset = 0) {
  const w = H[6] * x + H[7] * y + H[8];
  if (!(Math.abs(w) > 1e-12)) return false;
  out[offset] = (H[0] * x + H[1] * y + H[2]) / w;
  out[offset + 1] = (H[3] * x + H[4] * y + H[5]) / w;
  return true;
}

export function invert3x3(M) {
  const a = M[0], b = M[1], c = M[2], d = M[3], e = M[4], f = M[5], g = M[6], h = M[7], i = M[8];
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (!(Math.abs(det) > 1e-18)) return null;
  const s = 1 / det;
  return new Float64Array([
    A * s, -(b * i - c * h) * s, (b * f - c * e) * s,
    B * s, (a * i - c * g) * s, -(a * f - c * d) * s,
    C * s, -(a * h - b * g) * s, (a * e - b * d) * s,
  ]);
}

export function multiply3x3(A, B) {
  const out = new Float64Array(9);
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      out[r * 3 + c] = A[r * 3] * B[c] + A[r * 3 + 1] * B[3 + c] + A[r * 3 + 2] * B[6 + c];
    }
  }
  return out;
}

/** Corners of rect [left, top, right, bottom] mapped through H as [[x, y] x4], or null behind the camera. */
export function projectRect(H, left, top, right, bottom) {
  const result = [];
  const scratch = [0, 0];
  for (const [x, y] of [[left, top], [right, top], [right, bottom], [left, bottom]]) {
    if (!(depth(H, x, y) > 0) || !project(H, x, y, scratch)) return null;
    result.push([scratch[0], scratch[1]]);
  }
  return result;
}

export function polygonArea(points) {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % points.length];
    sum += x1 * y2 - x2 * y1;
  }
  return sum / 2;
}

/** True when every turn has the orientation of a top-left, top-right, bottom-right, bottom-left walk (y down). */
export function isConvexClockwise(points) {
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % n];
    const [x2, y2] = points[(i + 2) % n];
    if ((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1) <= 0) return false;
  }
  return true;
}

export function pointInPolygon(point, polygon) {
  let inside = false;
  const px = point[0], py = point[1];
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i][0], yi = polygon[i][1], xj = polygon[j][0], yj = polygon[j][1];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function centroid(points) {
  let x = 0, y = 0;
  for (const p of points) { x += p[0]; y += p[1]; }
  return [x / points.length, y / points.length];
}

export function distance(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}
