import { Bot, FolderKanban, History, Home, MessageSquare, Settings, Workflow, TerminalSquare, UserRound, MoreHorizontal } from 'lucide-react';
import { navItems } from '../data';
import { RubyOrb } from './RubyOrb';

const icons = { home: Home, chat: MessageSquare, agents: Bot, tasks: Workflow, projects: FolderKanban, history: History, settings: Settings };

export function Sidebar({ active, setActive }) {
  return (
    <aside className="sidebar">
      <div className="brand"><RubyOrb /><div><strong>Ruby</strong><span>Agent Control Center</span></div></div>
      <div className="sidebar-label">Workspace</div>
      <nav>{navItems.map(([id, label]) => { const Icon = icons[id]; return <button key={id} className={`nav-item ${active === id ? 'active' : ''}`} onClick={() => setActive(id)}><Icon size={17} strokeWidth={1.8} /><span>{label}</span>{id === 'agents' && <span className="nav-count">2</span>}</button>; })}</nav>
      <div className="sidebar-spacer" />
      <div className="operator-card"><div className="operator-icon"><TerminalSquare size={15} /></div><div><span>Operator</span><strong>Live mode ready</strong></div><span className="live-dot" /></div>
      <div className="profile"><div className="avatar"><UserRound size={15} /></div><span>Local workspace</span><MoreHorizontal size={16} /></div>
    </aside>
  );
}
