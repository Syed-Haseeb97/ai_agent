export const ACTIVE_STATUSES = Object.freeze(['created', 'queued', 'running', 'verifying']);
export const TERMINAL_STATUSES = Object.freeze(['completed', 'failed', 'cancelled', 'timeout']);
export const SUCCESS_HOLD_MS = 2200;
export const ERROR_HOLD_MS = 3000;
const RECENT_COMPLETION_MS = 5000;

export const ORB_APPEARANCE = Object.freeze({
  idle: Object.freeze({ accent: '#8b5cf6', secondary: '#2563eb', glow: '139, 92, 246' }),
  thinking: Object.freeze({ accent: '#a78bfa', secondary: '#4f46e5', glow: '167, 139, 250' }),
  working: Object.freeze({ accent: '#22d3ee', secondary: '#2563eb', glow: '34, 211, 238' }),
  success: Object.freeze({ accent: '#34d399', secondary: '#059669', glow: '52, 211, 153' }),
  error: Object.freeze({ accent: '#ff526b', secondary: '#b91235', glow: '255, 82, 107' }),
});

export function orbAppearance(state) {
  return ORB_APPEARANCE[state] || ORB_APPEARANCE.idle;
}

export function orbMotionMode(prefersReducedMotion) {
  return prefersReducedMotion ? 'reduced' : 'full';
}

export const isActiveTask = (task) => Boolean(task) && ACTIVE_STATUSES.includes(task.status);
export const isTerminalTask = (task) => Boolean(task) && TERMINAL_STATUSES.includes(task.status);

/**
 * Pick the orb expression from the bridge task list. Active work always wins
 * over a transient success/error flash left over from a previous task.
 */
export function selectOrbVisual(tasks = [], transient = null) {
  const active = tasks.filter(isActiveTask);
  if (active.length) {
    const cursorTask = active.find((task) => task.execution_mode === 'cursor_control');
    const task = cursorTask || active[0];
    return {
      state: cursorTask ? 'working' : 'thinking',
      mode: task.execution_mode || 'task_doing',
      task,
      cursorTarget: cursorTask?.cursor_target || null,
      message: task.message || '',
    };
  }
  if (transient && (transient.state === 'success' || transient.state === 'error')) {
    return {
      state: transient.state,
      mode: null,
      task: transient.task || null,
      cursorTarget: null,
      message: transient.message || '',
    };
  }
  return { state: 'idle', mode: null, task: null, cursorTarget: null, message: '' };
}

/**
 * Decide whether a task update should flash success/error. A task that was
 * already terminal before the renderer saw it only flashes when it finished
 * within the last few seconds (covers very fast bridge tasks).
 */
export function transientForTask(before, task, now = Date.now()) {
  if (!isTerminalTask(task)) return null;
  if (before) {
    if (before.status === task.status) return null;
    return task.status === 'completed' ? 'success' : 'error';
  }
  const finishedAt = Date.parse(task.completed_at || '') || 0;
  if (!finishedAt || now - finishedAt > RECENT_COMPLETION_MS) return null;
  return task.status === 'completed' ? 'success' : 'error';
}

/** Convert F16's normalized 0-999 target into a small eye-gaze offset. */
export function gazeFromCursorTarget(target) {
  if (!target || !Number.isFinite(target.x) || !Number.isFinite(target.y)) return { x: 0, y: 0 };
  const clamp = (value) => Math.max(-1, Math.min(1, value));
  return {
    x: clamp((target.x - 500) / 500) * 2.5,
    y: clamp((target.y - 500) / 500) * 2,
  };
}

export function orbStateLabel(state) {
  switch (state) {
    case 'thinking': return 'Ruby is working on a task';
    case 'working': return 'Ruby is controlling the desktop';
    case 'success': return 'Ruby finished the task';
    case 'error': return 'Ruby needs attention';
    default: return 'Ruby is idle';
  }
}
