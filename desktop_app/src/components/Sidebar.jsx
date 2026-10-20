import { Bot, FolderKanban, History, Home, MessageSquare, Settings, Workflow, TerminalSquare, UserRound, MoreHorizontal } from 'lucide-react';
import { navItems } from '../data';
import { RubyOrb } from './RubyOrb';

const icons = { home: Home, chat: MessageSquare, agents: Bot, tasks: Workflow, projects: FolderKanban, history: History, settings: Settings };

export function Sidebar({ active, setActive, state }) {
  const activeCount = state?.tasks?.filter(task => !['completed', 'failed', 'cancelled', 'timeout'].includes(task.status)).length;
  return (
    <aside className="sidebar">
      <div className="brand">
        <RubyOrb />
        <div className="brand-wordmark"><strong>Ruby</strong></div>
      </div>
      <div className="sidebar-label">Workspace</div>
      <nav>{navItems.map(([id, label]) => { const Icon = icons[id]; return <button key={id} className={`nav-item ${active === id ? 'active' : ''}`} onClick={() => setActive(id)}><Icon size={17} strokeWidth={1.8} /><span>{label}</span>{id === 'agents' && activeCount > 0 && <span className="nav-count">{activeCount}</span>}</button>; })}</nav>
      <div className="sidebar-spacer" />
      <div className="operator-card"><div className="operator-icon"><TerminalSquare size={15} /></div><div><span>Python assistant</span><strong>{state ? 'Bridge connected' : 'Bridge offline'}</strong></div><span className="live-dot" style={{ opacity: state ? 1 : .25 }} /></div>
      <div className="profile"><div className="avatar"><UserRound size={15} /></div><span>Local workspace</span><MoreHorizontal size={16} /></div>
    </aside>
  );
}
