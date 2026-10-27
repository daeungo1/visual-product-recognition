// Grayscale image helpers. Everything works on Uint8Array buffers; no DOM or canvas access.

/** `out` may be a larger reusable buffer; the result always has exactly width * height bytes. */
export function rgbaToGray(rgba, width, height, out) {
  const n = width * height;
  const gray = out && out.length >= n ? out.subarray(0, n) : new Uint8Array(n);
  for (let i = 0, p = 0; i < n; i++, p += 4) {
    gray[i] = (rgba[p] * 77 + rgba[p + 1] * 150 + rgba[p + 2] * 29) >> 8;
  }
  return gray;
}

function areaWeights(sourceLength, targetLength) {
  const scale = sourceLength / targetLength;
  const firsts = new Int32Array(targetLength);
  const starts = new Int32Array(targetLength);
  const lengths = new Int32Array(targetLength);
  const weights = [];
  for (let j = 0; j < targetLength; j++) {
    const a = j * scale, b = (j + 1) * scale;
    const first = Math.floor(a), last = Math.min(sourceLength, Math.ceil(b));
    const base = weights.length;
    firsts[j] = first;
    starts[j] = base;
    lengths[j] = last - first;
    let sum = 0;
    for (let i = first; i < last; i++) {
      const w = Math.min(b, i + 1) - Math.max(a, i);
      weights.push(w);
      sum += w;
    }
    for (let k = base; k < weights.length; k++) weights[k] /= sum;
  }
  return { firsts, starts, lengths, weights: Float32Array.from(weights) };
}

/** Area-averaging downscale. Only shrinking (or same size) is supported. */
export function resizeGray(source, sourceWidth, sourceHeight, targetWidth, targetHeight) {
  if (targetWidth > sourceWidth || targetHeight > sourceHeight) {
    throw new RangeError('resizeGray only shrinks images');
  }
  if (targetWidth === sourceWidth && targetHeight === sourceHeight) return Uint8Array.from(source);
  const horizontal = areaWeights(sourceWidth, targetWidth);
  const vertical = areaWeights(sourceHeight, targetHeight);
  const temporary = new Float32Array(targetWidth * sourceHeight);
  for (let y = 0; y < sourceHeight; y++) {
    const rowOffset = y * sourceWidth;
    for (let x = 0; x < targetWidth; x++) {
      const first = horizontal.firsts[x];
      const start = horizontal.starts[x], length = horizontal.lengths[x];
      let sum = 0;
      for (let k = 0; k < length; k++) sum += source[rowOffset + first + k] * horizontal.weights[start + k];
      temporary[y * targetWidth + x] = sum;
    }
  }
  const target = new Uint8Array(targetWidth * targetHeight);
  for (let y = 0; y < targetHeight; y++) {
    const first = vertical.firsts[y];
    const start = vertical.starts[y], length = vertical.lengths[y];
    for (let x = 0; x < targetWidth; x++) {
      let sum = 0;
      for (let k = 0; k < length; k++) sum += temporary[(first + k) * targetWidth + x] * vertical.weights[start + k];
      target[y * targetWidth + x] = Math.round(sum);
    }
  }
  return target;
}

const KERNEL = [1, 6, 15, 20, 15, 6, 1]; // binomial, sums to 64, sigma about 1.2 px

/** Separable 7-tap binomial blur with clamped borders. `scratch` must hold width*height Uint16 values. */
export function blur7(source, width, height, target, scratch) {
  const out = target || new Uint8Array(width * height);
  const tmp = scratch || new Uint16Array(width * height);
  const last = width - 1;
  for (let y = 0; y < height; y++) {
    const row = y * width;
    for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let k = -3; k <= 3; k++) {
        let xx = x + k;
        if (xx < 0) xx = 0; else if (xx > last) xx = last;
        sum += KERNEL[k + 3] * source[row + xx];
      }
      tmp[row + x] = sum;
    }
  }
  const lastRow = height - 1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let k = -3; k <= 3; k++) {
        let yy = y + k;
        if (yy < 0) yy = 0; else if (yy > lastRow) yy = lastRow;
        sum += KERNEL[k + 3] * tmp[yy * width + x];
      }
      out[y * width + x] = (sum + 2048) >> 12;
    }
  }
  return out;
}

/** 2nd and 98th percentile of the intensities, used to adapt the corner threshold to the lighting. */
export function intensityRange(gray, step = 4) {
  const histogram = new Uint32Array(256);
  let total = 0;
  for (let i = 0; i < gray.length; i += step) { histogram[gray[i]]++; total++; }
  const lowTarget = total * 0.02, highTarget = total * 0.98;
  let acc = 0, low = 0, high = 255;
  for (let v = 0; v < 256; v++) {
    acc += histogram[v];
    if (acc >= lowTarget) { low = v; break; }
  }
  acc = 0;
  for (let v = 0; v < 256; v++) {
    acc += histogram[v];
    if (acc >= highTarget) { high = v; break; }
  }
  return { low, high };
}
