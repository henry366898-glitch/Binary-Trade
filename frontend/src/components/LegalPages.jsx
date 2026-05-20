import ThemeToggle from './ThemeToggle';

function Shell({ title, children }) {
  return (
    <div className="legal-screen">
      <div className="legal-topbar">
        <a className="legal-back" href="/">← Back to EdgeTrade</a>
        <div className="brand" style={{ fontSize: 14 }}>
          <span className="dot"></span>
          EDGETRADE
          <span className="practice">PRACTICE</span>
        </div>
        <ThemeToggle />
      </div>
      <div className="legal-card">
        <h1 className="legal-title">{title}</h1>
        {children}
      </div>
      <div className="legal-footer-links">
        <a href="/disclaimer">Disclaimer</a>
        <span>·</span>
        <a href="/privacy">Privacy</a>
        <span>·</span>
        <a href="/terms">Terms</a>
      </div>
    </div>
  );
}

export function Disclaimer() {
  return (
    <Shell title="Risk Disclosure & Disclaimer">
      

      <h2>About binary options</h2>
      <p>
        Real binary options trading is a high-risk activity. Multiple regulators have
        documented that <strong>74–89% of retail traders lose money</strong>. Binary
        options are <strong>banned for retail clients</strong> in the European Union,
        United Kingdom, United States, Australia, and several other jurisdictions for
        precisely this reason.
      </p>
      <p>
        The 85% payout structure used on this platform is illustrative. It produces a
        negative expected return for a 50/50 win rate — a trader needs a win rate above
        approximately 54% just to break even, which is statistically very difficult to
        sustain on short-timeframe price movements that are essentially random.
      </p>

      <h2>No guarantee of real-world results</h2>
      <p>
        Past or simulated performance — including profits, win rates, or strategies that
        appear to work inside this simulator — is not indicative of future results in
        real markets. Real trading involves slippage, spreads, broker risk, emotional
        pressure, and capital at risk that this simulator does not model.
      </p>

      <h2>About academy referrals</h2>
      <p>
        EdgeTrade may refer users to independent third-party trading education providers,
        including Stewarts Academy. These are <strong>separate businesses</strong> and
        EdgeTrade does not endorse, guarantee, or take responsibility for the courses,
        outcomes, or representations made by any referred academy. We do not represent
        that any course or training will result in profitable trading.
      </p>

      <h2>Eligibility &amp; use</h2>
      <p>
        You must be at least 18 years old to use this platform. Do not use this platform
        from any jurisdiction where access to a practice trading simulator is unlawful.
      </p>

      <p className="legal-meta">Last updated: 2026-05-15</p>
    </Shell>
  );
}

export function Privacy() {
  return (
    <Shell title="Privacy Notice">
      <p className="legal-meta">
        Placeholder — a full privacy policy is in progress. The summary below describes
        what data EdgeTrade currently collects and why.
      </p>

      <h2>What we collect when you register</h2>
      <ul>
        <li>Full name</li>
        <li>Email address</li>
        <li>Phone number (with country code)</li>
        <li>Country of residence</li>
        <li>How you heard about us (optional)</li>
        <li>Marketing-consent preference</li>
      </ul>

      <h2>What we collect as you use the platform</h2>
      <ul>
        <li>Trades you place (symbol, amount, direction, outcome)</li>
        <li>Account balance and balance-reset history</li>
        <li>Clicks on academy referral CTAs (which surface, when, your balance at that moment)</li>
      </ul>

      <h2>Why we collect it</h2>
      <ul>
        <li>To operate your account and the practice trading simulator.</li>
        <li>
          If you tick the marketing-consent box at signup, to contact you with trading
          tips via email and WhatsApp, and to share your contact details with our
          partner academy (Stewarts Academy) for educational follow-up.
        </li>
        <li>To understand which parts of the platform users engage with, in aggregate.</li>
      </ul>

      <h2>Your rights</h2>
      <p>
        You can withdraw marketing consent at any time. You can request that we delete
        your account and personal data. Contact us at <a href="mailto:hello@edgetrade.local">hello@edgetrade.local</a>.
      </p>

      <p className="legal-meta">Last updated: 2026-05-15</p>
    </Shell>
  );
}

export function Terms() {
  return (
    <Shell title="Terms of Use">
      <p className="legal-meta">
        Placeholder — full terms are in progress. Use of this platform is currently
        subject to the practice-simulation framing described below.
      </p>

      <h2>Practice only</h2>
      <p>
        EdgeTrade is a virtual trading simulator. No real money is deposited, traded,
        withdrawn, or held on this platform. You may not use the platform to attempt
        to trade real money or to misrepresent the platform as a real trading venue.
      </p>

      <h2>Acceptable use</h2>
      <p>
        Do not attempt to abuse, scrape, or disrupt the platform; do not register on
        behalf of someone else; do not use the platform from any jurisdiction where
        access to a practice trading simulator is unlawful.
      </p>

      <h2>Academy referrals</h2>
      <p>
        Clicking an academy referral CTA takes you to a third-party communication
        channel (WhatsApp) operated by an independent business. EdgeTrade is not
        responsible for the academy&apos;s services, claims, or outcomes.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms. Continued use after an update constitutes
        acceptance.
      </p>

      <p className="legal-meta">Last updated: 2026-05-15</p>
    </Shell>
  );
}
