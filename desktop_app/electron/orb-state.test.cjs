'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const load = () => import('../src/orbState.js');

test('active cursor control maps to working and carries its target', async () => {
  const { selectOrbVisual, gazeFromCursorTarget } = await load();
  const visual = selectOrbVisual([
    { status: 'running', execution_mode: 'cursor_control', message: 'Desktop action: click', cursor_target: { x: 900, y: 100 } },
  ]);

  assert.equal(visual.state, 'working');
  assert.equal(visual.mode, 'cursor_control');
  assert.deepEqual(visual.cursorTarget, { x: 900, y: 100 });
  assert.ok(gazeFromCursorTarget(visual.cursorTarget).x > 0);
  assert.ok(gazeFromCursorTarget(visual.cursorTarget).y < 0);
  assert.deepEqual(gazeFromCursorTarget(null), { x: 0, y: 0 });
});

test('queued and running managed tasks map to thinking', async () => {
  const { selectOrbVisual } = await load();

  assert.equal(selectOrbVisual([{ status: 'created', execution_mode: 'task_doing' }]).state, 'thinking');
  assert.equal(selectOrbVisual([{ status: 'queued', execution_mode: 'background_task' }]).state, 'thinking');
  assert.equal(selectOrbVisual([{ status: 'running', execution_mode: 'task_doing' }]).state, 'thinking');
  assert.equal(selectOrbVisual([{ status: 'verifying', execution_mode: 'task_doing' }]).state, 'thinking');
});

test('an active task wins over a leftover transient flash', async () => {
  const { selectOrbVisual } = await load();
  const visual = selectOrbVisual(
    [{ status: 'running', execution_mode: 'task_doing' }],
    { state: 'success' },
  );

  assert.equal(visual.state, 'thinking');
});

test('completed, failed, and cancelled transitions trigger the right flash', async () => {
  const { transientForTask } = await load();

  assert.equal(transientForTask({ status: 'running' }, { status: 'completed' }), 'success');
  assert.equal(transientForTask({ status: 'running' }, { status: 'failed' }), 'error');
  assert.equal(transientForTask({ status: 'running' }, { status: 'cancelled' }), 'error');
  assert.equal(transientForTask({ status: 'running' }, { status: 'running' }), null);
  assert.equal(transientForTask({ status: 'completed' }, { status: 'completed' }), null);
});

test('a task first seen as terminal only flashes when it just finished', async () => {
  const { transientForTask } = await load();
  const now = Date.parse('2026-10-20T12:00:00Z');

  assert.equal(transientForTask(null, { status: 'completed', completed_at: '2026-10-20T11:59:58Z' }, now), 'success');
  assert.equal(transientForTask(null, { status: 'completed', completed_at: '2026-10-20T11:00:00Z' }, now), null);
  assert.equal(transientForTask(null, { status: 'failed', completed_at: '2026-10-20T11:59:58Z' }, now), 'error');
});

test('idle is the fallback when there is no work or transient', async () => {
  const { selectOrbVisual, orbStateLabel } = await load();

  assert.equal(selectOrbVisual([]).state, 'idle');
  assert.equal(selectOrbVisual([], { state: 'success' }).state, 'success');
  assert.equal(selectOrbVisual([], { state: 'error' }).state, 'error');
  assert.match(orbStateLabel('idle'), /idle/i);
  assert.match(orbStateLabel('working'), /desktop/i);
});
