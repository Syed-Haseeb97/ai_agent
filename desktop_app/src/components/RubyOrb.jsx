import { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  ERROR_HOLD_MS,
  SUCCESS_HOLD_MS,
  gazeFromCursorTarget,
  orbStateLabel,
  orbAppearance,
  orbMotionMode,
  selectOrbVisual,
  transientForTask,
} from '../orbState';
import { OrbDragController } from '../orbDrag';

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

export function RubyOrb({ label = 'Ruby', onClick, draggable = false }) {
  const { tasks, transient } = useBridgeOrbSignal();
  const visual = selectOrbVisual(tasks, transient);
  const gaze = gazeFromCursorTarget(visual.cursorTarget);
  const appearance = orbAppearance(visual.state);
  const statusText = visual.message || orbStateLabel(visual.state);
  const accessibleLabel = label && label !== 'Ruby' ? `${label} — ${statusText}` : statusText;
  const onClickRef = useRef(onClick);
  onClickRef.current = onClick;
  const dragControllerRef = useRef(null);
  if (!dragControllerRef.current) {
    dragControllerRef.current = new OrbDragController({
      onStart: () => window.rubyDesktop?.orbDrag.start(),
      onMove: () => window.rubyDesktop?.orbDrag.move(),
      onEnd: () => window.rubyDesktop?.orbDrag.end(),
    });
  }
  const dragController = dragControllerRef.current;
  const [reducedMotion, setReducedMotion] = useState(() => (
    typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ));

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(query.matches);
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, []);

  const handlePointerDown = (event) => {
    dragController.pointerDown(event);
    if (event.button === 0) event.currentTarget.setPointerCapture(event.pointerId);
  };
  const handlePointerMove = (event) => dragController.pointerMove(event);
  const handlePointerUp = (event) => dragController.pointerUp(event);
  const handlePointerCancel = (event) => dragController.pointerCancel(event);
  const handleLostPointerCapture = (event) => dragController.lostPointerCapture(event);

  return (
    <button
      type="button"
      className={`ruby-trigger orb-${visual.state}`}
      data-state={visual.state}
      data-mode={visual.mode || 'idle'}
      onPointerDown={draggable ? handlePointerDown : undefined}
      onPointerMove={draggable ? handlePointerMove : undefined}
      onPointerUp={draggable ? handlePointerUp : undefined}
      onPointerCancel={draggable ? handlePointerCancel : undefined}
      onLostPointerCapture={draggable ? handleLostPointerCapture : undefined}
      onClick={(event) => {
        if (!dragController.shouldTriggerClick(event)) {
          event.preventDefault();
          return;
        }
        onClickRef.current?.();
      }}
      aria-label={accessibleLabel}
      title={accessibleLabel}
    >
      <span
        className={`ruby-orb-wrap orb-${visual.state}`}
        data-motion={orbMotionMode(reducedMotion)}
        style={{
          '--orb-gaze-x': `${gaze.x}px`,
          '--orb-gaze-y': `${gaze.y}px`,
          '--orb-accent': appearance.accent,
          '--orb-secondary': appearance.secondary,
          '--orb-glow': appearance.glow,
        }}
        aria-hidden="true"
      >
        <OrbArtwork state={visual.state} />
        <span className="ruby-target" />
        <span className="ruby-status-dot" />
      </span>
    </button>
  );
}

function OrbArtwork({ state }) {
  const id = `ruby-orb-${useId().replace(/:/g, '')}`;
  return (
    <svg className="ruby-orb" viewBox="0 0 100 100" role="presentation">
      <defs>
        <radialGradient id={`${id}-body`} cx="34%" cy="24%" r="83%">
          <stop offset="0%" stopColor="#fff" stopOpacity=".92" />
          <stop offset="17%" stopColor="var(--orb-accent)" />
          <stop offset="64%" stopColor="var(--orb-secondary)" />
          <stop offset="100%" stopColor="#090914" />
        </radialGradient>
        <linearGradient id={`${id}-plasma`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--orb-accent)" stopOpacity=".08" />
          <stop offset="44%" stopColor="var(--orb-accent)" stopOpacity=".88" />
          <stop offset="72%" stopColor="#fb8cff" stopOpacity=".82" />
          <stop offset="100%" stopColor="var(--orb-secondary)" stopOpacity=".12" />
        </linearGradient>
        <clipPath id={`${id}-clip`}>
          <path d="M50 7 C61 4 70 11 77 18 C89 21 96 34 91 46 C98 58 92 71 81 78 C77 91 62 97 51 91 C39 98 26 92 20 82 C8 78 3 65 9 53 C3 41 9 28 20 21 C26 10 39 4 50 7 Z" />
        </clipPath>
      </defs>
      <g className="orb-body">
        <path
          className="orb-shell"
          d="M50 7 C61 4 70 11 77 18 C89 21 96 34 91 46 C98 58 92 71 81 78 C77 91 62 97 51 91 C39 98 26 92 20 82 C8 78 3 65 9 53 C3 41 9 28 20 21 C26 10 39 4 50 7 Z"
          fill={`url(#${id}-body)`}
        />
        <g className="orb-plasma" clipPath={`url(#${id}-clip)`}>
          <path className="orb-plasma-stream stream-one" d="M-8 38 C15 13 30 62 51 39 S80 19 109 42" />
          <path className="orb-plasma-stream stream-two" d="M-6 66 C16 38 31 83 53 59 S82 41 108 67" />
          <path className="orb-plasma-cloud" d="M10 30 C26 15 38 24 47 32 C59 42 73 16 91 28 C103 39 82 57 66 53 C50 49 42 72 27 63 C15 56 1 43 10 30 Z" fill={`url(#${id}-plasma)`} />
          <ellipse className="orb-core-glint" cx="35" cy="25" rx="18" ry="9" />
        </g>
        <path className="orb-glass-sheen" d="M24 18 C34 9 48 9 56 13 C43 14 32 21 26 32 C23 28 22 23 24 18 Z" />
        <g className="orb-face">
          <path className="orb-brow brow-left" d="M28 37 Q35 33 42 37" />
          <path className="orb-brow brow-right" d="M58 37 Q65 33 72 37" />
          <g className="orb-eye eye-left">
            <g className="orb-eye-lid">
              <ellipse className="orb-eye-white" cx="35" cy="46" rx="5.2" ry="7.4" />
              <ellipse className="orb-pupil" cx="36" cy="47" rx="2.1" ry="3.2" />
              <circle className="orb-eye-glint" cx="36.5" cy="45" r="1" />
            </g>
          </g>
          <g className="orb-eye eye-right">
            <g className="orb-eye-lid">
              <ellipse className="orb-eye-white" cx="65" cy="46" rx="5.2" ry="7.4" />
              <ellipse className="orb-pupil" cx="66" cy="47" rx="2.1" ry="3.2" />
              <circle className="orb-eye-glint" cx="66.5" cy="45" r="1" />
            </g>
          </g>
          <path className="orb-mouth mouth-idle" d="M43 63 Q50 67 57 63" />
          <path className="orb-mouth mouth-success" d="M40 61 Q50 72 60 61" />
          <path className="orb-mouth mouth-error" d="M42 68 Q50 60 58 68" />
        </g>
      </g>
    </svg>
  );
}
