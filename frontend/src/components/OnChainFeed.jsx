import React from 'react';

// Testnet (TN10) explorer base. kaspa.stream is the explorer recommended by Kaspa
// core (IzioDev) for TN10 — explorer-tn10.kaspa.org has been unreliable.
const EXPLORER_BASE = 'https://tn10.kaspa.stream/transactions';

const MSG_TYPES = {
  1: { label: 'Task', color: '#ffaa00' },
  2: { label: 'Bid', color: '#4f9eff' },
  3: { label: 'Assign', color: '#bb88ff' },
  4: { label: 'Solution', color: '#00ff88' },
};

const truncateTx = (txId) => {
  if (!txId) return '';
  if (txId.length <= 12) return txId;
  return `${txId.slice(0, 4)}…${txId.slice(-4)}`;
};

const formatSender = (tx) => {
  // Prefer a readable agent id; fall back to address.
  if (tx.from) return tx.from;
  if (tx.from_address) return `${tx.from_address.slice(0, 8)}…`;
  return 'unknown';
};

const relativeTime = (ts) => {
  if (!ts) return '';
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
};

const OnChainFeed = ({ transactions, mode }) => {
  const txs = Array.isArray(transactions) ? [...transactions].reverse() : [];
  const onchainCount = txs.filter((t) => t.onchain).length;
  const isLive = mode === 'live';

  return (
    <div style={styles.container} className="ks-card">
      <div style={styles.header}>
        <span style={styles.headerTitle}>⛓ On-Chain Activity</span>
        <span style={styles.count}>
          {isLive ? `${onchainCount}/${txs.length} on-chain` : `${txs.length}`}
        </span>
      </div>

      {!isLive && txs.length > 0 && (
        <div style={styles.simHint}>Simulation mode — enable live mode for real tx links</div>
      )}

      <div style={styles.list} className="ks-scroll">
        {txs.length === 0 ? (
          <div style={styles.empty}>
            <div style={styles.emptyIcon}>⛓</div>
            <div style={styles.emptyText}>Waiting for swarm messages…</div>
          </div>
        ) : (
          txs.map((tx, idx) => {
            const meta = MSG_TYPES[tx.msg_type] || { label: `Type ${tx.msg_type}`, color: '#888' };
            const hasLink = tx.onchain && tx.tx_id;
            return (
              <div key={`${tx.tx_id || 'mem'}-${tx.timestamp || idx}-${idx}`} style={styles.row} className="ks-list-item">
                <div style={styles.rowTop}>
                  <span style={{ ...styles.typeBadge, background: meta.color }}>
                    {meta.label}
                  </span>
                  {tx.task_id != null && tx.task_id !== '' && (
                    <span style={styles.taskId}>#{tx.task_id}</span>
                  )}
                  <span style={styles.sender}>{formatSender(tx)}</span>
                </div>

                <div style={styles.rowBottom}>
                  {hasLink ? (
                    <a
                      href={`${EXPLORER_BASE}/${tx.tx_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={styles.txLink}
                      className="ks-link"
                      title={tx.tx_id}
                    >
                      🔗 {truncateTx(tx.tx_id)}
                    </a>
                  ) : (
                    <span style={styles.memBadge}>in-memory</span>
                  )}
                  <span style={styles.time}>{relativeTime(tx.timestamp)}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

const styles = {
  container: {
    width: '100%',
    // Fill the remaining rail space (below CovenantPanel) rather than the whole
    // viewport, so the rail has one scrollbar instead of a nested double-scroll.
    flex: 1,
    minHeight: '260px',
    background: 'rgba(17, 19, 24, 0.92)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255, 255, 255, 0.10)',
    borderRadius: '14px',
    color: '#f3f5f8',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    display: 'flex',
    flexDirection: 'column',
    boxSizing: 'border-box',
    boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '14px 16px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.10)',
  },
  headerTitle: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    color: '#00ff88',
  },
  count: {
    fontSize: '10px',
    fontWeight: 700,
    color: '#9aa4b2',
    background: 'rgba(255,255,255,0.08)',
    border: '1px solid rgba(255,255,255,0.10)',
    borderRadius: '20px',
    padding: '2px 9px',
    fontVariantNumeric: 'tabular-nums',
  },
  list: {
    flex: 1,
    minHeight: 0,
    overflowY: 'auto',
    padding: '8px',
  },
  empty: {
    textAlign: 'center',
    padding: '28px 8px',
  },
  emptyIcon: {
    fontSize: '26px',
    opacity: 0.25,
    marginBottom: '8px',
  },
  emptyText: {
    fontSize: '12px',
    color: '#9aa4b2',
  },
  row: {
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: '10px',
    padding: '9px 11px',
    marginBottom: '6px',
  },
  rowTop: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '5px',
  },
  typeBadge: {
    fontSize: '10px',
    fontWeight: 700,
    color: '#000',
    borderRadius: '6px',
    padding: '2px 7px',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
  },
  taskId: {
    fontSize: '11px',
    fontFamily: 'monospace',
    color: '#ffc94d',
  },
  sender: {
    fontSize: '11px',
    color: '#9aa4b2',
    marginLeft: 'auto',
    maxWidth: '120px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  rowBottom: {
    display: 'flex',
    alignItems: 'center',
  },
  simHint: {
    fontSize: '10px',
    color: '#d4a843',
    padding: '6px 14px 0',
    fontStyle: 'italic',
  },
  time: {
    fontSize: '10px',
    color: '#9aa4b2',
    marginLeft: 'auto',
  },
  txLink: {
    fontSize: '11px',
    fontFamily: 'monospace',
    color: '#00ff88',
    textDecoration: 'none',
    borderBottom: '1px dotted rgba(0,255,136,0.5)',
  },
  memBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: '#9aa4b2',
    background: 'rgba(255,255,255,0.07)',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: '6px',
    padding: '2px 7px',
  },
};

export default OnChainFeed;
