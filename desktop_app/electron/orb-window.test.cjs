'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const {
  ORB_SIZE,
  clampOrbPosition,
  collapseOrbWindow,
  hideOrbForExpansion,
  initialOrbBounds,
  registerOrbDragHandlers,
} = require('./orb-window.cjs');

function createOrbWindow(bounds) {
  const events = new EventEmitter();
  return {
    bounds: { ...bounds },
    destroyed: false,
    webContents: {},
    isDestroyed() { return this.destroyed; },
    getBounds() { return { ...this.bounds }; },
    setPosition(x, y) { this.bounds = { ...this.bounds, x, y }; },
    hide() { this.visible = false; },
    showInactive() { this.visible = true; },
    once: events.once.bind(events),
    emit: events.emit.bind(events),
  };
}

function dragHarness({ bounds, workArea }) {
  const ipcMain = new EventEmitter();
  let pointer = { x: 100, y: 100 };
  const window = createOrbWindow(bounds);
  const screen = {
    getCursorScreenPoint: () => pointer,
    getDisplayNearestPoint: () => ({ workArea }),
  };
  const handlers = registerOrbDragHandlers({ ipcMain, screen, getOrbWindow: () => window });
  const event = { sender: window.webContents };
  return {
    handlers,
    ipcMain,
    moveCursor(point) {
      pointer = point;
      ipcMain.emit('ruby:orb:drag-move', event);
    },
    start() { ipcMain.emit('ruby:orb:drag-start', event); },
    end() { ipcMain.emit('ruby:orb:drag-end', event); },
    window,
  };
}

test('new orb starts at the bottom-right inside its display work area', () => {
  assert.deepEqual(initialOrbBounds({ x: 0, y: 0, width: 1920, height: 1080 }), {
    x: 1792, y: 952, width: ORB_SIZE, height: ORB_SIZE,
  });
  assert.deepEqual(initialOrbBounds({ x: -1280, y: 0, width: 1280, height: 720 }), {
    x: -128, y: 592, width: ORB_SIZE, height: ORB_SIZE,
  });
});

test('drag maps native screen coordinates to window coordinates and clamps to work area', () => {
  const harness = dragHarness({
    bounds: { x: 500, y: 400, width: ORB_SIZE, height: ORB_SIZE },
    workArea: { x: 0, y: 0, width: 1920, height: 1080 },
  });
  harness.start();
  harness.moveCursor({ x: 150, y: 175 });
  assert.equal(harness.window.bounds.x, 550);
  assert.equal(harness.window.bounds.y, 475);
  harness.moveCursor({ x: 2500, y: 1400 });
  assert.equal(harness.window.bounds.x, 1810);
  assert.equal(harness.window.bounds.y, 970);
  harness.handlers.dispose();
});

test('drag respects negative-origin display coordinates and rejects other renderers', () => {
  const harness = dragHarness({
    bounds: { x: -900, y: 100, width: ORB_SIZE, height: ORB_SIZE },
    workArea: { x: -1280, y: 0, width: 1280, height: 720 },
  });
  harness.ipcMain.emit('ruby:orb:drag-start', { sender: {} });
  harness.ipcMain.emit('ruby:orb:drag-move', { sender: {} });
  assert.equal(harness.window.bounds.x, -900);
  harness.start();
  harness.moveCursor({ x: -1200, y: 30 });
  assert.equal(harness.window.bounds.x, -1280);
  assert.equal(harness.window.bounds.y, 30);
  harness.handlers.dispose();
});

test('collapse preserves an existing orb position and only initializes new windows', () => {
  const existing = createOrbWindow({ x: 420, y: 260, width: ORB_SIZE, height: ORB_SIZE });
  const retained = collapseOrbWindow({
    orbWindow: existing,
    createOrbWindow: () => assert.fail('existing orb should not be recreated'),
    initialBounds: { x: 0, y: 0 },
  });
  assert.equal(retained, existing);
  assert.deepEqual(retained.getBounds(), { x: 420, y: 260, width: ORB_SIZE, height: ORB_SIZE });
  assert.equal(retained.visible, true);

  let createdBounds;
  const created = createOrbWindow({ x: 0, y: 0, width: ORB_SIZE, height: ORB_SIZE });
  const result = collapseOrbWindow({
    orbWindow: null,
    createOrbWindow: (bounds) => {
      createdBounds = bounds;
      return created;
    },
    initialBounds: { x: 1792, y: 952, width: ORB_SIZE, height: ORB_SIZE },
  });
  assert.equal(result, created);
  assert.deepEqual(createdBounds, { x: 1792, y: 952, width: ORB_SIZE, height: ORB_SIZE });
  created.emit('ready-to-show');
  assert.equal(created.visible, true);
});

test('orb position survives expansion and the next collapse', () => {
  const orb = createOrbWindow({ x: 660, y: 430, width: ORB_SIZE, height: ORB_SIZE });
  hideOrbForExpansion(orb);
  assert.equal(orb.visible, false);
  assert.deepEqual(orb.getBounds(), { x: 660, y: 430, width: ORB_SIZE, height: ORB_SIZE });
  const returned = collapseOrbWindow({
    orbWindow: orb,
    createOrbWindow: () => assert.fail('expansion must retain the same orb window'),
    initialBounds: { x: 0, y: 0, width: ORB_SIZE, height: ORB_SIZE },
  });
  assert.equal(returned, orb);
  assert.deepEqual(orb.getBounds(), { x: 660, y: 430, width: ORB_SIZE, height: ORB_SIZE });
  assert.equal(orb.visible, true);
});

test('drag handlers stop moving after end and dispose cleanly', () => {
  const harness = dragHarness({
    bounds: { x: 500, y: 400, width: ORB_SIZE, height: ORB_SIZE },
    workArea: { x: 0, y: 0, width: 1920, height: 1080 },
  });
  harness.start();
  harness.end();
  harness.moveCursor({ x: 300, y: 300 });
  assert.equal(harness.window.bounds.x, 500);
  harness.handlers.dispose();
  assert.equal(harness.ipcMain.listenerCount('ruby:orb:drag-start'), 0);
});
