import { useCallback, useEffect, useId, useRef, useState } from 'react';
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
        <OrbArtwork state={visual.state} gaze={gaze} />
        <span className="ruby-target" />
        <span className="ruby-status-dot" />
      </span>
    </button>
  );
}

/**
 * SVG recreation of Ruby's original living liquid orb. The shell, plasma
 * currents, dark face core, and highlights stay together as one scalable asset
 * so the compact sidebar and standalone orb render the same character.
 */
function OrbArtwork({ state, gaze }) {
  const rawId = useId();
  const id = `ruby-liquid-${rawId.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  return (
    <svg className="ruby-orb ruby-liquid-art" viewBox="0 0 100 100" role="presentation">
      <defs>
        <linearGradient id={`${id}-shell`} x1="12%" y1="5%" x2="88%" y2="94%">
          <stop offset="0%" stopColor="var(--orb-highlight)" />
          <stop offset="24%" stopColor="var(--orb-accent)" />
          <stop offset="58%" stopColor="var(--orb-secondary)" />
          <stop offset="100%" stopColor="#090b18" />
        </linearGradient>
        <linearGradient id={`${id}-stream`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e7dfff" stopOpacity=".15" />
          <stop offset="36%" stopColor="var(--orb-accent)" stopOpacity=".95" />
          <stop offset="66%" stopColor="#8bdcff" stopOpacity=".9" />
          <stop offset="100%" stopColor="var(--orb-secondary)" stopOpacity=".08" />
        </linearGradient>
        <radialGradient id={`${id}-shine`} cx="29%" cy="19%" r="75%">
          <stop offset="0%" stopColor="#fff" stopOpacity=".9" />
          <stop offset="24%" stopColor="#fff" stopOpacity=".2" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={`${id}-core`} cx="34%" cy="25%" r="80%">
          <stop offset="0%" stopColor="#202033" />
          <stop offset="58%" stopColor="#080a12" />
          <stop offset="100%" stopColor="#020309" />
        </radialGradient>
        <clipPath id={`${id}-clip`}>
          <path d="M50 4 C62 2 71 10 77 17 C90 20 97 33 92 45 C99 58 93 72 81 79 C77 92 63 97 51 92 C38 99 25 92 19 82 C7 78 2 65 8 52 C2 40 9 27 20 20 C26 9 39 3 50 4 Z" />
        </clipPath>
      </defs>
      <g className="orb-liquid-body">
        <path className="orb-liquid-shell" d="M50 4 C62 2 71 10 77 17 C90 20 97 33 92 45 C99 58 93 72 81 79 C77 92 63 97 51 92 C38 99 25 92 19 82 C7 78 2 65 8 52 C2 40 9 27 20 20 C26 9 39 3 50 4 Z" fill={`url(#${id}-shell)`} />
        <g className="orb-liquid-current" clipPath={`url(#${id}-clip)`}>
          <path className="orb-current-line current-a" d="M-10 34 C12 13 24 58 43 41 S74 14 110 35" />
          <path className="orb-current-line current-b" d="M-8 60 C13 37 29 78 50 59 S81 39 110 61" />
          <path className="orb-current-line current-c" d="M2 81 C25 53 43 90 65 69 S90 60 108 76" />
          <path className="orb-current-cloud" d="M8 27 C24 12 38 24 47 31 C60 41 73 16 91 28 C103 39 82 56 67 53 C51 49 42 72 27 63 C14 56 0 41 8 27 Z" fill={`url(#${id}-stream)`} />
          <ellipse className="orb-current-glint" cx="34" cy="23" rx="19" ry="9" />
        </g>
        <path className="orb-liquid-sheen" d="M21 19 C32 7 49 7 59 13 C44 13 31 23 25 35 C21 30 19 24 21 19 Z" fill={`url(#${id}-shine)`} />
        <ellipse className="orb-liquid-core" cx="50" cy="51" rx="32" ry="31" fill={`url(#${id}-core)`} />
        <g className="orb-liquid-face">
          <path className="orb-face-brow brow-left" d="M30 40 Q36 36 42 40" />
          <path className="orb-face-brow brow-right" d="M58 40 Q64 36 70 40" />
          <g className="orb-face-eye eye-left">
            <ellipse className="orb-face-eye-white" cx="36" cy="47" rx="5.1" ry="7.2" />
            <ellipse className="orb-face-pupil" cx={36 + gaze.x} cy={48 + gaze.y} rx="2.2" ry="3.2" />
            <circle className="orb-face-glint" cx="36.5" cy="45" r="1.1" />
          </g>
          <g className="orb-face-eye eye-right">
            <ellipse className="orb-face-eye-white" cx="64" cy="47" rx="5.1" ry="7.2" />
            <ellipse className="orb-face-pupil" cx={64 + gaze.x} cy={48 + gaze.y} rx="2.2" ry="3.2" />
            <circle className="orb-face-glint" cx="64.5" cy="45" r="1.1" />
          </g>
          <path className="orb-face-mouth mouth-idle" d="M43 64 Q50 68 57 64" />
          <path className="orb-face-mouth mouth-success" d="M40 62 Q50 73 60 62" />
          <path className="orb-face-mouth mouth-error" d="M42 69 Q50 60 58 69" />
        </g>
      </g>
    </svg>
  );
}

