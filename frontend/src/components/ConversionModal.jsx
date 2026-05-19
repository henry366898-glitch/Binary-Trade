import { useEffect } from 'react';
import { waLink, openAcademyCta } from '../lib/leadCta';

function StewartsCard({ surface, large = false }) {
  const onClick = (e) => {
    e.preventDefault();
    openAcademyCta(surface);
  };
  return (
    <a
      href={waLink(surface)}
      onClick={onClick}
      className={`academy-card ${large ? 'academy-card-lg' : ''}`}
      target="_blank"
      rel="noopener noreferrer"
    >
      <div className="academy-logo">S</div>
      <div className="academy-name">Stewarts Academy</div>
      <div className="academy-tagline">Abu Dhabi&apos;s licensed forex &amp; gold trading school</div>
      <div className="academy-meta">Salam HQ, Abu Dhabi · Licensed since 2024</div>
      <div className="academy-cta">Book a free consultation →</div>
    </a>
  );
}

export default function ConversionModal({ variant, onClose, onReset, canReset, resetsUsed, resetsMax }) {
  // close on Escape (only when close is allowed)
  useEffect(() => {
    if (!onClose) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const isZero = variant === 'zero';

  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className={`conversion-card ${isZero ? 'conversion-card-zero' : ''}`}>
        {onClose && (
          <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        )}

        {isZero ? (
          <>
            <div className="conversion-heading">Your $10,000 practice balance is gone</div>
            <div className="conversion-sub">
              That&apos;s how trading often goes without training. Most retail traders lose money learning the hard way.
              You can talk to a licensed UAE forex school — no obligation — or reset and try again.
            </div>
          </>
        ) : (
          <>
            <div className="conversion-heading">Your practice balance is running low</div>
            <div className="conversion-sub">
              You&apos;re not alone — most retail traders lose money. If you&apos;d like to learn properly, we work with a
              licensed forex training school in Abu Dhabi you can talk to. No obligation.
            </div>
          </>
        )}

        <div className="academy-row">
          <StewartsCard surface={isZero ? 'modal_zero' : 'modal_low'} large={isZero} />
        </div>

        {isZero ? (
          <div className="conversion-footer">
            {canReset ? (
              <>
                <button className="conversion-reset" onClick={onReset}>
                  Reset balance ({resetsUsed}/{resetsMax} used)
                </button>
                <button className="conversion-secondary" onClick={onClose}>Close</button>
              </>
            ) : (
              <div className="conversion-no-reset">
                You&apos;ve used all {resetsMax} balance resets. If you want to keep learning, talking to a licensed school is the next step.
                <button className="conversion-secondary" onClick={onClose}>Close anyway</button>
              </div>
            )}
          </div>
        ) : (
          <div className="conversion-footer-low">
            Or continue practicing — we&apos;ll be here when you&apos;re ready.
          </div>
        )}
      </div>
    </div>
  );
}
