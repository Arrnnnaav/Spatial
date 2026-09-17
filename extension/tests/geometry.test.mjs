import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const geometry = createRequire(import.meta.url)('../geometry.js');

test('closed freehand stroke becomes a polygon mark with its bbox', () => {
  const points = [];
  for (let i = 0; i <= 40; i++) points.push([100 + 50 * Math.cos((i / 40) * Math.PI * 2), 100 + 30 * Math.sin((i / 40) * Math.PI * 2)]);
  const mark = geometry.strokeToMark(points);
  assert.equal(mark.type, 'polygon');
  assert.equal(mark.closed, true);
  assert.equal(mark.role, 'reference');
  assert.equal(mark.x, 50); assert.equal(mark.y, 70); assert.equal(mark.width, 100); assert.equal(mark.height, 60);
});

test('open stroke is padded so the pointed-at thing is included', () => {
  const mark = geometry.strokeToMark([[10, 10], [40, 12], [80, 11], [120, 10], [160, 12], [200, 10], [240, 11], [280, 10], [320, 12]]);
  assert.equal(mark.closed, false);
  assert.ok(mark.x < 10 && mark.y < 10);
  assert.ok(mark.width > 310);
});

test('simplify drops near-duplicate points but keeps endpoints', () => {
  const points = [[0, 0], [0.5, 0.5], [1, 1], [10, 10], [10.2, 10.1], [30, 30]];
  const simplified = geometry.simplify(points, 2);
  assert.deepEqual(simplified[0], [0, 0]);
  assert.deepEqual(simplified[simplified.length - 1], [30, 30]);
  assert.ok(simplified.length < points.length);
});

test('anchorFilter rejects page-sized containers and accepts overlapping leaf elements', () => {
  const viewport = { width: 1280, height: 720 };
  const mark = { x: 100, y: 100, width: 200, height: 100 };
  assert.equal(geometry.anchorFilter({ x: 0, y: 0, width: 1280, height: 5000 }, mark, viewport), false);
  assert.equal(geometry.anchorFilter({ x: 90, y: 90, width: 220, height: 120 }, mark, viewport), true);
  assert.equal(geometry.anchorFilter({ x: 600, y: 600, width: 50, height: 50 }, mark, viewport), false);
});

test('rankAnchors prefers the element that covers the mark most, smaller on ties', () => {
  const mark = { x: 100, y: 100, width: 200, height: 100 };
  const ranked = geometry.rankAnchors([
    { id: 'wide', bbox: { x: 0, y: 90, width: 1000, height: 120 } },
    { id: 'tight', bbox: { x: 95, y: 95, width: 210, height: 110 } },
    { id: 'far', bbox: { x: 900, y: 900, width: 10, height: 10 } },
  ], mark);
  assert.equal(ranked[0].id, 'tight');
  assert.equal(ranked.some(a => a.id === 'far'), false);
});

test('shapeToMark normalises drag direction', () => {
  const mark = geometry.shapeToMark('circle', [200, 150], [50, 40]);
  assert.deepEqual([mark.type, mark.x, mark.y, mark.width, mark.height], ['circle', 50, 40, 150, 110]);
});
