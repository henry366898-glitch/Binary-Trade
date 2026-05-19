import { useState } from 'react';
import { api } from '../lib/api';
import { useStore } from '../lib/store';
import ThemeToggle from './ThemeToggle';

const COUNTRIES = [
  { name: 'UAE',          dial: '+971' },
  { name: 'India',        dial: '+91'  },
  { name: 'Pakistan',     dial: '+92'  },
  { name: 'Saudi Arabia', dial: '+966' },
  { name: 'Kuwait',       dial: '+965' },
  { name: 'Bahrain',      dial: '+973' },
  { name: 'Oman',         dial: '+968' },
  { name: 'Qatar',        dial: '+974' },
  { name: 'Other',        dial: '+'    },
];

const REFERRAL_SOURCES = ['Google', 'Facebook', 'Instagram', 'TikTok', 'Friend', 'Other'];

export default function AuthScreen() {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  // register-only fields
  const [fullName, setFullName] = useState('');
  const [country, setCountry] = useState('UAE');
  const [dialCode, setDialCode] = useState('+971');
  const [phoneLocal, setPhoneLocal] = useState('');
  const [referral, setReferral] = useState('');
  const [marketingOk, setMarketingOk] = useState(false);

  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const setUser = useStore((s) => s.setUser);

  const onCountryChange = (c) => {
    setCountry(c);
    const match = COUNTRIES.find((x) => x.name === c);
    if (match && match.dial !== '+') setDialCode(match.dial);
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      if (mode === 'login') {
        const res = await api.login({ email, password });
        setUser(res.user, res.access_token);
      } else {
        const phone = `${dialCode}${phoneLocal.replace(/[^\d]/g, '')}`;
        const res = await api.register({
          email,
          password,
          full_name: fullName,
          phone_number: phone,
          country,
          referral_source: referral || null,
          agreed_to_marketing: marketingOk,
        });
        setUser(res.user, res.access_token);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <div style={{ position: 'fixed', top: 16, right: 16 }}>
        <ThemeToggle />
      </div>
      <div className="auth-card">
        <div className="brand" style={{ marginBottom: 20 }}>
          <span className="dot"></span>
          EDGETRADE
          <span className="practice">PRACTICE</span>
        </div>
        <div className="auth-title">{mode === 'login' ? 'Welcome back' : 'Create account'}</div>
        <div className="auth-sub">
          {mode === 'login'
            ? 'Sign in to access the trading simulator'
            : 'Start with $10,000 in virtual funds'}
        </div>
        <form className="auth-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}

          {mode === 'register' && (
            <input
              type="text"
              placeholder="Full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              minLength={2}
              autoComplete="name"
            />
          )}

          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />

          {mode === 'register' && (
            <>
              <div className="phone-row">
                <select
                  className="dial-select"
                  value={dialCode}
                  onChange={(e) => setDialCode(e.target.value)}
                  aria-label="Country code"
                >
                  {COUNTRIES.filter((c) => c.dial !== '+').map((c) => (
                    <option key={c.name} value={c.dial}>{c.dial}</option>
                  ))}
                </select>
                <input
                  type="tel"
                  inputMode="numeric"
                  placeholder="Phone number"
                  value={phoneLocal}
                  onChange={(e) => setPhoneLocal(e.target.value)}
                  required
                  minLength={6}
                  autoComplete="tel-national"
                />
              </div>

              <select
                className="country-select"
                value={country}
                onChange={(e) => onCountryChange(e.target.value)}
                required
              >
                {COUNTRIES.map((c) => (
                  <option key={c.name} value={c.name}>{c.name}</option>
                ))}
              </select>
            </>
          )}

          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />

          {mode === 'register' && (
            <>
              <select
                className="referral-select"
                value={referral}
                onChange={(e) => setReferral(e.target.value)}
              >
                <option value="">How did you hear about us? (optional)</option>
                {REFERRAL_SOURCES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={marketingOk}
                  onChange={(e) => setMarketingOk(e.target.checked)}
                />
                <span>I agree to receive trading tips via email and WhatsApp. You can unsubscribe at any time.</span>
              </label>
            </>
          )}

          <button type="submit" className="auth-submit" disabled={busy}>
            {busy ? '…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
        <div className="auth-switch">
          {mode === 'login' ? 'No account? ' : 'Already have one? '}
          <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>
            {mode === 'login' ? 'Register' : 'Sign in'}
          </button>
        </div>
        <div className="disclaimer">
          <strong>PRACTICE SIMULATION.</strong> No real money is involved.
          Real binary options trading is high-risk: 74–89% of retail traders lose money.
          This platform is designed to demonstrate trading mechanics for learning.
        </div>
      </div>
    </div>
  );
}
