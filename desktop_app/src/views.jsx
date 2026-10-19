import { useState } from 'react';
import { Clock3, FolderKanban, History, MessageSquare, Settings, Sparkles, Square, Check, X, RefreshCw } from 'lucide-react';
import { Header } from './components/Header';
import { RubyOrb } from './components/RubyOrb';

const terminal = new Set(['completed', 'failed', 'cancelled', 'timeout']);
const label = (s = 'unknown') => s.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());

function Status({ connected, error }) {
  return <div className={`bridge-status ${connected ? 'online' : 'offline'}`}><i />{connected ? 'Assistant bridge connected' : error || 'Connecting to assistant bridge…'}</div>;
}

function TaskCard({ task, refresh }) {
  const [busy, setBusy] = useState(false);
  const stop = async () => {
    setBusy(true);
    try { await window.rubyDesktop.bridge.cancelTask(task.id); await refresh(); }
    catch (error) { window.alert(error.message); }
    finally { setBusy(false); }
  };
  return <article className="agent-card task-card">
    <div className="agent-card-top"><div className="agent-icon"><Sparkles size={16} /></div><span className={`state-badge ${task.status}`}><span className="state-dot" />{label(task.status)}</span></div>
    <h3>{task.goal}</h3><p>{task.message || task.error?.message || 'Waiting for Ruby…'}</p>
    {task.progress?.length > 0 && <ul className="task-progress">{task.progress.slice(-3).map((p, i) => <li key={`${p.timestamp}-${i}`}>{p.message}</li>)}</ul>}
    {task.result?.summary && <p className="task-result">{task.result.summary}{task.result.verified ? ' · Verified' : ''}</p>}
    {task.error && <p className="task-error">{task.error.code}: {task.error.message}</p>}
    {task.outputs?.length > 0 && <div className="task-outputs">{task.outputs.map(o => <div key={o.path}>{o.path}{o.verified ? ' · verified' : ''}</div>)}</div>}
    <div className="agent-footer"><span>{task.action_count || 0} actions</span>{!terminal.has(task.status) && <button className="stop-button" disabled={busy} onClick={stop}><Square size={12} fill="currentColor" /> Stop</button>}</div>
  </article>;
}

function Confirmations({ confirmations = [], refresh }) {
  const [busyId, setBusyId] = useState('');
  const decide = async (item, approved) => {
    setBusyId(item.id);
    try { await window.rubyDesktop.bridge.respondConfirmation(item.id, approved); await refresh(); }
    catch (error) { window.alert(error.message); }
    finally { setBusyId(''); }
  };
  if (!confirmations.length) return null;
  return <section className="section"><div className="section-heading"><div><span className="eyebrow">ACTION REVIEW</span><h2>Ruby needs your approval</h2></div></div>{confirmations.map(c => <article className="confirmation-card" key={c.id}><strong>{c.summary}</strong><p>{c.reason}</p><pre>{typeof c.details === 'string' ? c.details : JSON.stringify(c.details, null, 2)}</pre><div><button className="new-button" disabled={busyId === c.id} onClick={() => decide(c, true)}><Check size={14} /> Approve once</button><button className="stop-button" disabled={busyId === c.id} onClick={() => decide(c, false)}><X size={14} /> Deny</button></div></article>)}</section>;
}

export function HomeView({ setActive, state, error, refresh }) {
  const tasks = state?.tasks || [];
  const activeTasks = tasks.filter(t => !terminal.has(t.status)).slice(0, 2);
  return <><Header title="Ruby workspace" /><Status connected={Boolean(state) && !error} error={error} /><section className="hero-panel"><div><div className="hero-kicker"><Sparkles size={15} /> Local assistant</div><h2>What should Ruby work on?</h2><p>Submit a task to the Python assistant. Ruby runs it through the local bridge and reports progress here.</p></div><div className="quick-input"><span>Describe a task for Ruby…</span><button onClick={() => setActive('chat')}><MessageSquare size={17} /> New task</button></div></section><Confirmations confirmations={state?.confirmations} refresh={refresh} /><section className="section"><div className="section-heading"><div><span className="eyebrow">LIVE FROM PYTHON</span><h2>Active tasks</h2></div><button className="text-button" onClick={() => setActive('agents')}>View all →</button></div><div className="agent-grid">{activeTasks.length ? activeTasks.map(t => <TaskCard key={t.id} task={t} refresh={refresh} />) : <p className="empty-state">No active tasks. Start one to see Ruby's live status here.</p>}</div></section></>;
}

export function AgentsView({ state, error, refresh, history = false }) {
  const tasks = state?.tasks || [];
  const shown = history ? tasks.filter(t => terminal.has(t.status)) : tasks;
  return <><Header title={history ? 'Task history' : 'Ruby tasks'} /><Status connected={Boolean(state) && !error} error={error} /><div className="canvas-toolbar"><div><span className="eyebrow">PYTHON ASSISTANT · LOCAL BRIDGE</span><p>{history ? 'Completed and stopped tasks reported by Ruby.' : 'Live task states and results from the Python assistant.'}</p></div><button className="ghost-button" onClick={refresh}><RefreshCw size={13} /> Refresh</button></div><Confirmations confirmations={state?.confirmations} refresh={refresh} /><div className="agent-grid wide">{shown.length ? shown.map(t => <TaskCard key={t.id} task={t} refresh={refresh} />) : <p className="empty-state">{state ? 'No tasks yet.' : 'Waiting for the Python bridge to connect.'}</p>}</div></>;
}

export function ChatView({ state, error, refresh }) {
  const [goal, setGoal] = useState('');
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState('');
  const submit = async (event) => {
    event.preventDefault();
    if (!goal.trim() || !window.rubyDesktop?.bridge) return;
    setSending(true); setMessage('');
    try { await window.rubyDesktop.bridge.submitTask(goal); setGoal(''); setMessage('Task submitted to Ruby.'); await refresh(); }
    catch (e) { setMessage(e.message || 'Could not submit the task.'); }
    finally { setSending(false); }
  };
  return <><Header title="New task" /><Status connected={Boolean(state) && !error} error={error} /><div className="chat-surface"><div className="chat-empty"><RubyOrb /><h2>Give Ruby a task</h2><p>This sends work to the Python assistant through the localhost bridge. The task panel shows progress, approvals, outputs, and errors.</p></div><form className="chat-input task-compose" onSubmit={submit}><textarea aria-label="Task for Ruby" maxLength={4000} placeholder="Describe what Ruby should do…" value={goal} onChange={e => setGoal(e.target.value)} /><button type="submit" disabled={sending || !goal.trim() || !state || Boolean(error)}><MessageSquare size={16} /> {sending ? 'Sending…' : 'Start task'}</button></form>{message && <p className="bridge-message">{message}</p>}</div></>;
}

export function Placeholder({ title, eyebrow, description, icon: Icon }) {
  return <><Header title={title} /><div className="placeholder"><div className="placeholder-icon"><Icon size={23} /></div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{description}</p></div></>;
}

export const placeholderViews = {
  projects: { title: 'Projects', eyebrow: 'WORKSPACES', description: 'Project folders and task workspace configuration are not connected yet.', icon: FolderKanban },
  settings: { title: 'Settings', eyebrow: 'CONFIGURATION', description: 'Assistant configuration is managed by the Python runtime.', icon: Settings },
  tasks: { title: 'Tasks', eyebrow: 'AUTOMATIONS', description: 'Background tasks are managed by the Python assistant.', icon: Clock3 },
  history: { title: 'History', eyebrow: 'PAST RUNS', description: 'Review previous background task runs.', icon: History },
};
