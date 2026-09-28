import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import geometry from '../geometry.js';
import bridge from '../bridge-geometry.js';

test('desktop DOM collection skips password fields', () => {
  const mark = { x: 100, y: 100, width: 100, height: 30 };
  const input = (type, value) => ({
    tagName: 'INPUT', value, placeholder: '',
    matches: (selector) => selector === 'input,textarea,select',
    getAttribute: (name) => name === 'type' ? type : '',
    getBoundingClientRect: () => ({ left: 100, top: 100, width: 100, height: 30 }),
    closest: () => null,
  });
  const elements = [input('password', 'secret-123'), input('text', 'Visible label')];
  let listener;
  const window = { SpatialGeometry: geometry, SpatialBridgeGeometry: bridge,
    innerWidth: 1000, innerHeight: 700, outerWidth: 1000, outerHeight: 700,
    devicePixelRatio: 1, getSelection: () => null };
  const document = { body: {}, documentElement: {}, elementsFromPoint: () => elements };
  const chrome = { runtime: { onMessage: { addListener: (fn) => { listener = fn; } } } };
  vm.runInNewContext(readFileSync(new URL('../content.js', import.meta.url), 'utf8'),
    { window, document, chrome });
  let result;
  listener({ type: 'spatial:bridge-collect', region: mark,
    monitor: { x: 0, y: 0 }, window: { rect: [0, 0, 1000, 700] } }, null,
  (response) => { result = response; });
  assert.deepEqual(Array.from(result.candidates, (candidate) => candidate.text), ['Visible label']);
});
