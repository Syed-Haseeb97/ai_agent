import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ERROR_HOLD_MS,
  SUCCESS_HOLD_MS,
  gazeFromCursorTarget,
  orbStateLabel,
  selectOrbVisual,
  transientForTask,
} from '../orbState';

function useBridgeOrbSignal() {
  const tasksRef = useRef(new Map());
  const [tasks, setTasks] = useState([]);
  const [transient, setTransient] = useState(null);
  const timerRef = useRef(null);
  const initializedRef = useRef(false);

  const flash = useCallback((state, task) => {
    if (!state) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    setTransient({ state, task, message: task?.message || '' });
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      setTransient(null);
    }, state === 'success' ? SUCCESS_HOLD_MS : ERROR_HOLD_MS);
  }, []);

  const applyTasks = useCallback((list) => {
    const next = new Map();
    for (const task of list || []) {
      if (task?.id) next.set(task.id, task);
    }
    let flashState = null;
    let flashTask = null;
    for (const [id, task] of next) {
      const transition = transientForTask(tasksRef.current.get(id), task);
      if (transition) {
        flashState = transition;
        flashTask = task;
      }
    }
    tasksRef.current = next;
    setTasks(Array.from(next.values()));
    if (flashState) flash(flashState, flashTask);
  }, [flash]);

  useEffect(() => {
    const bridge = window.rubyDesktop?.bridge;
    if (!bridge) return undefined;

    const unsubscribeState = bridge.onState?.((state) => {
      initializedRef.current = true;
      applyTasks(state?.tasks);
    });
    const unsubscribeTask = bridge.onTask?.((frame) => {
      const task = frame?.task;
      if (!task?.id) return;
      initializedRef.current = true;
      const before = tasksRef.current.get(task.id);
      const next = new Map(tasksRef.current);
      next.set(task.id, task);
      tasksRef.current = next;
      setTasks(Array.from(next.values()));
      const transition = transientForTask(before, task);
      if (transition) flash(transition, task);
    });

    bridge.getState?.()
      .then((state) => {
        if (!initializedRef.current && state?.tasks) {
          initializedRef.current = true;
          applyTasks(state.tasks);
        }
      })
      .catch(() => {});

    return () => {
      unsubscribeState?.();
      unsubscribeTask?.();
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [applyTasks, flash]);

  return { tasks, transient };
}

export function RubyOrb({ label = 'Ruby', onClick }) {
  const { tasks, transient } = useBridgeOrbSignal();
  const visual = selectOrbVisual(tasks, transient);
  const gaze = gazeFromCursorTarget(visual.cursorTarget);
  const statusText = visual.message || orbStateLabel(visual.state);
  const accessibleLabel = label && label !== 'Ruby' ? `${label} — ${statusText}` : statusText;

  return (
    <button
      type="button"
      className={`ruby-trigger orb-${visual.state}`}
      data-state={visual.state}
      data-mode={visual.mode || 'idle'}
      aria-label={accessibleLabel}
      title={accessibleLabel}
      onClick={onClick}
    >
      <span
        className={`ruby-orb-wrap orb-${visual.state}`}
        style={{ '--orb-gaze-x': `${gaze.x}px`, '--orb-gaze-y': `${gaze.y}px` }}
        aria-hidden="true"
      >
        <span className="ruby-orb"><span className="ruby-eye left" /><span className="ruby-eye right" /></span>
        <span className="ruby-target" />
        <span className="ruby-status-dot" />
      </span>
    </button>
  );
}
