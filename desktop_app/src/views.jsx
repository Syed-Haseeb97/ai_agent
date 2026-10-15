import { Clock3, FolderKanban, History, MessageSquare, Plus, Settings, Sparkles } from 'lucide-react';
import { mockAgents } from './data';
import { AgentCard } from './components/AgentCard';
import { Header } from './components/Header';
import { RubyOrb } from './components/RubyOrb';

export function HomeView({ setActive }) {
  return <><Header title="Good evening" /><section className="hero-panel"><div><div className="hero-kicker"><Sparkles size={15} /> Agent command center</div><h2>What should Ruby work on?</h2><p>Start a conversation, launch an agent, or pick up where you left off.</p></div><div className="quick-input"><span>Tell Ruby what you want done…</span><button onClick={() => setActive('chat')}><MessageSquare size={17} /> Start</button></div></section><section className="section"><div className="section-heading"><div><span className="eyebrow">LIVE WORK</span><h2>Active sessions</h2></div><button className="text-button" onClick={() => setActive('agents')}>View all →</button></div><div className="agent-grid">{mockAgents.slice(0, 2).map(a => <AgentCard key={a.title} agent={a} />)}</div></section></>;
}

export function AgentsView() {
  return <><Header title="Agents / Sessions" /><div className="canvas-toolbar"><div><span className="eyebrow">AGENT CANVAS</span><p>Monitor independent Ruby runs without taking over your desktop.</p></div><div className="filter-pills"><button className="selected">All</button><button>Working</button><button>Awaiting input</button><button>Completed</button></div></div><div className="agent-grid wide">{mockAgents.map(a => <AgentCard key={a.title} agent={a} />)}</div></>;
}

export function ChatView() {
  return <><Header title="Chat" /><div className="chat-surface"><div className="chat-empty"><RubyOrb /><h2>Talk to Ruby</h2><p>Use chat for quick conversations. Long-running work belongs in an agent session.</p></div><div className="chat-input"><span>Message Ruby…</span><button><MessageSquare size={16} /></button></div></div></>;
}

export function Placeholder({ title, eyebrow, description, icon: Icon }) {
  return <><Header title={title} /><div className="placeholder"><div className="placeholder-icon"><Icon size={23} /></div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{description}</p><button className="new-button"><Plus size={16} /> Create</button></div></>;
}

export const placeholderViews = {
  tasks: { title: 'Tasks', eyebrow: 'AUTOMATIONS', description: 'Scheduled and recurring work will live here. Background execution is intentionally deferred to PR B.', icon: Clock3 },
  projects: { title: 'Projects', eyebrow: 'WORKSPACES', description: 'Manage local folders and project contexts Ruby is allowed to access.', icon: FolderKanban },
  history: { title: 'History', eyebrow: 'PAST RUNS', description: 'Review previous conversations, agent sessions, outputs, and execution logs.', icon: History },
  settings: { title: 'Settings', eyebrow: 'CONFIGURATION', description: 'API keys, model preferences, voice, system permissions, and application behavior.', icon: Settings },
};
