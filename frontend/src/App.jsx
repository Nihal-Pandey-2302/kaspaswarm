import React, { useState, useEffect } from 'react';
import SwarmVisualization from './components/SwarmVisualization';
import ControlPanel from './components/ControlPanel';
import TaskHistory from './components/TaskHistory';
import PerformanceCharts from './components/PerformanceCharts';
import WalletConnect from './components/WalletConnect';
import { useWebSocket } from './hooks/useWebSocket';
import StatsOverlay from './components/StatsOverlay';
import OnChainFeed from './components/OnChainFeed';
import CovenantPanel from './components/CovenantPanel';
import GuidedTour, { shouldAutoOpenTour } from './components/GuidedTour';

function App() {
  const { isConnected, swarmData } = useWebSocket();
  const [showHistory, setShowHistory] = useState(false);
  const [showCharts, setShowCharts] = useState(false);
  const [showTour, setShowTour] = useState(false);

  useEffect(() => { if (shouldAutoOpenTour()) setShowTour(true); }, []);

  const isLive = swarmData?.mode === 'live';
  const chainConnected = swarmData?.chain?.connected;

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden', backgroundColor: '#050505' }}>
      {/* Center: full-window 3D canvas background (z-index 0) */}
      <SwarmVisualization swarmData={swarmData} />

      {/* ---- LEFT RAIL ---- one scrollable column, contents can never overlap */}
      <div className="ks-rail ks-rail-left ks-scroll" style={styles.leftRail}>
        {/* Brand / status header */}
        <div style={styles.brandCard} className="ks-card">
          <div style={styles.brandRow}>
            <span style={styles.brandMark}>KaspaSwarm</span>
            <span
              style={{
                ...styles.modePill,
                color: isLive ? '#00ff88' : '#ffaa00',
                borderColor: isLive ? 'rgba(0,255,136,0.4)' : 'rgba(255,170,0,0.4)',
                background: isLive ? 'rgba(0,255,136,0.10)' : 'rgba(255,170,0,0.10)',
              }}
            >
              {isLive ? '🟢 LIVE · TN10' : '🟡 SIMULATION'}
            </span>
          </div>
          <span style={styles.brandTag}>Decentralized AI Coordination</span>

          <div style={styles.statusRow}>
            <span style={styles.statusItem}>
              <span style={{ ...styles.dot, background: isConnected ? '#00ff88' : '#ff4444' }} />
              {isConnected ? 'Connected' : 'Offline'}
            </span>
            {isLive && (
              <span style={styles.statusItem}>
                <span style={{ ...styles.dot, background: chainConnected ? '#00ff88' : '#ff4444' }} />
                👁 {swarmData?.chain?.blocks ?? 0} blocks · {swarmData?.chain?.swarm_msgs ?? 0} msgs
              </span>
            )}
          </div>

          <div style={styles.railButtons}>
            <button
              onClick={() => setShowHistory(true)}
              className="ks-pill-btn"
              style={styles.railButton}
            >
              📜 Task History
            </button>
            <button
              onClick={() => setShowCharts(true)}
              className="ks-pill-btn"
              style={styles.railButton}
            >
              📊 Performance
            </button>
            <button
              onClick={() => setShowTour(true)}
              className="ks-pill-btn"
              style={styles.railButton}
              title="How this demo works"
            >
              ❓ Tour
            </button>
          </div>
        </div>

        <StatsOverlay swarmData={swarmData} isConnected={isConnected} />

        <ControlPanel isConnected={isConnected} />

        <WalletConnect />
      </div>

      {/* ---- RIGHT RAIL ---- on-chain activity, fills rail height */}
      <div className="ks-rail ks-rail-right ks-scroll" style={styles.rightRail}>
        <CovenantPanel />
        <OnChainFeed transactions={swarmData?.transactions} mode={swarmData?.mode} />
      </div>

      {/* First-visit guided tour (re-openable via ❓ Tour) */}
      <GuidedTour open={showTour} onClose={() => setShowTour(false)} />

      {/* Task History modal */}
      {showHistory && (
        <TaskHistory
          tasks={swarmData?.task_history}
          onClose={() => setShowHistory(false)}
        />
      )}

      {/* Performance Charts modal */}
      {showCharts && (
        <PerformanceCharts
          taskHistory={swarmData?.task_history}
          onClose={() => setShowCharts(false)}
        />
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.7; transform: scale(1.2); }
        }
        @keyframes ks-fade-in {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        /* ---- Shared design system ---- */
        .ks-btn {
          transition: transform 0.12s ease, filter 0.12s ease,
                      box-shadow 0.12s ease, background 0.12s ease,
                      border-color 0.12s ease;
        }
        .ks-btn:hover:not(:disabled) {
          filter: brightness(1.08);
          transform: translateY(-1px);
        }
        .ks-btn:active:not(:disabled) {
          transform: translateY(0) scale(0.98);
          filter: brightness(0.96);
        }
        .ks-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
          filter: grayscale(0.3);
        }

        .ks-pill-btn {
          transition: transform 0.12s ease, background 0.12s ease,
                      box-shadow 0.12s ease, border-color 0.12s ease;
        }
        .ks-pill-btn:hover {
          transform: translateY(-1px);
          background: rgba(0, 255, 136, 0.18) !important;
          border-color: rgba(0, 255, 136, 0.55) !important;
          box-shadow: 0 4px 16px rgba(0, 255, 136, 0.22) !important;
        }
        .ks-pill-btn:active {
          transform: translateY(0) scale(0.97);
        }

        .ks-icon-btn {
          transition: color 0.12s ease, background 0.12s ease,
                      transform 0.12s ease;
          border-radius: 8px;
        }
        .ks-icon-btn:hover {
          color: #fff !important;
          background: rgba(255, 255, 255, 0.1);
          opacity: 1 !important;
        }
        .ks-icon-btn:active { transform: scale(0.9); }

        .ks-card {
          transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }

        .ks-list-item {
          transition: background 0.15s ease, border-color 0.15s ease,
                      transform 0.15s ease;
        }
        .ks-list-item:hover {
          background: rgba(255, 255, 255, 0.07) !important;
          border-color: rgba(0, 255, 136, 0.25) !important;
        }

        .ks-field {
          transition: border-color 0.15s ease, box-shadow 0.15s ease,
                      background 0.15s ease;
        }
        .ks-field:focus {
          outline: none;
          border-color: rgba(0, 255, 136, 0.6) !important;
          box-shadow: 0 0 0 3px rgba(0, 255, 136, 0.12);
          background: rgba(255, 255, 255, 0.14) !important;
        }

        /* Readable form controls everywhere (fixes invisible dropdown text) */
        select, input, textarea { color: #f3f5f8; }
        select option,
        select optgroup {
          background-color: #15171c;
          color: #f3f5f8;
        }
        input::placeholder, textarea::placeholder { color: #7d8794; }
        /* Custom caret for selects (since appearance is removed) */
        select.ks-field {
          appearance: none;
          -webkit-appearance: none;
          background-image: url("data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D'http%3A//www.w3.org/2000/svg'%20viewBox%3D'0%200%2012%208'%3E%3Cpath%20fill%3D'%2300ff88'%20d%3D'M1%201l5%205%205-5'%2F%3E%3C/svg%3E");
          background-repeat: no-repeat;
          background-position: right 12px center;
          background-size: 11px;
          padding-right: 30px !important;
        }

        .ks-link:hover { filter: brightness(1.15); }

        .ks-rail { scrollbar-width: thin; }
        .ks-rail::-webkit-scrollbar { width: 6px; }
        .ks-rail::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.15);
          border-radius: 3px;
        }
        .ks-rail::-webkit-scrollbar-track { background: transparent; }
        .ks-scroll { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.18) transparent; }
        .ks-scroll::-webkit-scrollbar { width: 6px; }
        .ks-scroll::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.15);
          border-radius: 3px;
        }
        .ks-scroll::-webkit-scrollbar-track { background: transparent; }

        /* Narrow viewports: shrink the rails so nothing runs off-screen. */
        @media (max-width: 1024px) {
          .ks-rail-left { width: 300px !important; padding: 12px !important; }
          .ks-rail-right { width: 280px !important; padding: 12px !important; }
        }
        @media (max-width: 680px) {
          .ks-rail-left {
            width: calc(100vw - 24px) !important;
            max-width: 360px;
          }
          .ks-rail-right {
            width: calc(100vw - 24px) !important;
            max-width: 360px;
          }
        }
      `}</style>
    </div>
  );
}

const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

const styles = {
  leftRail: {
    position: 'fixed',
    left: 0,
    top: 0,
    height: '100vh',
    width: '360px',
    overflowY: 'auto',
    zIndex: 20,
    padding: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    boxSizing: 'border-box',
  },
  rightRail: {
    position: 'fixed',
    right: 0,
    top: 0,
    height: '100vh',
    width: '340px',
    overflowY: 'auto',
    zIndex: 20,
    padding: '16px',
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
  },
  brandCard: {
    background: 'rgba(17, 19, 24, 0.92)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255, 255, 255, 0.10)',
    borderRadius: '14px',
    padding: '18px',
    boxSizing: 'border-box',
    width: '100%',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
    fontFamily: FONT,
    userSelect: 'none',
  },
  brandRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '10px',
  },
  brandMark: {
    fontFamily: FONT,
    fontSize: '24px',
    fontWeight: 800,
    letterSpacing: '-0.6px',
    lineHeight: 1.05,
    background: 'linear-gradient(135deg, #00ff88 0%, #4f9eff 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  modePill: {
    fontSize: '10px',
    fontWeight: 800,
    letterSpacing: '1px',
    padding: '3px 10px',
    borderRadius: '20px',
    border: '1px solid transparent',
    fontVariantNumeric: 'tabular-nums',
  },
  brandTag: {
    display: 'block',
    fontFamily: FONT,
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    color: '#7d8794',
    marginTop: '6px',
  },
  statusRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px 14px',
    marginTop: '14px',
    paddingTop: '14px',
    borderTop: '1px solid rgba(255, 255, 255, 0.10)',
  },
  statusItem: {
    display: 'flex',
    alignItems: 'center',
    fontSize: '11px',
    fontWeight: 600,
    color: '#9aa4b2',
    fontVariantNumeric: 'tabular-nums',
  },
  dot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    marginRight: '7px',
    flexShrink: 0,
  },
  railButtons: {
    display: 'flex',
    gap: '8px',
    marginTop: '14px',
  },
  railButton: {
    flex: 1,
    background: 'rgba(0, 255, 136, 0.1)',
    border: '1px solid rgba(0, 255, 136, 0.3)',
    color: '#00ff88',
    padding: '8px 10px',
    borderRadius: '10px',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '12px',
    letterSpacing: '0.2px',
    fontFamily: FONT,
    boxShadow: '0 2px 10px rgba(0, 255, 136, 0.1)',
  },
};

export default App;
