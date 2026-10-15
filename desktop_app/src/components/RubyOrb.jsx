export function RubyOrb({ label = 'Ruby status: working' }) {
  return (
    <div className="ruby-orb-wrap" aria-label={label}>
      <div className="ruby-orb"><span className="ruby-eye left" /><span className="ruby-eye right" /></div>
      <span className="ruby-status-dot" />
    </div>
  );
}
