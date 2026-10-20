import { useState } from 'react';
import { Clock3, FolderKanban, History, MessageSquare, Settings, Sparkles, Square, Check, X, RefreshCw } from 'lucide-react';
import { Header } from './components/Header';
import { RubyOrb } from './components/RubyOrb';
import { ExecutionModeSelector } from './components/ExecutionModeSelector';

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

export function HomeView({ setActive, state, error, refresh, executionMode, setExecutionMode }) {
  const tasks = state?.tasks || [];
  const activeTasks = tasks.filter(t => !terminal.has(t.status)).slice(0, 2);
  return <><Header title="Ruby workspace" /><Status connected={Boolean(state) && !error} error={error} /><section className="hero-panel"><div><div className="hero-kicker"><Sparkles size={15} /> Local assistant</div><h2>What should Ruby work on?</h2><p>Submit a task to the Python assistant. Ruby runs it through the local bridge and reports progress here.</p></div><div className="quick-input"><span>Describe a task for Ruby…</span><button onClick={() => setActive('chat')}><MessageSquare size={17} /> Chat with Ruby</button></div><ExecutionModeSelector value={executionMode} onChange={setExecutionMode} /></section><Confirmations confirmations={state?.confirmations} refresh={refresh} /><section className="section"><div className="section-heading"><div><span className="eyebrow">LIVE FROM PYTHON</span><h2>Active tasks</h2></div><button className="text-button" onClick={() => setActive('agents')}>View all →</button></div><div className="agent-grid">{activeTasks.length ? activeTasks.map(t => <TaskCard key={t.id} task={t} refresh={refresh} />) : <p className="empty-state">No active tasks. Start one to see Ruby's live status here.</p>}</div></section></>;
}

export function AgentsView({ state, error, refresh, history = false }) {
  const tasks = state?.tasks || [];
  const shown = history ? tasks.filter(t => terminal.has(t.status)) : tasks;
  return <><Header title={history ? 'Task history' : 'Ruby tasks'} /><Status connected={Boolean(state) && !error} error={error} /><div className="canvas-toolbar"><div><span className="eyebrow">PYTHON ASSISTANT · LOCAL BRIDGE</span><p>{history ? 'Completed and stopped tasks reported by Ruby.' : 'Live task states and results from the Python assistant.'}</p></div><button className="ghost-button" onClick={refresh}><RefreshCw size={13} /> Refresh</button></div><Confirmations confirmations={state?.confirmations} refresh={refresh} /><div className="agent-grid wide">{shown.length ? shown.map(t => <TaskCard key={t.id} task={t} refresh={refresh} />) : <p className="empty-state">{state ? 'No tasks yet.' : 'Waiting for the Python bridge to connect.'}</p>}</div></>;
}


export function ChatView({ state, error, refresh, executionMode, setExecutionMode }) {
  const [composeMode, setComposeMode] = useState('chat');
  const makeId = () => window.crypto?.randomUUID?.() || ('ruby-' + Date.now() + '-' + Math.random().toString(16).slice(2));
  const [conversationId, setConversationId] = useState(makeId);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState('');
  const [taskGoal, setTaskGoal] = useState('');

  const submitChat = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending || !window.rubyDesktop?.bridge) return;
    setSending(true);
    setMessage('');
    setMessages(current => [...current, { role: 'user', content: text }]);
    setDraft('');
    try {
      const result = await window.rubyDesktop.bridge.chat({ conversationId, message: text });
      setConversationId(result.conversationId || conversationId);
      setMessages(current => [...current, { role: 'assistant', content: result.response || 'Ruby returned an empty response.' }]);
    } catch (e) {
      setMessages(current => current.slice(0, -1));
      setDraft(text);
      setMessage(e.message || 'Ruby could not answer. Try again.');
    } finally {
      setSending(false);
    }
  };

  const submitTask = async (event) => {
    event.preventDefault();
    if (!taskGoal.trim() || sending || !window.rubyDesktop?.bridge) return;
    setSending(true);
    setMessage('');
    try {
      await window.rubyDesktop.bridge.submitTask({ goal: taskGoal.trim(), executionMode });
      setTaskGoal('');
      setMessage('Task submitted. Track its progress in Agents / Sessions.');
      await refresh();
    } catch (e) {
      setMessage(e.message || 'Could not submit the task.');
    } finally {
      setSending(false);
    }
  };

  const newConversation = () => {
    setConversationId(makeId());
    setMessages([]);
    setDraft('');
    setMessage('');
  };

  return <><Header title="Chat with Ruby" /><Status connected={Boolean(state) && !error} error={error} />
    <div className="chat-surface real-chat">
      <div className="chat-toolbar">
        <div className="chat-tabs" role="tablist" aria-label="Ruby interaction mode">
          <button type="button" role="tab" aria-selected={composeMode === 'chat'} className={composeMode === 'chat' ? 'selected' : ''} onClick={() => { setComposeMode('chat'); setMessage(''); }}>Chat</button>
          <button type="button" role="tab" aria-selected={composeMode === 'task'} className={composeMode === 'task' ? 'selected' : ''} onClick={() => { setComposeMode('task'); setMessage(''); }}>New task</button>
        </div>
        {composeMode === 'chat' && <button type="button" className="ghost-button" onClick={newConversation}><RefreshCw size={13} /> New conversation</button>}
      </div>
      {composeMode === 'chat' ? <>
        <div className="conversation-history" role="log" aria-live="polite">
          {!messages.length ? <div className="chat-empty"><RubyOrb /><h2>Hey, I'm Ruby.</h2><p>Ask a question, talk through an idea, or follow up naturally. Ruby keeps context within this conversation.</p></div> : messages.map((item, index) => <article className={'conversation-message ' + item.role} key={index + '-' + item.role}><span>{item.role === 'user' ? 'YOU' : 'RUBY'}</span><p>{item.content}</p></article>)}
          {sending && <div className="chat-thinking" role="status"><span className="thinking-dot" /> Ruby is thinking…</div>}
        </div>
        <form className="chat-input real-chat-input" onSubmit={submitChat}>
          <textarea aria-label="Message Ruby" maxLength={8000} placeholder="Message Ruby… (Enter to send, Shift+Enter for a new line)" value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
          <button className="chat-send" type="submit" disabled={sending || !draft.trim() || !state || Boolean(error)}><MessageSquare size={15} /> {sending ? 'Thinking…' : 'Send'}</button>
        </form>
      </> : <>
        <div className="task-mode-intro"><RubyOrb /><div><h2>Give Ruby work to do</h2><p>Tasks use the execution engine and remain separate from conversational chat.</p></div></div>
        <form className="chat-input task-compose" onSubmit={submitTask}>
          <div className="task-compose-row"><textarea aria-label="Task for Ruby" maxLength={4000} placeholder="Describe what Ruby should do…" value={taskGoal} onChange={e => setTaskGoal(e.target.value)} /><button className="task-submit" type="submit" disabled={sending || !taskGoal.trim() || !state || Boolean(error)}><Sparkles size={16} /> {sending ? 'Sending…' : 'Start task'}</button></div>
          <ExecutionModeSelector value={executionMode} onChange={setExecutionMode} />
        </form>
      </>}
      {message && <p className="bridge-message" role="status">{message}</p>}
    </div>
  </>;
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
