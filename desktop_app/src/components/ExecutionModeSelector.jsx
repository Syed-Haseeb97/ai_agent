import { Clock3, MousePointer2, Sparkles } from 'lucide-react';

export const DEFAULT_EXECUTION_MODE = 'task_doing';

export const EXECUTION_MODES = [
  { id: 'cursor_control', label: 'Cursor control', icon: MousePointer2, hint: 'Ruby drives the desktop with direct cursor actions.' },
  { id: 'task_doing', label: 'Task doing', icon: Sparkles, hint: 'Ruby runs the task step by step in the foreground.' },
  { id: 'background_task', label: 'Background task', icon: Clock3, hint: 'Ruby works on the task while you continue elsewhere.' },
];

export function ExecutionModeSelector({ value, onChange }) {
  const active = EXECUTION_MODES.find(mode => mode.id === value) || EXECUTION_MODES[1];
  return (
    <div className="execution-modes" role="radiogroup" aria-label="Execution mode">
      <span className="execution-modes-label">Execution mode</span>
      <div className="execution-mode-options">
        {EXECUTION_MODES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={value === id}
            className={`execution-mode${value === id ? ' selected' : ''}`}
            onClick={() => onChange(id)}
          >
            <Icon size={13} aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      <p className="execution-mode-hint">{active.hint}</p>
    </div>
  );
}
