import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Home, MessageSquare, Bot, Workflow, FolderKanban, History, Settings, Minus, Square, X } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { RubyOrb } from './components/RubyOrb';
import { HomeView, ChatView, AgentsView, Placeholder, placeholderViews } from './views';
import './styles.css';

const iconByRoute = { home: Home, chat: MessageSquare, agents: Bot, ...Object.fromEntries(Object.entries(placeholderViews).map(([key, value]) => [key, value.icon])) };

function App() {
  const [active, setActive] = useState('home');
  const placeholder = placeholderViews[active];
  const view = active === 'home'
    ? <HomeView setActive={setActive} />
    : active === 'chat'
      ? <ChatView />
      : active === 'agents'
        ? <AgentsView />
        : <Placeholder {...placeholder} icon={iconByRoute[active]} />;

  return <div className="app-shell">
    <Sidebar active={active} setActive={setActive} />
    <main className="main">
      <div className="windowbar"><span>Ruby</span><div><button aria-label="Minimize"><Minus size={14} /></button><button aria-label="Maximize"><Square size={12} /></button><button aria-label="Close"><X size={14} /></button></div></div>
      <div className="content">{view}</div>
      <div className="floating-ruby"><RubyOrb label="Ruby global status indicator" /></div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
