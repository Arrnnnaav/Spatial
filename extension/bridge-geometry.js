/* Convert a desktop mark in physical monitor pixels to Chrome viewport CSS pixels, and back. */
(function (root) {
  function map(region, monitor, rect, view) {
    const dpr = Number(view.dpr);
    if (!Number.isFinite(dpr) || dpr <= 0 || !Array.isArray(rect) || rect.length !== 4) return null;
    const insetX = Math.max(0, (view.outerWidth - view.innerWidth) / 2);
    const insetY = Math.max(0, view.outerHeight - view.innerHeight - insetX);
    const x = (monitor.x + region.x - rect[0]) / dpr - insetX;
    const y = (monitor.y + region.y - rect[1]) / dpr - insetY;
    const width = region.width / dpr, height = region.height / dpr;
    const cx = x + width / 2, cy = y + height / 2;
    if (![x, y, width, height, cx, cy].every(Number.isFinite) ||
        cx < 0 || cy < 0 || cx > view.innerWidth || cy > view.innerHeight) return null;
    const left = Math.max(0, x), top = Math.max(0, y);
    const mark = { x: left, y: top, width: Math.min(view.innerWidth, x + width) - left,
                   height: Math.min(view.innerHeight, y + height) - top };
    return {
      mark,
      toMonitor(box) {
        return { x: rect[0] - monitor.x + (insetX + box.x) * dpr,
                 y: rect[1] - monitor.y + (insetY + box.y) * dpr,
                 width: box.width * dpr, height: box.height * dpr };
      },
    };
  }
  function matchingTabs(title, tabs) {
    const name = String(title || '').toLowerCase();
    return tabs.filter((tab) => tab.id != null && tab.title && name.includes(tab.title.toLowerCase()));
  }
  function uniqueTab(title, tabs) {
    const matches = matchingTabs(title, tabs);
    return matches.length === 1 ? matches[0] : null;
  }
  function sameTab(bound, tab) {
    return Boolean(tab && bound && tab.id === bound.tabId && tab.windowId === bound.windowId &&
      tab.url === bound.url && tab.title === bound.title);
  }
  function sameWindow(rect, browserWindow, dpr) {
    if (!browserWindow?.focused || browserWindow.incognito || !Array.isArray(rect) || rect.length !== 4) return false;
    const actual = [browserWindow.left, browserWindow.top,
      browserWindow.left + browserWindow.width, browserWindow.top + browserWindow.height];
    return [1, dpr].some((scale) => Number.isFinite(scale) && scale > 0 &&
      actual.every((value, index) => Number.isFinite(value) && Math.abs(value * scale - rect[index]) <= 12));
  }
  root.SpatialBridgeGeometry = { map, matchingTabs, uniqueTab, sameTab, sameWindow };
  if (typeof module !== 'undefined') module.exports = { map, matchingTabs, uniqueTab, sameTab, sameWindow };
})(typeof window !== 'undefined' ? window : globalThis);
