import { Plus } from 'lucide-react';

export function Header({ title }) {
  return <header className="header"><div><span className="eyebrow">RUBY WORKSPACE</span><h1>{title}</h1></div><div className="header-actions"><button className="ghost-button">⌘ K</button><button className="new-button"><Plus size={16} /> New agent</button></div></header>;
}
