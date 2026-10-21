'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const load = () => import('../src/orbDrag.js');
const pointerEvent = (pointerId, clientX, clientY, button = 0) => ({
  pointerId, clientX, clientY, button,
});
const clickEvent = (detail = 1) => ({ detail });

test('ordinary pointer click invokes the existing action', async () => {
  const { OrbDragController } = await load();
  let actions = 0;
  const controller = new OrbDragController({
    onStart: () => assert.fail('click should not start a drag'),
    onMove: () => assert.fail('click should not move the window'),
    onEnd: () => assert.fail('click should not end a drag'),
  });
  controller.pointerDown(pointerEvent(1, 20, 30));
  controller.pointerUp(pointerEvent(1, 20, 30));
  if (controller.shouldTriggerClick(clickEvent())) actions += 1;
  assert.equal(actions, 1);
});

test('movement beyond the threshold moves the window and suppresses click action', async () => {
  const { OrbDragController } = await load();
  const calls = [];
  const controller = new OrbDragController({
    onStart: () => calls.push('start'),
    onMove: () => calls.push('move'),
    onEnd: () => calls.push('end'),
  });
  controller.pointerDown(pointerEvent(2, 20, 30));
  controller.pointerMove(pointerEvent(2, 26, 30));
  controller.pointerMove(pointerEvent(2, 38, 44));
  controller.pointerUp(pointerEvent(2, 38, 44));
  assert.deepEqual(calls, ['start', 'move', 'move', 'end']);
  assert.equal(controller.shouldTriggerClick(clickEvent()), false);
  assert.equal(controller.shouldTriggerClick(clickEvent()), true);
});

test('movement below the threshold remains a click', async () => {
  const { OrbDragController } = await load();
  const calls = [];
  const controller = new OrbDragController({
    onStart: () => calls.push('start'),
    onMove: () => calls.push('move'),
    onEnd: () => calls.push('end'),
  });
  controller.pointerDown(pointerEvent(3, 10, 10));
  controller.pointerMove(pointerEvent(3, 13, 14));
  controller.pointerUp(pointerEvent(3, 13, 14));
  assert.deepEqual(calls, []);
  assert.equal(controller.shouldTriggerClick(clickEvent()), true);
});

test('release position beyond the threshold is still treated as a drag', async () => {
  const { OrbDragController } = await load();
  const calls = [];
  const controller = new OrbDragController({
    onStart: () => calls.push('start'),
    onMove: () => calls.push('move'),
    onEnd: () => calls.push('end'),
  });
  controller.pointerDown(pointerEvent(5, 10, 10));
  controller.pointerUp(pointerEvent(5, 10, 16));
  assert.deepEqual(calls, ['start', 'move', 'end']);
  assert.equal(controller.shouldTriggerClick(clickEvent()), false);
});

test('pointer cancellation and lost capture end an active drag exactly once', async () => {
  const { OrbDragController } = await load();
  const calls = [];
  const controller = new OrbDragController({
    onStart: () => calls.push('start'),
    onMove: () => calls.push('move'),
    onEnd: () => calls.push('end'),
  });
  controller.pointerDown(pointerEvent(4, 10, 10));
  controller.pointerMove(pointerEvent(4, 20, 10));
  controller.pointerCancel(pointerEvent(4, 20, 10));
  controller.lostPointerCapture(pointerEvent(4, 20, 10));
  assert.deepEqual(calls, ['start', 'move', 'end']);
  assert.equal(controller.shouldTriggerClick(clickEvent()), false);
});
