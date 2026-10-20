'use strict';

const ACTIVE_STATUSES = new Set(['created', 'queued', 'running', 'verifying']);

const sameJson = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function taskChange(before, task) {
  if (!before) return 'created';
  if (before.status !== task.status) return 'status';
  if ((before.progress?.length || 0) !== (task.progress?.length || 0) ||
      before.message !== task.message) return 'progress';
  if (before.execution_mode !== task.execution_mode ||
      before.execution_environment !== task.execution_environment ||
      before.cancel_requested !== task.cancel_requested ||
      before.action_count !== task.action_count ||
      before.cursor_target?.x !== task.cursor_target?.x ||
      before.cursor_target?.y !== task.cursor_target?.y ||
      !sameJson(before.result, task.result) ||
      !sameJson(before.error, task.error)) return 'updated';
  return null;
}

/**
 * Compare two bridge snapshots and return renderer-friendly task frames.
 * The initial snapshot returns no frames; it is delivered as full state.
 */
function diffTaskFrames(previousState, nextState) {
  if (!previousState || !nextState) return [];
  const previous = new Map((previousState.tasks || []).map((task) => [task.id, task]));
  const frames = [];
  for (const task of nextState.tasks || []) {
    if (!task || !task.id) continue;
    const before = previous.get(task.id);
    const change = taskChange(before, task);
    if (change) frames.push({ change, task, previousStatus: before?.status || null });
  }
  return frames;
}

class BridgeEventPump {
  constructor({
    request,
    getBackendState = () => null,
    broadcast = () => {},
    intervalMs = 1000,
    setIntervalFn = setInterval,
    clearIntervalFn = clearInterval,
  } = {}) {
    if (typeof request !== 'function') throw new TypeError('request must be a function');
    this._request = request;
    this._getBackendState = getBackendState;
    this._broadcast = broadcast;
    this._intervalMs = intervalMs;
    this._setInterval = setIntervalFn;
    this._clearInterval = clearIntervalFn;
    this._timer = null;
    this._inFlight = null;
    this._lastState = null;
    this._lastSignature = null;
    this._lastActivitySignature = null;
  }

  start() {
    if (this._timer !== null) return;
    this._timer = this._setInterval(() => { void this.poll(); }, this._intervalMs);
    void this.poll();
  }

  stop() {
    if (this._timer !== null) {
      this._clearInterval(this._timer);
      this._timer = null;
    }
  }

  reset() {
    this._lastState = null;
    this._lastSignature = null;
    this._lastActivitySignature = null;
  }

  async refresh() {
    if (this._inFlight) {
      try { await this._inFlight; } catch {}
    }
    return this.poll();
  }

  poll() {
    if (this._inFlight) return this._inFlight;
    const runtime = this._getBackendState?.();
    if (!runtime || runtime.status !== 'READY') return Promise.resolve(null);
    this._inFlight = this._pollOnce().finally(() => { this._inFlight = null; });
    return this._inFlight;
  }

  async _pollOnce() {
    let state;
    try {
      state = await this._request('/v1/state');
    } catch {
      return null;
    }
    if (!state || !Array.isArray(state.tasks)) return null;

    const frames = diffTaskFrames(this._lastState, state);
    this._lastState = state;

    const signature = JSON.stringify(state);
    if (signature !== this._lastSignature) {
      this._lastSignature = signature;
      this._broadcast('ruby:bridge:changed', state);
    }

    for (const frame of frames) {
      this._broadcast('ruby:bridge:task', { ...frame, activity: state.activity || null });
    }

    const activitySignature = JSON.stringify(state.activity || null);
    if (activitySignature !== this._lastActivitySignature) {
      this._lastActivitySignature = activitySignature;
      this._broadcast('ruby:bridge:activity', state.activity || null);
    }
    return frames;
  }
}

module.exports = { ACTIVE_STATUSES, BridgeEventPump, diffTaskFrames, taskChange };
