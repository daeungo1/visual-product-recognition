import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { rgbaToGray } from '../../assets/ar/image.js';
import { decodePng } from './png.mjs';

const ASSETS = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'assets');

export function loadCatalog() {
  return JSON.parse(readFileSync(join(ASSETS, 'scenarios', 'catalog.json'), 'utf8'));
}

export function loadGrayPng(relativePath) {
  const png = decodePng(readFileSync(join(ASSETS, relativePath)));
  return { gray: rgbaToGray(png.rgba, png.width, png.height), width: png.width, height: png.height, rgba: png.rgba };
}

/** Every registered scenario target as `{ id, scenario, gray, width, height }`. */
export function loadScenarioTargets() {
  const catalog = loadCatalog();
  const scenarios = catalog.scenarios || catalog;
  return scenarios.map((scenario) => ({ id: scenario.target_id, scenario, ...loadGrayPng(scenario.image) }));
}
