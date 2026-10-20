import { useCallback, useEffect, useState } from 'react';
import { Home, MessageSquare, Bot, History, Settings, Minus, Square, X } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { RubyOrb } from './components/RubyOrb';
import { HomeView, ChatView, AgentsView, Placeholder, placeholderViews } from './views';
import './styles.css';

const iconByRoute = { home: Home, chat: MessageSquare, agents: Bot, ...Object.fromEntries(Object.entries(placeholderViews).map(([key, value]) => [key, value.icon])) };

function App() {
  const [active, setActive] = useState('home');
  const [isExpanded, setIsExpanded] = useState(false);
  const [bridgeState, setBridgeState] = useState(null);
  const [bridgeError, setBridgeError] = useState('');
  const [runtimeState, setRuntimeState] = useState({ status: 'STARTING', message: 'Starting Ruby…' });
  const refreshBridge = useCallback(async () => {
    if (!window.rubyDesktop?.bridge) { setBridgeError('Open Ruby in the Electron desktop app to connect to the local assistant bridge.'); return; }
    try { setBridgeState(await window.rubyDesktop.bridge.getState()); setBridgeError(''); }
    catch (error) { setBridgeError(error.message || 'Ruby bridge is unavailable.'); }
  }, []);
  const placeholder = placeholderViews[active];
  useEffect(() => {
    window.rubyDesktop?.setExpanded(isExpanded);
  }, [isExpanded]);
  useEffect(() => {
    const runtime = window.rubyDesktop?.runtime;
    if (!runtime) return;
    runtime.getState().then(setRuntimeState).catch(() => {});
    return runtime.onState(setRuntimeState);
  }, []);
  useEffect(() => {
    if (runtimeState.status === 'CONFIGURATION_REQUIRED') setIsExpanded(true);
  }, [runtimeState.status]);
  useEffect(() => {
    refreshBridge();
    const timer = window.setInterval(refreshBridge, 1500);
    return () => window.clearInterval(timer);
  }, [refreshBridge]);
  const view = runtimeState.status === 'CONFIGURATION_REQUIRED' || active === 'settings'
    ? <GeminiSetup state={runtimeState} onConfigured={setRuntimeState} reconfigure={runtimeState.status !== 'CONFIGURATION_REQUIRED'} />
    : runtimeState.status !== 'READY'
      ? <RuntimePanel state={runtimeState} />
      : active === 'home'
    ? <HomeView setActive={setActive} state={bridgeState} error={bridgeError} refresh={refreshBridge} />
    : active === 'chat'
      ? <ChatView state={bridgeState} error={bridgeError} refresh={refreshBridge} />
      : active === 'agents'
        ? <AgentsView state={bridgeState} error={bridgeError} refresh={refreshBridge} />
        : active === 'tasks' || active === 'history'
          ? <AgentsView state={bridgeState} error={bridgeError} refresh={refreshBridge} history={active === 'history'} />
          : <Placeholder {...placeholder} icon={iconByRoute[active]} />;

  return (
    <div className={`app-root ${isExpanded ? 'is-expanded' : 'is-collapsed'}`}>
      <div className={`expanded-layer ${isExpanded ? 'visible' : ''}`} aria-hidden={!isExpanded}>
        <div className="app-shell">
          <Sidebar active={active} setActive={setActive} state={bridgeState} />
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

function RuntimePanel({ state }) {
  return <section className="runtime-panel" role="status" aria-live="polite">
    <div className="runtime-indicator" />
    <span className="eyebrow">RUBY DESKTOP</span>
    <h2>{state.message || 'Starting Ruby…'}</h2>
    <p>{state.error || (state.status === 'WAITING_FOR_BACKEND' ? 'Connecting to the local assistant.' : 'Preparing your assistant for the first task.')}</p>
  </section>;
}

function GeminiSetup({ state, onConfigured, reconfigure = false }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const configure = async () => {
    setBusy(true);
    setMessage('');
    try {
      await window.rubyDesktop.runtime.configureGeminiFromClipboard();
      onConfigured(await window.rubyDesktop.runtime.getState());
    } catch (error) {
      setMessage(error.message || 'Ruby could not configure Gemini.');
    } finally {
      setBusy(false);
    }
  };
  return <section className="runtime-panel setup-panel">
    <div className="runtime-indicator" />
    <span className="eyebrow">GEMINI SETUP</span>
    <h2>{reconfigure ? 'Change Gemini API key' : 'Connect Ruby to Gemini'}</h2>
    <p>{state.error || 'Copy your Gemini API key, then paste it securely through Ruby. Electron reads it directly from the clipboard, stores it encrypted for this Windows account, and clears that clipboard value after setup.'}</p>
    <button className="setup-button" type="button" disabled={busy} onClick={configure}>{busy ? 'Checking key…' : 'Paste key and start Ruby'}</button>
    {(message || state.status === 'INITIALIZING') && <p className="runtime-message" role="status">{message || state.message}</p>}
  </section>;
}

createRoot(document.getElementById('root')).render(<App />);
