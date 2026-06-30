export default function StatsOverlay({ swarmData, isConnected }) {
  if (!swarmData) {
    return (
      <div style={styles.stack}>
        <div style={styles.card} className="ks-card">
          <div style={styles.title}>🐝 Swarm Status</div>
          <div style={styles.subtitle}>Decentralized AI Coordination</div>
          <div style={styles.divider} />
          <div style={styles.loadingRow}>
            <div style={{
              ...styles.indicator,
              background: isConnected ? '#00ff88' : '#ffaa00',
              animation: 'pulse 1.6s infinite',
            }} />
            <span style={styles.status}>
              {isConnected ? 'Initializing swarm…' : 'Connecting…'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  const { coordinators = [], solvers = [] } = swarmData.agents || {};
  const totalEarnings = solvers.reduce((sum, s) => sum + (s.earnings || 0), 0);
  const avgSuccessRate = solvers.length > 0
    ? solvers.reduce((sum, s) => sum + (s.success_rate || 0), 0) / solvers.length
    : 0;

  return (
    <div style={styles.stack}>
      {/* Main card */}
      <div style={styles.card} className="ks-card">
        <div style={styles.cardHeader}>Swarm Overview</div>

        <div style={styles.divider} />
        
        <div style={styles.stat}>
          <span style={styles.label}>Mode:</span>
          <span style={styles.value}>{swarmData.mode?.toUpperCase()}</span>
        </div>
        
        <div style={styles.stat}>
          <span style={styles.label}>Total Agents:</span>
          <span style={styles.value}>{swarmData.total_agents}</span>
        </div>
        
        <div style={styles.stat}>
          <span style={styles.label}>Coordinators:</span>
          <span style={{...styles.value, color: '#00ff88'}}>{swarmData.coordinators_count}</span>
        </div>
        
        <div style={styles.stat}>
          <span style={styles.label}>Solvers:</span>
          <span style={{...styles.value, color: '#4f9eff'}}>{swarmData.solvers_count}</span>
        </div>
        
        <div style={styles.divider} />
        
        <div style={styles.stat}>
          <span style={styles.label}>Active Tasks:</span>
          <span style={{...styles.value, color: '#ffaa00'}}>{swarmData.active_tasks}</span>
        </div>
        
        <div style={styles.stat}>
          <span style={styles.label}>Completed:</span>
          <span style={{...styles.value, color: '#00ff88'}}>{swarmData.completed_tasks}</span>
        </div>
        
        <div style={styles.stat}>
          <span style={styles.label}>Success Rate:</span>
          <span style={styles.value}>{(avgSuccessRate * 100).toFixed(1)}%</span>
        </div>
        
        <div style={styles.stat}>
          <span style={styles.label}>Total Rewards:</span>
          <span style={styles.value}>{totalEarnings} sompi</span>
        </div>

        {swarmData.escrow && (
          <div style={styles.stat}>
            <span style={styles.label}>Escrow:</span>
            <span style={styles.value}>
              <span style={{ color: '#00ff88' }}>{swarmData.escrow.released || 0}✓</span>
              {' / '}
              <span style={{ color: '#ff6b6b' }}>{swarmData.escrow.slashed || 0}⚔</span>
            </span>
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{...styles.card, ...styles.legend}} className="ks-card">
        <div style={styles.legendTitle}>Legend</div>
        <div style={styles.legendItem}>
          <div style={{...styles.dot, background: '#00ff88'}} />
          <span>Coordinator (Posts Tasks)</span>
        </div>
        <div style={styles.legendItem}>
          <div style={{...styles.dot, background: '#4f9eff'}} />
          <span>Solver (Completes Tasks)</span>
        </div>
        <div style={styles.legendItem}>
          <div style={{...styles.dot, background: '#ffaa00', animation: 'pulse 2s infinite'}} />
          <span>Active (Working)</span>
        </div>
      </div>

      {/* Reputation leaderboard — the economy at a glance */}
      {solvers.length > 0 && (
        <div style={{...styles.card, ...styles.legend}} className="ks-card">
          <div style={styles.legendTitle}>Top Agents · Reputation</div>
          {[...solvers]
            .sort((a, b) => (b.reputation || 0) - (a.reputation || 0))
            .map((s) => (
              <div key={s.agent_id} style={styles.repRow}>
                <span style={styles.repName}>{(s.agent_id || '').replace('solver_', 'S')}</span>
                <span style={styles.repTrack}>
                  <span style={{ ...styles.repFill, width: `${Math.min(100, (s.reputation || 0) / 200 * 100)}%` }} />
                </span>
                <span style={styles.repVal}>{Math.round(s.reputation || 0)}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

const styles = {
  stack: {
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    width: '100%',
  },
  card: {
    background: 'rgba(17, 19, 24, 0.92)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255, 255, 255, 0.10)',
    borderRadius: '14px',
    padding: '18px',
    color: '#f3f5f8',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    width: '100%',
    boxSizing: 'border-box',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
  },
  cardHeader: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    color: '#7d8794',
  },
  title: {
    fontSize: '20px',
    fontWeight: 800,
    letterSpacing: '-0.5px',
    marginBottom: '4px',
    background: 'linear-gradient(135deg, #00ff88 0%, #4f9eff 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  subtitle: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    color: '#7d8794',
    marginBottom: '16px',
  },
  divider: {
    height: '1px',
    background: 'rgba(255, 255, 255, 0.10)',
    margin: '16px 0',
  },
  stat: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  label: {
    fontSize: '13px',
    fontWeight: 500,
    color: '#9aa4b2',
  },
  value: {
    fontSize: '14px',
    fontWeight: 700,
    color: '#f3f5f8',
    fontFamily: 'monospace',
    fontVariantNumeric: 'tabular-nums',
  },
  loadingRow: {
    display: 'flex',
    alignItems: 'center',
  },
  status: {
    fontSize: '13px',
    color: '#ffaa00',
    fontWeight: 600,
  },
  legend: {
    fontSize: '13px',
  },
  legendTitle: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    marginBottom: '12px',
    color: '#7d8794',
  },
  legendItem: {
    display: 'flex',
    alignItems: 'center',
    marginBottom: '8px',
    color: '#9aa4b2',
  },
  dot: {
    width: '12px',
    height: '12px',
    borderRadius: '50%',
    marginRight: '8px',
  },
  repRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '8px',
  },
  repName: {
    fontSize: '12px',
    fontWeight: 700,
    color: '#cbd5e1',
    width: '28px',
  },
  repTrack: {
    flex: 1,
    height: '6px',
    borderRadius: '3px',
    background: 'rgba(255,255,255,0.08)',
    overflow: 'hidden',
  },
  repFill: {
    display: 'block',
    height: '100%',
    borderRadius: '3px',
    background: 'linear-gradient(90deg, #00ff88, #4f9eff)',
  },
  repVal: {
    fontSize: '12px',
    fontWeight: 700,
    color: '#f3f5f8',
    width: '30px',
    textAlign: 'right',
    fontFamily: 'monospace',
    fontVariantNumeric: 'tabular-nums',
  },
  indicator: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    marginRight: '8px',
  },
};
