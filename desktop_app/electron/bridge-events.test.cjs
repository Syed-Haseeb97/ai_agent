'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { BridgeEventPump, diffTaskFrames } = require('./bridge-events.cjs');

const task = (overrides = {}) => ({
  id: 'a'.repeat(32),
  goal: 'do the thing',
  status: 'queued',
  message: 'Queued',
  progress: [],
  execution_mode: 'task_doing',
  execution_environment: 'foreground',
  cancel_requested: false,
  action_count: 0,
  result: null,
  error: null,
  ...overrides,
});

test('diffTaskFrames reports created, status, progress, and metadata changes', () => {
  const created = task();
  const running = task({ status: 'running', message: 'Started' });
  const progressed = task({ status: 'running', message: 'Step 1', progress: [{ message: 'Step 1' }] });
  const cursor = task({
    status: 'running',
    message: 'Started',
    execution_mode: 'cursor_control',
    execution_environment: 'desktop',
    cursor_target: { x: 500, y: 250 },
  });

  assert.deepEqual(diffTaskFrames(null, { tasks: [created] }), []);
  assert.deepEqual(diffTaskFrames({ tasks: [] }, { tasks: [created] }).map((f) => f.change), ['created']);
  assert.deepEqual(diffTaskFrames({ tasks: [created] }, { tasks: [running] }).map((f) => f.change), ['status']);
  assert.equal(diffTaskFrames({ tasks: [created] }, { tasks: [running] })[0].previousStatus, 'queued');
  assert.deepEqual(diffTaskFrames({ tasks: [running] }, { tasks: [progressed] }).map((f) => f.change), ['progress']);
  assert.deepEqual(diffTaskFrames({ tasks: [running] }, { tasks: [cursor] }).map((f) => f.change), ['updated']);
  assert.deepEqual(diffTaskFrames({ tasks: [cursor] }, { tasks: [cursor] }), []);
});

test('the pump only polls a READY backend and forwards state, task frames, and activity', async () => {
  const states = [
    { tasks: [task()], activity: { state: 'queued', queued: 1, running: 0 } },
    { tasks: [task({ status: 'running', message: 'Step 1' })], activity: { state: 'running', queued: 0, running: 1 } },
    { tasks: [task({ status: 'completed', message: 'Done', completed_at: '2026-10-20T10:00:00+00:00' })], activity: { state: 'idle', queued: 0, running: 0 } },
  ];
  const broadcasts = [];
  const pump = new BridgeEventPump({
    request: async () => states.shift(),
    getBackendState: () => ({ status: 'READY' }),
    broadcast: (channel, payload) => broadcasts.push({ channel, payload }),
  });

  assert.deepEqual(await pump.poll(), []);
  assert.equal(broadcasts.filter((item) => item.channel === 'ruby:bridge:changed').length, 1);
  assert.equal(broadcasts.filter((item) => item.channel === 'ruby:bridge:task').length, 0);

  const frames = await pump.poll();
  assert.equal(frames.length, 1);
  assert.equal(frames[0].change, 'status');
  assert.equal(frames[0].task.execution_mode, 'task_doing');
  assert.equal(broadcasts.filter((item) => item.channel === 'ruby:bridge:activity').length, 2);

  const completed = await pump.poll();
  assert.equal(completed[0].change, 'status');
  assert.equal(completed[0].task.status, 'completed');
  const taskFrames = broadcasts.filter((item) => item.channel === 'ruby:bridge:task');
  assert.equal(taskFrames.at(-1).payload.activity.state, 'idle');
});

test('the pump does not touch an unready backend', async () => {
  let requests = 0;
  const pump = new BridgeEventPump({
    request: async () => { requests += 1; return { tasks: [] }; },
    getBackendState: () => ({ status: 'WAITING_FOR_BACKEND' }),
    broadcast: () => { throw new Error('should not broadcast'); },
  });

  assert.equal(await pump.poll(), null);
  assert.equal(requests, 0);
});

test('poll failures are swallowed so the desktop app stays alive', async () => {
  let broadcasts = 0;
  const pump = new BridgeEventPump({
    request: async () => { throw new Error('bridge offline'); },
    getBackendState: () => ({ status: 'READY' }),
    broadcast: () => { broadcasts += 1; },
  });

  assert.equal(await pump.poll(), null);
  assert.equal(broadcasts, 0);
});

test('start schedules the poll interval and stop clears it', () => {
  let scheduled = null;
  let cleared = null;
  const pump = new BridgeEventPump({
    request: async () => ({ tasks: [] }),
    getBackendState: () => ({ status: 'STARTING' }),
    setIntervalFn: (callback, ms) => { scheduled = { callback, ms }; return 'timer-1'; },
    clearIntervalFn: (timer) => { cleared = timer; },
  });

  pump.start();
  assert.equal(scheduled.ms, 1000);
  pump.stop();
  assert.equal(cleared, 'timer-1');
});
