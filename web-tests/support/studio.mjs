import { projectRect } from '../../assets/ar/geometry.js';
import { buildMips, poseHomography, renderScene } from '../../assets/ar/synthetic.js';
import { ImageTargetTracker } from '../../assets/ar/tracker.js';

export function createTracker(targets, options) {
  const tracker = new ImageTargetTracker(options);
  for (const target of targets) tracker.addTarget(target.id, target.gray, target.width, target.height);
  return tracker;
}

/** Renders registered targets into synthetic camera frames and measures how far a reported pose is from the truth. */
export class Studio {
  constructor(targets, { width = 288, height = 512 } = {}) {
    this.targets = targets;
    this.width = width;
    this.height = height;
    this.mips = new Map(targets.map((t) => [t.id, buildMips(t.gray, t.width, t.height, 5)]));
  }

  homography(target, pose = {}) {
    return poseHomography({
      refWidth: target.width, refHeight: target.height, frameWidth: this.width, frameHeight: this.height, ...pose,
    });
  }

  layer(target, H) {
    return { mips: this.mips.get(target.id), refWidth: target.width, refHeight: target.height, H };
  }

  /** Frame with `target` placed by an explicit homography; `effects` are renderScene camera effects. */
  renderWith(target, H, { background, ...effects }) {
    return renderScene({
      width: this.width, height: this.height, background, layers: [this.layer(target, H)], ...effects,
    });
  }

  /** `{ gray, H }` for one target seen at `pose` over `background`. */
  frame(target, pose, options) {
    const H = this.homography(target, pose);
    return { gray: this.renderWith(target, H, options), H };
  }

  /** Mean distance in frame pixels between the four reported reference corners and their true projection. */
  cornerError(H, target, quad) {
    const truth = projectRect(H, 0, 0, target.width, target.height);
    return truth.reduce((sum, p, i) => sum + Math.hypot(p[0] - quad[i][0], p[1] - quad[i][1]), 0) / 4;
  }
}

export function median(values) {
  if (!values.length) return NaN;
  const sorted = values.slice().sort((a, b) => a - b);
  return sorted[sorted.length >> 1];
}
