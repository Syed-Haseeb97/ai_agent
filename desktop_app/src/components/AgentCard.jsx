import { CheckCircle2, MoreHorizontal, Play, Sparkles, Square } from 'lucide-react';

export function AgentCard({ agent }) {
  const working = agent.state === 'Working';
  const waiting = agent.state === 'Awaiting Input';
  return <article className={`agent-card ${agent.state.toLowerCase().replaceAll(' ', '-')}`}>
    <div className="agent-card-top"><div className="agent-icon"><Sparkles size={16} /></div><span className="state-badge"><span className="state-dot" />{agent.state}</span><button className="icon-button"><MoreHorizontal size={17} /></button></div>
    <h3>{agent.title}</h3><p>{agent.detail}</p>
    <div className="progress-track"><div className="progress-fill" style={{ width: `${agent.progress}%` }} /></div>
    <div className="agent-footer"><span>{working ? 'Agent is working' : waiting ? 'Needs your decision' : 'Verified result'}</span>{working && <button className="stop-button"><Square size={12} fill="currentColor" /> Stop</button>}{waiting && <button className="resume-button"><Play size={12} fill="currentColor" /> Review</button>}{!working && !waiting && <CheckCircle2 size={15} />}</div>
  </article>;
}
