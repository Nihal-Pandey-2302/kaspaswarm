export default function StatsOverlay({ swarmData, isConnected }) {
  if (!swarmData) {
    return (
      <div style={styles.overlay}>
        <div style={styles.card}>
          <div style={styles.title}>🐝 KaspaSwarm</div>
          <div style={styles.status}>
            {isConnected ? '⚡ Initializing...' : '🔴 Connecting...'}
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
    <div style={styles.overlay}>
      {/* Main card */}
      <div style={styles.card}>
        <div style={styles.title}>🐝 KaspaSwarm</div>
        <div style={styles.subtitle}>Decentralized AI Coordination</div>
        
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
          <span style={{...styles.value, color: '#0088ff'}}>{swarmData.solvers_count}</span>
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
      </div>

      {/* Legend */}
      <div style={{...styles.card, ...styles.legend}}>
        <div style={styles.legendTitle}>Legend</div>
        <div style={styles.legendItem}>
          <div style={{...styles.dot, background: '#00ff88'}} />
          <span>Coordinator (Posts Tasks)</span>
        </div>
        <div style={styles.legendItem}>
          <div style={{...styles.dot, background: '#0088ff'}} />
          <span>Solver (Completes Tasks)</span>
        </div>
        <div style={styles.legendItem}>
          <div style={{...styles.dot, background: '#ffaa00', animation: 'pulse 2s infinite'}} />
          <span>Active (Working)</span>
        </div>
      </div>

      {/* Connection status */}
      <div style={styles.connection}>
        <div style={{...styles.indicator, background: isConnected ? '#00ff88' : '#ff4444'}} />
        <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    padding: '20px',
    pointerEvents: 'none',
    zIndex: 1000,
  },
  card: {
    background: 'rgba(10, 10, 10, 0.85)',
    backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '16px',
    padding: '24px',
    color: '#ffffff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    minWidth: '280px',
    marginBottom: '16px',
  },
  title: {
    fontSize: '28px',
    fontWeight: 'bold',
    marginBottom: '4px',
    background: 'linear-gradient(135deg, #00ff88 0%, #0088ff 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  subtitle: {
    fontSize: '12px',
    color: '#888',
    marginBottom: '16px',
  },
  divider: {
    height: '1px',
    background: 'rgba(255, 255, 255, 0.1)',
    margin: '16px 0',
  },
  stat: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  label: {
    fontSize: '14px',
    color: '#aaa',
  },
  value: {
    fontSize: '16px',
    fontWeight: 'bold',
    color: '#fff',
  },
  status: {
    fontSize: '14px',
    color: '#ffaa00',
    marginTop: '8px',
  },
  legend: {
    fontSize: '14px',
  },
  legendTitle: {
    fontSize: '14px',
    fontWeight: 'bold',
    marginBottom: '12px',
    color: '#fff',
  },
  legendItem: {
    display: 'flex',
    alignItems: 'center',
    marginBottom: '8px',
    color: '#ccc',
  },
  dot: {
    width: '12px',
    height: '12px',
    borderRadius: '50%',
    marginRight: '8px',
  },
  connection: {
    position: 'absolute',
    bottom: '20px',
    right: '20px',
    background: 'rgba(10, 10, 10, 0.85)',
    backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '24px',
    padding: '8px 16px',
    display: 'flex',
    alignItems: 'center',
    fontSize: '12px',
    color: '#ccc',
  },
  indicator: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    marginRight: '8px',
  },
};
