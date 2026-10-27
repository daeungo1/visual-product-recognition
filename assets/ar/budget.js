/**
 * Analysis size of the camera AR demo. Pure: no DOM, camera or timers.
 *
 * The tracker only receives frames shrunk to the current long edge. A slow device trades operating range
 * (the target has to fill more of the frame) for frame rate; a frame is never enlarged.
 */

export const LONG_EDGES = Object.freeze([512, 416, 336]);

export const BUDGET_DEFAULTS = Object.freeze({
  edges: LONG_EDGES,
  window: 8,
  slowMs: 160,
  fastMs: 60,
  upAfter: 90,
});

export class FrameBudget {
  constructor(options = {}) {
    this.options = { ...BUDGET_DEFAULTS, ...options };
    const { edges } = this.options;
    const valid = Array.isArray(edges) && edges.length > 0
      && edges.every((edge, i) => Number.isFinite(edge) && edge > 0 && (i === 0 || edge < edges[i - 1]));
    if (!valid) throw new TypeError('edges must be positive and strictly decreasing');
    this.index = 0;
    this.samples = [];
    this.fastRun = 0;
  }

  get edge() {
    return this.options.edges[this.index];
  }

  /** Size of the analysed frame for a video of the given size, or null when the video has no size yet. */
  fit(videoWidth, videoHeight) {
    if (!(videoWidth > 0) || !(videoHeight > 0)) return null;
    const scale = Math.min(1, this.edge / Math.max(videoWidth, videoHeight));
    return { width: Math.max(1, Math.round(videoWidth * scale)), height: Math.max(1, Math.round(videoHeight * scale)) };
  }

  /** One processing time in milliseconds. `changed` tells that the size changed and the tracker has to restart. */
  record(ms) {
    if (!Number.isFinite(ms) || ms < 0) return { changed: false, edge: this.edge };
    const { window, slowMs, fastMs, upAfter, edges } = this.options;
    this.samples.push(ms);
    if (this.samples.length > window) this.samples.shift();
    if (this.samples.length < window) return { changed: false, edge: this.edge };
    const mean = this.samples.reduce((sum, value) => sum + value, 0) / window;
    if (mean > slowMs && this.index < edges.length - 1) return this.move(1);
    if (mean < fastMs && this.index > 0) {
      // Cost grows with the pixel count: only go back up when the larger size is still expected to be fast.
      const predicted = mean * (edges[this.index - 1] / this.edge) ** 2;
      this.fastRun = predicted < slowMs * 0.8 ? this.fastRun + 1 : 0;
      if (this.fastRun >= upAfter) return this.move(-1);
    } else {
      this.fastRun = 0;
    }
    return { changed: false, edge: this.edge };
  }

  move(step) {
    this.index += step;
    this.samples = [];
    this.fastRun = 0;
    return { changed: true, edge: this.edge };
  }
}
