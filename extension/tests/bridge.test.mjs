import test from 'node:test';
import assert from 'node:assert/strict';
import bridge from '../bridge-geometry.js';

test('desktop physical mark maps to Chrome viewport and candidate maps back', () => {
  const monitor = { x: -1920, y: 0, width: 1920, height: 1080 };
  const rect = [-1800, 50, -200, 950];
  const view = { dpr: 2, outerWidth: 800, innerWidth: 784, outerHeight: 450, innerHeight: 350 };
  const region = { x: 320, y: 350, width: 120, height: 40 };
  const mapped = bridge.map(region, monitor, rect, view);
  assert.deepEqual(mapped.mark, { x: 92, y: 58, width: 60, height: 20 });
  assert.deepEqual(mapped.toMonitor(mapped.mark), region);
});

test('mark in browser chrome abstains', () => {
  const monitor = { x: 0, y: 0, width: 1920, height: 1080 };
  const view = { dpr: 1, outerWidth: 1000, innerWidth: 984, outerHeight: 800, innerHeight: 700 };
  assert.equal(bridge.map({ x: 200, y: 110, width: 20, height: 10 }, monitor,
    [100, 100, 1100, 900], view), null);
});

test('tab binding abstains on duplicate titles or a tab switch', () => {
  const first = { id: 1, windowId: 10, title: 'Notes', url: 'https://a.example/' };
  const second = { id: 2, windowId: 11, title: 'Notes', url: 'https://b.example/' };
  assert.equal(bridge.uniqueTab('Notes - Google Chrome', [first, second]), null);
  assert.deepEqual(bridge.matchingTabs('Notes - Google Chrome', [first, second]), [first, second]);
  assert.equal(bridge.uniqueTab('Notes - Google Chrome', [first]), first);
  const bound = { tabId: first.id, windowId: first.windowId, title: first.title, url: first.url };
  assert.equal(bridge.sameTab(bound, first), true);
  assert.equal(bridge.sameTab(bound, { ...first, id: 3 }), false);
  assert.equal(bridge.sameTab(bound, { ...first, url: 'https://b.example/' }), false);
});

test('native Chrome window must be the focused window at matching bounds', () => {
  const browserWindow = { left: 100, top: 50, width: 800, height: 600, focused: true, incognito: false };
  assert.equal(bridge.sameWindow([100, 50, 900, 650], browserWindow, 1), true);
  assert.equal(bridge.sameWindow([200, 100, 1800, 1300], browserWindow, 2), true);
  assert.equal(bridge.sameWindow([100, 50, 900, 650], { ...browserWindow, focused: false }, 1), false);
  assert.equal(bridge.sameWindow([100, 50, 900, 650], { ...browserWindow, incognito: true }, 1), false);
  assert.equal(bridge.sameWindow([150, 50, 950, 650], browserWindow, 1), false);
});
