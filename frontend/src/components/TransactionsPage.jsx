import { Fragment, useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useStore } from '../lib/store';
import ThemeToggle from './ThemeToggle';

function fmtDate(s) { return s ? new Date(s).toLocaleString() : '—'; }
function fmtSigned(n) { return `${n > 0 ? '+' : ''}$${Number(n).toFixed(2)}`; }

async function openClientProofInNewTab(txnId) {
  try {
    const res = await fetch(`/api/trades/transactions/${txnId}/proof`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const w = window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
    if (!w) alert('Pop-up blocked. Please allow pop-ups for this site.');
  } catch (e) { alert(`Could not load proof: ${e.message}`); }
}

function CreateTxnModal({ onClose, onCreated, currentBalance, pendingWithdrawalTotal }) {
  const [direction, setDirection] = useState('deposit');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [proof, setProof] = useState(null);
  const [paymentTypes, setPaymentTypes] = useState([]);
  const [paymentTypeId, setPaymentTypeId] = useState('');
  const [fieldValues, setFieldValues] = useState({}); // { label: value } collected from client (withdrawal) or echoed (deposit)
  const [imgUrl, setImgUrl] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Reload payment types whenever the direction changes
  useEffect(() => {
    setPaymentTypeId('');
    setFieldValues({});
    (async () => {
      try { setPaymentTypes(await api.paymentTypes(direction)); }
      catch (e) { /* don't block the form if PT list fails */ }
    })();
  }, [direction]);

  // when a payment type is picked, reset field values to either admin-provided (deposit)
  // or empty (withdrawal — client fills them in)
  useEffect(() => {
    if (!paymentTypeId) { setFieldValues({}); return; }
    const pt = paymentTypes.find((p) => String(p.id) === String(paymentTypeId));
    if (!pt) return;
    const init = {};
    for (const f of (pt.fields || [])) {
      init[f.label] = direction === 'deposit' ? (f.value || '') : '';
    }
    setFieldValues(init);
  }, [paymentTypeId, direction, paymentTypes]);

  // Load preview image for the selected payment type
  useEffect(() => {
    if (!paymentTypeId) { setImgUrl(null); return; }
    const pt = paymentTypes.find((p) => String(p.id) === String(paymentTypeId));
    if (!pt?.has_image) { setImgUrl(null); return; }
    let url;
    (async () => {
      try {
        const res = await fetch(`/api/trades/payment_types/${pt.id}/image`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
        });
        if (!res.ok) return;
        const blob = await res.blob();
        url = URL.createObjectURL(blob);
        setImgUrl(url);
      } catch {}
    })();
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [paymentTypeId, paymentTypes]);

  const selectedPt = paymentTypes.find((p) => String(p.id) === String(paymentTypeId));

  const isDep = direction === 'deposit';
  const availableForWithdrawal = Math.max(0, +(currentBalance - pendingWithdrawalTotal).toFixed(2));
  const numAmt = Number(amount);
  const overWithdraw = !isDep && Number.isFinite(numAmt) && numAmt > availableForWithdrawal;

  const submit = async (e) => {
    e.preventDefault(); setError('');
    if (!Number.isFinite(numAmt) || numAmt <= 0) { setError('Amount must be a positive number'); return; }
    if (overWithdraw) {
      setError(
        pendingWithdrawalTotal > 0
          ? `You can only withdraw up to $${availableForWithdrawal.toFixed(2)} right now. Your balance is $${currentBalance.toFixed(2)} but $${pendingWithdrawalTotal.toFixed(2)} is already in pending withdrawals.`
          : `You can only withdraw up to $${currentBalance.toFixed(2)} (your current balance).`
      );
      return;
    }
    // Build bank_details from the payment type's fields (only for withdrawals).
    // For withdrawals we send whatever the client filled. Required fields: any with a non-empty label.
    let bankDetails = null;
    if (!isDep) {
      const labelsRequired = (selectedPt?.fields || []).map((f) => f.label).filter(Boolean);
      if (labelsRequired.length === 0) {
        setError(`This payment method has no withdrawal fields configured. Ask support to set them up.`);
        return;
      }
      const missing = labelsRequired.filter((lbl) => !(fieldValues[lbl] || '').trim());
      if (missing.length) {
        setError(`Please fill in: ${missing.join(', ')}`);
        return;
      }
      bankDetails = {};
      for (const lbl of labelsRequired) bankDetails[lbl] = (fieldValues[lbl] || '').trim();
    }
    if (paymentTypes.length > 0 && !paymentTypeId) {
      setError('Please pick a payment type');
      return;
    }
    if (selectedPt) {
      const lo = isDep ? selectedPt.deposit_min : selectedPt.withdrawal_min;
      const hi = isDep ? selectedPt.deposit_max : selectedPt.withdrawal_max;
      if (numAmt < lo) { setError(`Minimum ${direction} via ${selectedPt.name} is $${lo.toFixed(2)}`); return; }
      if (numAmt > hi) { setError(`Maximum ${direction} via ${selectedPt.name} is $${hi.toFixed(2)}`); return; }
    }
    setBusy(true);
    try {
      const payload = { direction, amount: numAmt, note: note.trim() };
      if (bankDetails) payload.bank_details = bankDetails;
      if (paymentTypeId) payload.payment_type_id = Number(paymentTypeId);
      const res = await api.createTransaction(payload);
      if (proof) {
        try { await api.uploadTransactionProof(res.id, proof); }
        catch (e) {
          // request was created but proof upload failed — surface but don't roll back
          setError(`Request created (#${res.id}) but proof upload failed: ${e.message}`);
        }
      }
      onCreated?.(res); onClose();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card">
        <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>Create transaction</div>
        <div className="conversion-sub">
          Submit a deposit or withdrawal request. It stays <strong>pending</strong> until an EdgeTrade administrator approves it.
        </div>

        <form className="adjust-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}

          <div className="adjust-row">
            <label>Type</label>
            <div className="txn-direction-toggle">
              <button type="button"
                className={`txn-dir-btn ${isDep ? 'active deposit' : ''}`}
                onClick={() => setDirection('deposit')}>
                + Deposit
              </button>
              <button type="button"
                className={`txn-dir-btn ${!isDep ? 'active withdrawal' : ''}`}
                onClick={() => setDirection('withdrawal')}>
                − Withdrawal
              </button>
            </div>
          </div>

          {paymentTypes.length > 0 && (
            <div className="adjust-row">
              <label>Payment method *</label>
              <select value={paymentTypeId} onChange={(e) => setPaymentTypeId(e.target.value)} required>
                <option value="">— Pick a method —</option>
                {paymentTypes.map((p) => {
                  const lo = isDep ? p.deposit_min : p.withdrawal_min;
                  const hi = isDep ? p.deposit_max : p.withdrawal_max;
                  return <option key={p.id} value={p.id}>{p.name} (${lo} – ${hi})</option>;
                })}
              </select>
              {selectedPt?.instructions && (
                <div style={{ marginTop: 6, padding: 10, background: 'var(--bg-2)', borderRadius: 6, fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5, overflowWrap: 'anywhere' }}>
                  <strong style={{ color: 'var(--text)' }}>Instructions:</strong> {selectedPt.instructions}
                </div>
              )}
              {imgUrl && (
                <img src={imgUrl} alt="payment instructions"
                  style={{ marginTop: 6, maxWidth: '100%', maxHeight: 240, borderRadius: 6, border: '1px solid var(--border)' }} />
              )}
            </div>
          )}

          <div className="adjust-row">
            <label>Amount (USD)</label>
            <input type="number" step="0.01" min="0.01" max="100000"
              placeholder="e.g. 500" value={amount}
              onChange={(e) => setAmount(e.target.value)} required autoFocus />
            <div className="adjust-presets">
              {[50, 100, 500, 1000, 2500, 5000].map((v) => (
                <button key={v} type="button" className="preset" onClick={() => setAmount(String(v))}>${v}</button>
              ))}
            </div>
          </div>

          <div className="adjust-row">
            <label>Note (visible to staff)</label>
            <input type="text"
              placeholder={isDep ? 'e.g. Topping up to continue practicing' : 'e.g. Cashing out my practice winnings'}
              value={note} onChange={(e) => setNote(e.target.value)} required minLength={3} maxLength={255} />
          </div>

          {/* Dynamic fields driven by the selected payment type */}
          {selectedPt && (selectedPt.fields || []).length > 0 && (
            <div className="adjust-row">
              <label>{isDep ? 'Send to (use these details)' : 'Your bank / wallet details *'}</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {selectedPt.fields.map((f) => (
                  <div key={f.label} style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 8, alignItems: 'center' }}>
                    <div style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>{f.label}</div>
                    {isDep ? (
                      <div style={{ fontSize: 13, padding: '8px 12px', background: 'var(--bg-2)', borderRadius: 6, border: '1px solid var(--border)', overflowWrap: 'anywhere' }}>
                        {f.value || <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </div>
                    ) : (
                      <input
                        type="text"
                        placeholder={`Enter your ${f.label.toLowerCase()}`}
                        value={fieldValues[f.label] || ''}
                        onChange={(e) => setFieldValues((s) => ({ ...s, [f.label]: e.target.value }))}
                        required
                        maxLength={512}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="adjust-row">
            <label>{isDep ? 'Payment proof (optional)' : 'Reference / proof (optional)'}</label>
            <input type="file"
              accept=".jpg,.jpeg,.png,.webp,.pdf"
              onChange={(e) => setProof(e.target.files?.[0] || null)} />
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {proof ? `Selected: ${proof.name} (${(proof.size / 1024).toFixed(0)} KB)` : 'JPG / PNG / WebP / PDF, max 5MB'}
            </div>
          </div>

          {!isDep && (
            <div className="adjust-preview" style={{ fontSize: 12 }}>
              Available for withdrawal: <strong style={{ color: overWithdraw ? 'var(--down)' : 'var(--up)' }}>${availableForWithdrawal.toFixed(2)}</strong>
              {pendingWithdrawalTotal > 0 && (
                <span style={{ color: 'var(--text-muted)', marginLeft: 8, fontSize: 11 }}>
                  (balance ${currentBalance.toFixed(2)} − ${pendingWithdrawalTotal.toFixed(2)} pending)
                </span>
              )}
            </div>
          )}
          {amount && Number(amount) > 0 && !overWithdraw && (
            <div className="adjust-preview">
              {isDep
                ? <>Requesting: <strong style={{ color: 'var(--up)' }}>+${Number(amount).toFixed(2)}</strong> deposit</>
                : <>Requesting: <strong style={{ color: 'var(--down)' }}>−${Number(amount).toFixed(2)}</strong> withdrawal</>
              }
            </div>
          )}
          {overWithdraw && (
            <div className="auth-error" style={{ marginTop: 0 }}>
              Amount exceeds available balance (${availableForWithdrawal.toFixed(2)}).
            </div>
          )}

          {(() => {
            const needsMethod = paymentTypes.length > 0 && !paymentTypeId;
            const missingFields = !isDep && selectedPt
              ? (selectedPt.fields || []).map((f) => f.label).filter((l) => l && !(fieldValues[l] || '').trim())
              : [];
            let hint = '';
            if (needsMethod) hint = 'Pick a payment method';
            else if (!amount) hint = 'Enter an amount';
            else if (missingFields.length) hint = `Fill in: ${missingFields.join(', ')}`;
            else if (!note) hint = 'Add a short note for our staff';
            const blocked = busy || !amount || !note || overWithdraw || needsMethod || missingFields.length > 0;
            return (
              <>
                {hint && (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textAlign: 'center' }}>
                    {hint} to submit.
                  </div>
                )}
                <div className="conversion-footer">
                  <button
                    type="submit"
                    className="conversion-reset"
                    disabled={blocked}
                    style={!blocked ? { background: isDep ? 'var(--up)' : 'var(--down)', color: '#0a0d12' } : undefined}
                  >
                    {busy ? '…' : `Request ${isDep ? 'deposit' : 'withdrawal'}`}
                  </button>
                  <button type="button" className="conversion-secondary" onClick={onClose}>Cancel</button>
                </div>
              </>
            );
          })()}
        </form>
      </div>
    </div>
  );
}

function StatusTag({ status }) {
  const cls = status === 'pending' ? 'open' : status === 'approved' ? 'won' : 'lost';
  return <span className={`tag ${cls}`}>{status}</span>;
}

function ClientTxnDetailsModal({ txn, onClose }) {
  const bd = txn.bank_details;
  const isDeposit = txn.amount > 0;
  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card">
        <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>
          Transaction #{txn.id} ·{' '}
          <span className={`tag ${isDeposit ? 'up' : 'down'}`}>{isDeposit ? 'deposit' : 'withdrawal'}</span>{' '}
          <StatusTag status={txn.status} />
        </div>

        <div className="client-card" style={{ marginTop: 12 }}>
          <div className="client-card-title">Amount</div>
          <dl>
            <dt>Amount</dt>
            <dd className="mono" style={{ color: isDeposit ? 'var(--up)' : 'var(--down)' }}>
              {fmtSigned(txn.amount)}
            </dd>
            <dt>Balance before</dt>
            <dd className="mono">{txn.balance_before != null ? `$${txn.balance_before.toFixed(2)}` : '—'}</dd>
            <dt>Balance after</dt>
            <dd className="mono">{txn.balance_after != null ? `$${txn.balance_after.toFixed(2)}` : '—'}</dd>
            <dt>Your note</dt>
            <dd style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{txn.reason}</dd>
            <dt>Requested at</dt>
            <dd className="mono">{fmtDate(txn.created_at)}</dd>
            {txn.processed_at && (
              <>
                <dt>Processed at</dt>
                <dd className="mono">{fmtDate(txn.processed_at)}</dd>
              </>
            )}
          </dl>
        </div>

        {txn.status === 'rejected' && txn.reject_reason && (
          <div className="client-card" style={{ marginTop: 10, borderColor: 'var(--down)' }}>
            <div className="client-card-title" style={{ color: 'var(--down)' }}>Rejection reason</div>
            <div style={{ color: 'var(--text)', fontSize: 13, overflowWrap: 'anywhere', wordBreak: 'break-word', lineHeight: 1.5 }}>
              {txn.reject_reason}
            </div>
          </div>
        )}

        {bd && Object.keys(bd).length > 0 && (
          <div className="client-card" style={{ marginTop: 10 }}>
            <div className="client-card-title">Bank / wallet details (your submission)</div>
            <dl>
              {Object.entries(bd).map(([label, value]) => (
                <Fragment key={label}>
                  <dt>{label.replace(/_/g, ' ')}</dt>
                  <dd className="mono" style={{ overflowWrap: 'anywhere' }}>{value || '—'}</dd>
                </Fragment>
              ))}
            </dl>
          </div>
        )}

        <div className="conversion-footer" style={{ marginTop: 16 }}>
          {txn.proof_image_path && (
            <button type="button" className="admin-btn" onClick={() => openClientProofInNewTab(txn.id)}>
              View payment proof
            </button>
          )}
          <button type="button" className="conversion-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default function TransactionsPage() {
  const user = useStore((s) => s.user);
  const token = useStore((s) => s.token);
  const loadMe = useStore((s) => s.loadMe);
  const [txns, setTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [detailTxn, setDetailTxn] = useState(null);

  useEffect(() => { if (token && !user) loadMe(); }, [token]);

  const load = async () => {
    if (!user) return;
    setLoading(true);
    try {
      setTxns(await api.transactions());
      // also refresh balance — pending requests don't change it but admin may have approved
      try { await loadMe(); } catch {}
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [user?.id]);

  if (!token) { window.location.href = '/'; return null; }

  const approved = txns.filter((t) => t.status === 'approved');
  const deposits = approved.filter((t) => t.amount > 0).reduce((s, t) => s + t.amount, 0);
  const withdrawals = approved.filter((t) => t.amount < 0).reduce((s, t) => s + Math.abs(t.amount), 0);
  const pending = txns.filter((t) => t.status === 'pending').length;

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

      <div style={{ maxWidth: 1400, margin: '32px auto', padding: '0 32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <h1 className="legal-title" style={{ margin: 0 }}>Transactions</h1>
          <button className="admin-btn" onClick={() => setCreateOpen(true)} style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
            + Create txn
          </button>
        </div>
        {user?.account_number && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)', marginBottom: 16 }}>
            Account number: <strong style={{ color: 'var(--accent)' }}>{user.account_number}</strong> · use this number when contacting support
          </div>
        )}
        <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 24 }}>
          Request a deposit or withdrawal. Requests stay <strong>pending</strong> until staff review them.
          Approved requests show their effect on your balance below.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
          <div className="client-card">
            <div className="client-card-title">Current balance</div>
            <div className="mono" style={{ fontSize: 22, color: 'var(--accent)' }}>${user?.balance.toFixed(2)}</div>
          </div>
          <div className="client-card">
            <div className="client-card-title">Total deposits</div>
            <div className="mono" style={{ fontSize: 22, color: 'var(--up)' }}>${deposits.toFixed(2)}</div>
          </div>
          <div className="client-card">
            <div className="client-card-title">Total withdrawals</div>
            <div className="mono" style={{ fontSize: 22, color: 'var(--down)' }}>${withdrawals.toFixed(2)}</div>
          </div>
          <div className="client-card">
            <div className="client-card-title">Pending</div>
            <div className="mono" style={{ fontSize: 22, color: pending > 0 ? 'var(--accent)' : 'var(--text-muted)' }}>{pending}</div>
          </div>
        </div>

        {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="admin-table-wrap" style={{ background: 'var(--bg-1)', border: '1px solid var(--border)', borderRadius: 8 }}>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Requested</th>
                <th>Type</th>
                <th>Method</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
                <th>Status</th>
                <th>Note</th>
                <th>Proof</th>
                <th>Processed</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={9} style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>Loading…</td></tr>}
              {!loading && txns.length === 0 && (
                <tr><td colSpan={9} style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
                  No transactions yet. Click <strong>Create txn</strong> to submit your first request.
                </td></tr>
              )}
              {txns.map((t) => (
                <tr key={t.id}>
                  <td className="mono">{fmtDate(t.created_at)}</td>
                  <td><span className={`tag ${t.amount > 0 ? 'up' : 'down'}`}>{t.amount > 0 ? 'deposit' : 'withdrawal'}</span></td>
                  <td>{t.payment_type_name || <span style={{ color: 'var(--text-muted)' }}>—</span>}</td>
                  <td className="mono" style={{ textAlign: 'right', color: t.amount > 0 ? 'var(--up)' : 'var(--down)' }}>{fmtSigned(t.amount)}</td>
                  <td>
                    <StatusTag status={t.status} />
                    {t.status === 'rejected' && (
                      <button
                        type="button"
                        className="admin-wa"
                        style={{ background: 'transparent', border: 'none', padding: 0, marginLeft: 6, fontSize: 11, color: 'var(--down)' }}
                        onClick={() => setDetailTxn(t)}
                        title="See why this was rejected"
                      >
                        why?
                      </button>
                    )}
                  </td>
                  <td className="cell-wrap">{t.reason}</td>
                  <td>
                    {t.proof_image_path ? (
                      <button className="admin-wa" style={{ background: 'transparent', border: 'none', padding: 0 }} onClick={() => openClientProofInNewTab(t.id)}>View</button>
                    ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                  </td>
                  <td className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {t.processed_at ? fmtDate(t.processed_at) : '—'}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="admin-wa"
                      style={{ background: 'transparent', border: 'none', padding: 0 }}
                      onClick={() => setDetailTxn(t)}
                    >
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {createOpen && (
        <CreateTxnModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => load()}
          currentBalance={user?.balance ?? 0}
          pendingWithdrawalTotal={txns.filter((t) => t.status === 'pending' && t.amount < 0).reduce((s, t) => s + Math.abs(t.amount), 0)}
        />
      )}
      {detailTxn && (
        <ClientTxnDetailsModal
          txn={detailTxn}
          onClose={() => setDetailTxn(null)}
        />
      )}
    </div>
  );
}
