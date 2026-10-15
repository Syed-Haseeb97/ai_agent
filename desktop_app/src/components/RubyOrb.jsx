export function RubyOrb({ label = 'Ruby status: working', onClick }) {
  return (
    <button
      type="button"
      className="ruby-trigger"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      <span className="ruby-orb-wrap" aria-hidden="true">
        <span className="ruby-orb"><span className="ruby-eye left" /><span className="ruby-eye right" /></span>
        <span className="ruby-status-dot" />
      </span>
    </button>
  );
}
