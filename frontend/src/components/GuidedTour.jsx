import React, { useState, useEffect } from 'react';

// A lightweight, dismissible first-visit tour so a judge understands the demo in
// ~30 seconds. Shows once (localStorage), re-openable via the ❓ button in App.
const STEPS = [
  {
    icon: '🐝',
    title: 'A live agent economy on Kaspa',
    body: 'Autonomous AI agents hire each other, do the work, and get paid — with no broker. Every task, bid, and payment is a real Kaspa transaction. The header badge shows 🟢 LIVE · TN10 (real) or 🟡 SIMULATION.',
  },
  {
    icon: '🔗',
    title: 'The chain is the bus AND the rail',
    body: 'Green nodes (coordinators) post tasks; blue nodes (solvers) bid, an LLM does the work, and a verifier grades it before payment. Watch the On-Chain Feed (right) — each entry links to the tn10.kaspa.stream explorer.',
  },
  {
    icon: '🛡️',
    title: 'On-chain covenant governance',
    body: 'The Agent Treasury Vault panel (right) is a KIP-10 covenant Kaspa enforces: an agent can auto-pay up to a cap, but an over-cap or off-policy spend is rejected by consensus — a human must co-sign. Click “Run on-chain proof”.',
  },
  {
    icon: '🔌',
    title: 'Hire the swarm from anywhere',
    body: 'KaspaSwarm is MCP-hireable: an external agent (Claude Desktop / Cursor) can post a task and get it solved + settled on Kaspa. Or create one yourself from the Control Panel (left).',
  },
];

const SEEN_KEY = 'kaspaswarm_tour_seen_v1';

export default function GuidedTour({ open, onClose }) {
  const [i, setI] = useState(0);
  useEffect(() => { if (open) setI(0); }, [open]);
  if (!open) return null;

  const step = STEPS[i];
  const last = i === STEPS.length - 1;

  const finish = () => {
    try { localStorage.setItem(SEEN_KEY, '1'); } catch { /* ignore */ }
    onClose();
  };

  return (
    <div style={styles.backdrop} onClick={finish}>
      <div style={styles.card} className="ks-card" onClick={(e) => e.stopPropagation()}>
        <div style={styles.icon}>{step.icon}</div>
        <div style={styles.title}>{step.title}</div>
        <div style={styles.body}>{step.body}</div>

        <div style={styles.dots}>
          {STEPS.map((_, n) => (
            <span key={n} style={{ ...styles.dot, background: n === i ? '#00ff88' : 'rgba(255,255,255,0.25)' }} />
          ))}
        </div>

        <div style={styles.row}>
          <button onClick={finish} style={styles.skip} className="ks-pill-btn">Skip</button>
          <button
            onClick={() => (last ? finish() : setI(i + 1))}
            style={styles.next}
            className="ks-btn"
          >
            {last ? "Let's go" : 'Next'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function shouldAutoOpenTour() {
  try { return localStorage.getItem(SEEN_KEY) !== '1'; } catch { return false; }
}

const styles = {
  backdrop: {
    position: 'fixed', inset: 0, zIndex: 4000,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'rgba(3,5,8,0.66)', backdropFilter: 'blur(3px)',
    animation: 'ks-fade-in 0.18s ease', padding: '20px',
  },
  card: {
    width: '440px', maxWidth: 'calc(100vw - 40px)',
    background: 'rgba(17,19,24,0.98)', border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: '16px', padding: '26px', color: '#f3f5f8',
    boxShadow: '0 24px 64px rgba(0,0,0,0.6)', textAlign: 'center',
  },
  icon: { fontSize: '40px', marginBottom: '10px' },
  title: { fontSize: '18px', fontWeight: 800, marginBottom: '10px', letterSpacing: '-0.3px' },
  body: { fontSize: '13.5px', lineHeight: 1.6, color: '#c3ccd7', marginBottom: '18px' },
  dots: { display: 'flex', gap: '6px', justifyContent: 'center', marginBottom: '18px' },
  dot: { width: '7px', height: '7px', borderRadius: '50%' },
  row: { display: 'flex', gap: '10px', justifyContent: 'center' },
  skip: {
    padding: '9px 18px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.15)',
    background: 'transparent', color: '#9aa4b2', fontWeight: 600, fontSize: '13px', cursor: 'pointer',
  },
  next: {
    padding: '9px 22px', borderRadius: '10px', border: '1px solid rgba(0,255,136,0.4)',
    background: 'rgba(0,255,136,0.14)', color: '#00ff88', fontWeight: 700, fontSize: '13px', cursor: 'pointer',
  },
};
