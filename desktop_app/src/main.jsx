import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Bot,
  CheckCircle2,
  Clock3,
  FolderKanban,
  History,
  Home,
  MessageSquare,
  MoreHorizontal,
  Play,
  Plus,
  Settings,
  Sparkles,
  Square,
  TerminalSquare,
  UserRound,
  Workflow,
} from 'lucide-react';
import './styles.css';

const navItems = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'agents', label: 'Agents / Sessions', icon: Bot },
  { id: 'tasks', label: 'Tasks', icon: Workflow },
  { id: 'projects', label: 'Projects', icon: FolderKanban },
  { id: 'history', label: 'History', icon: History },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const mockAgents = [
  { title: 'Researching laptops', detail: 'Comparing current options under ₹70k', state: 'Working', progress: 68 },
  { title: 'Cleaning Downloads', detail: 'Planning a safe file organization', state: 'Awaiting Input', progress: 42 },
  { title: 'Assignment report', detail: 'Final document generated and verified', state: 'Completed', progress: 100 },
];

function RubyOrb() {
  return (
    <div className="ruby-orb-wrap" aria-label="Ruby status: working">
      <div className="ruby-orb"><span className="ruby-eye left" /><span className="ruby-eye right" /></div>
      <span className="ruby-status-dot" />
    </div>
  );
}

function Sidebar({ active, setActive }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <RubyOrb />
        <div><strong>Ruby</strong><span>Agent Control Center</span></div>
      </div>
      <div className="sidebar-label">Workspace</div>
      <nav>
        {navItems.map(({ id, label, icon: Icon }) => (
          <button key={id} className={`nav-item ${active === id ? 'active' : ''}`} onClick={() => setActive(id)}>
            <Icon size={17} strokeWidth={1.8} />
            <span>{label}</span>
            {id === 'agents' && <span className="nav-count">2</span>}
          </button>
        ))}
      </nav>
      <div className="sidebar-spacer" />
      <div className="operator-card">
        <div className="operator-icon"><TerminalSquare size={15} /></div>
        <div><span>Operator</span><strong>Live mode ready</strong></div>
        <span className="live-dot" />
      </div>
      <div className="profile"><div className="avatar"><UserRound size={15} /></div><span>Local workspace</span><MoreHorizontal size={16} /></div>
    </aside>
  );
}

function AgentCard({ agent }) {
  const working = agent.state === 'Working';
  const waiting = agent.state === 'Awaiting Input';
  return (
    <article className={`agent-card ${agent.state.toLowerCase().replaceAll(' ', '-')}`}>
      <div className="agent-card-top">
        <div className="agent-icon"><Sparkles size={16} /></div>
        <span className="state-badge"><span className="state-dot" />{agent.state}</span>
        <button className="icon-button"><MoreHorizontal size={17} /></button>
      </div>
      <h3>{agent.title}</h3>
      <p>{agent.detail}</p>
      <div className="progress-track"><div className="progress-fill" style={{ width: `${agent.progress}%` }} /></div>
      <div className="agent-footer">
        <span>{working ? 'Agent is working' : waiting ? 'Needs your decision' : 'Verified result'}</span>
        {working && <button className="stop-button"><Square size={12} fill="currentColor" /> Stop</button>}
        {waiting && <button className="resume-button"><Play size={12} fill="currentColor" /> Review</button>}
        {!working && !waiting && <CheckCircle2 size={15} />}
      </div>
    </article>
  );
}

function Header({ title }) {
  return <header className="header"><div><span className="eyebrow">RUBY WORKSPACE</span><h1>{title}</h1></div><div className="header-actions"><button className="ghost-button">⌘ K</button><button className="new-button"><Plus size={16} /> New agent</button></div></header>;
}

function HomeView({ setActive }) {
  return <>
    <Header title="Good evening" />
    <section className="hero-panel">
      <div><div className="hero-kicker"><Sparkles size={15} /> Agent command center</div><h2>What should Ruby work on?</h2><p>Start a conversation, launch an agent, or pick up where you left off.</p></div>
      <div className="quick-input"><span>Tell Ruby what you want done…</span><button onClick={() => setActive('chat')}><MessageSquare size={17} /> Start</button></div>
    </section>
    <section className="section"><div className="section-heading"><div><span className="eyebrow">LIVE WORK</span><h2>Active sessions</h2></div><button className="text-button" onClick={() => setActive('agents')}>View all →</button></div><div className="agent-grid">{mockAgents.slice(0, 2).map(a => <AgentCard key={a.title} agent={a} />)}</div></section>
  </>;
}

function AgentsView() {
  return <><Header title="Agents / Sessions" /><div className="canvas-toolbar"><div><span className="eyebrow">AGENT CANVAS</span><p>Monitor independent Ruby runs without taking over your desktop.</p></div><div className="filter-pills"><button className="selected">All</button><button>Working</button><button>Awaiting input</button><button>Completed</button></div></div><div className="agent-grid wide">{mockAgents.map(a => <AgentCard key={a.title} agent={a} />)}</div></>;
}

function Placeholder({ title, eyebrow, description, icon: Icon }) {
  return <><Header title={title} /><div className="placeholder"><div className="placeholder-icon"><Icon size={23} /></div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{description}</p><button className="new-button"><Plus size={16} /> Create</button></div></>;
}

function ChatView() { return <><Header title="Chat" /><div className="chat-surface"><div className="chat-empty"><RubyOrb /><h2>Talk to Ruby</h2><p>Use chat for quick conversations. Long-running work belongs in an agent session.</p></div><div className="chat-input"><span>Message Ruby…</span><button><MessageSquare size={16} /></button></div></div></>; }

function App() {
  const [active, setActive] = useState('home');
  const content = {
    home: <HomeView setActive={setActive} />,
    chat: <ChatView />,
    agents: <AgentsView />,
    tasks: <Placeholder title="Tasks" eyebrow="AUTOMATIONS" description="Scheduled and recurring work will live here. Background execution is intentionally deferred to PR B." icon={Clock3} />,
    projects: <Placeholder title="Projects" eyebrow="WORKSPACES" description="Manage local folders and project contexts Ruby is allowed to access." icon={FolderKanban} />,
    history: <Placeholder title="History" eyebrow="PAST RUNS" description="Review previous conversations, agent sessions, outputs, and execution logs." icon={History} />,
    settings: <Placeholder title="Settings" eyebrow="CONFIGURATION" description="API keys, model preferences, voice, system permissions, and application behavior." icon={Settings} />,
  };
  return <div className="app-shell"><Sidebar active={active} setActive={setActive} /><main className="main"><div className="windowbar"><span>Ruby</span><div><button>—</button><button>□</button><button>×</button></div></div><div className="content">{content[active]}</div><div className="floating-ruby"><RubyOrb /></div></main></div>;
}

createRoot(document.getElementById('root')).render(<App />);
