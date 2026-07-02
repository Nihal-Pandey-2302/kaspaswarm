import React, { useState, useEffect, useRef } from 'react';

// Agent Treasury Vault — surfaces the on-chain spend-policy covenant and lets the
// user run the live proof (accept / block / block / co-sign) on testnet-10.
const OUTCOME = {
  accepted: { label: 'ACCEPTED', color: '#00ff88', bg: 'rgba(0,255,136,0.12)', border: 'rgba(0,255,136,0.35)' },
  blocked: { label: 'BLOCKED', color: '#ffaa33', bg: 'rgba(255,170,51,0.12)', border: 'rgba(255,170,51,0.35)' },
  pending: { label: '…', color: '#9aa4b2', bg: 'rgba(255,255,255,0.06)', border: 'rgba(255,255,255,0.15)' },
  unexpected_accept: { label: '⚠ ACCEPTED', color: '#ff6b6b', bg: 'rgba(255,107,107,0.12)', border: 'rgba(255,107,107,0.35)' },
  unexpected_fail: { label: '⚠ FAILED', color: '#ff6b6b', bg: 'rgba(255,107,107,0.12)', border: 'rgba(255,107,107,0.35)' },
};

const short = (a) => (a && a.length > 22 ? `${a.slice(0, 14)}…${a.slice(-6)}` : a);

export default function CovenantPanel() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);

  const fetchStatus = async () => {
    try {
      const r = await fetch('/api/covenant/status');
      const d = await r.json();
      setStatus(d);
      return d;
    } catch {
      return null;
    }
  };

  useEffect(() => {
    fetchStatus();
    return () => clearInterval(pollRef.current);
  }, []);

  // Poll while a run is in progress.
  useEffect(() => {
    if (status?.running) {
      clearInterval(pollRef.current);
      pollRef.current = setInterval(fetchStatus, 2500);
    } else {
      clearInterval(pollRef.current);
    }
    return () => clearInterval(pollRef.current);
  }, [status?.running]);

  const runProof = async () => {
    setBusy(true);
    try {
      await fetch('/api/covenant/run', { method: 'POST' });
      await new Promise((r) => setTimeout(r, 500));
      await fetchStatus();
    } finally {
      setBusy(false);
    }
  };

  if (!status) return null;

  if (!status.configured) {
    return (
      <div style={styles.card} className="ks-card">
        <div style={styles.header}>🛡️ Treasury Vault</div>
        <div style={styles.muted}>On-chain covenant not configured (live mode + funded coordinator required).</div>
      </div>
    );
  }

  const result = status.result;
  const acts = result?.acts || [];
  const running = status.running;

  return (
    <div style={styles.card} className="ks-card">
      <div style={styles.header}>
        🛡️ Agent Treasury Vault
        <span style={styles.tag}>on-chain governance</span>
      </div>
      <div style={styles.sub}>
        A KIP-10 covenant Kaspa itself enforces: the agent may auto-pay a pinned payee up to a
        cap; larger or off-policy spends need human co-sign.
      </div>

      <div style={styles.kv}><span style={styles.k}>Per-tx cap</span><span style={styles.v}>{status.cap_kas} KAS</span></div>
      <div style={styles.kv}>
        <span style={styles.k}>Vault</span>
        <a style={styles.link} href={status.vault_explorer} target="_blank" rel="noreferrer">{short(status.vault_address)}</a>
      </div>
      <div style={styles.kv}><span style={styles.k}>Network</span><span style={styles.v}>{status.network}</span></div>

      <button
        onClick={runProof}
        disabled={busy || running}
        className="ks-btn"
        style={{ ...styles.btn, opacity: busy || running ? 0.6 : 1 }}
      >
        {running ? '⏳ Proving on-chain…' : '▶ Run on-chain proof'}
      </button>

      {acts.length > 0 && (
        <div style={styles.acts}>
          {acts.map((a) => {
            const o = OUTCOME[a.outcome] || OUTCOME.pending;
            return (
              <div key={a.n} style={styles.act}>
                <div style={styles.actTop}>
                  <span style={styles.actLabel}>{a.label}</span>
                  <span style={{ ...styles.badge, color: o.color, background: o.bg, borderColor: o.border }}>{o.label}</span>
                </div>
                <div style={styles.actMeta}>
                  <span style={styles.expect}>expect: {a.expect === 'accept' ? 'ACCEPT' : 'BLOCK'}</span>
                  {a.txid && (
                    <a style={styles.txlink} href={a.explorer} target="_blank" rel="noreferrer">tx ↗</a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {status.error && <div style={styles.err}>⚠ {status.error}</div>}
    </div>
  );
}

const styles = {
  card: {
    background: 'rgba(17, 19, 24, 0.92)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255,255,255,0.10)',
    borderRadius: '14px',
    padding: '16px',
    color: '#f3f5f8',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    width: '100%',
    boxSizing: 'border-box',
    boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
    marginBottom: '14px',
    flexShrink: 0,
  },
  header: { fontSize: '13px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' },
  tag: {
    fontSize: '8px', fontWeight: 700, letterSpacing: '0.5px', textTransform: 'uppercase',
    color: '#4f9eff', background: 'rgba(79,158,255,0.12)', border: '1px solid rgba(79,158,255,0.35)',
    borderRadius: '20px', padding: '2px 7px',
  },
  sub: { fontSize: '11px', lineHeight: 1.5, color: '#9aa4b2', marginBottom: '12px' },
  kv: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', fontSize: '12px' },
  k: { color: '#7d8794' },
  v: { color: '#f3f5f8', fontFamily: 'monospace', fontWeight: 700 },
  link: { color: '#4f9eff', fontFamily: 'monospace', fontSize: '11px', textDecoration: 'none' },
  btn: {
    width: '100%', marginTop: '10px', marginBottom: '4px', padding: '10px',
    borderRadius: '10px', border: '1px solid rgba(0,255,136,0.4)', background: 'rgba(0,255,136,0.12)',
    color: '#00ff88', fontWeight: 700, fontSize: '12px', cursor: 'pointer',
  },
  acts: { marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' },
  act: { background: 'rgba(0,0,0,0.25)', borderRadius: '9px', padding: '9px 10px' },
  actTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' },
  actLabel: { fontSize: '11px', color: '#dbe2ea', lineHeight: 1.35 },
  badge: {
    fontSize: '8px', fontWeight: 800, letterSpacing: '0.5px', borderRadius: '20px',
    padding: '2px 7px', border: '1px solid', whiteSpace: 'nowrap',
  },
  actMeta: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '5px' },
  expect: { fontSize: '9px', color: '#7d8794', textTransform: 'uppercase', letterSpacing: '0.5px' },
  txlink: { fontSize: '10px', color: '#4f9eff', textDecoration: 'none', fontWeight: 700 },
  muted: { fontSize: '11px', color: '#7d8794', lineHeight: 1.5 },
  err: { marginTop: '8px', fontSize: '10px', color: '#ff6b6b' },
};
