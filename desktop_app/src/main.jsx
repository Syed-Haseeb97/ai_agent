import { useEffect, useState } from 'react';
import { Home, MessageSquare, Bot, Workflow, FolderKanban, History, Settings, Minus, Square, X } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { RubyOrb } from './components/RubyOrb';
import { HomeView, ChatView, AgentsView, Placeholder, placeholderViews } from './views';
import './styles.css';

const iconByRoute = { home: Home, chat: MessageSquare, agents: Bot, ...Object.fromEntries(Object.entries(placeholderViews).map(([key, value]) => [key, value.icon])) };

function App() {
  const [active, setActive] = useState('home');
  const [isExpanded, setIsExpanded] = useState(false);
  const placeholder = placeholderViews[active];
  useEffect(() => {
    window.rubyDesktop?.setExpanded(isExpanded);
  }, [isExpanded]);
  const view = active === 'home'
    ? <HomeView setActive={setActive} />
    : active === 'chat'
      ? <ChatView />
      : active === 'agents'
        ? <AgentsView />
        : <Placeholder {...placeholder} icon={iconByRoute[active]} />;

  return (
    <div className={`app-root ${isExpanded ? 'is-expanded' : 'is-collapsed'}`}>
      <div className={`expanded-layer ${isExpanded ? 'visible' : ''}`} aria-hidden={!isExpanded}>
        <div className="app-shell">
          <Sidebar active={active} setActive={setActive} />
          <main className="main">
            <div className="windowbar"><span>Ruby</span><div><button aria-label="Minimize" onClick={() => window.rubyDesktop?.minimize()}><Minus size={14} /></button><button aria-label="Maximize" onClick={() => window.rubyDesktop?.toggleMaximize()}><Square size={12} /></button><button aria-label="Close" onClick={() => window.rubyDesktop ? window.rubyDesktop.close() : setIsExpanded(false)}><X size={14} /></button></div></div>
            <div className="content">{view}</div>
            <div className="floating-ruby"><RubyOrb label="Collapse Ruby" onClick={() => setIsExpanded(false)} /></div>
          </main>
        </div>
      </div>
      <div className={`collapsed-layer ${isExpanded ? 'hidden' : ''}`}>
        <RubyOrb label="Open Ruby Agent Control Center" onClick={() => setIsExpanded(true)} />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
