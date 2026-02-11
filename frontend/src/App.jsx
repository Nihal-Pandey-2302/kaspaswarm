import React, { useState, useEffect } from 'react';
import SwarmVisualization from './components/SwarmVisualization';
import ControlPanel from './components/ControlPanel';
import TaskHistory from './components/TaskHistory';
import PerformanceCharts from './components/PerformanceCharts';
import WalletConnect from './components/WalletConnect';
import { useWebSocket } from './hooks/useWebSocket';
import StatsOverlay from './components/StatsOverlay';

function App() {
  const { isConnected, swarmData, sendMessage } = useWebSocket();
  const [showHistory, setShowHistory] = useState(false);
  const [showCharts, setShowCharts] = useState(false);

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden', backgroundColor: '#050505' }}>
      <SwarmVisualization swarmData={swarmData} />
      
      <StatsOverlay swarmData={swarmData} isConnected={isConnected} />
      
      <ControlPanel 
        isConnected={isConnected} 
        onSendMessage={sendMessage} 
      />
      
      <WalletConnect />
      
      {/* Top Buttons Container */}
      <div style={{
        position: 'absolute',
        top: '20px',
        right: '640px', // Left of WalletConnect + Control Panel
        zIndex: 1000,
        display: 'flex',
        gap: '10px'
      }}>
        {!showHistory && (
          <button 
            onClick={() => setShowHistory(true)}
            style={styles.topButton}
          >
            📜 Task History
          </button>
        )}
        
        {!showCharts && (
          <button 
            onClick={() => setShowCharts(true)}
            style={styles.topButton}
          >
            📊 Performance
          </button>
        )}
      </div>

      {/* Task History Sidebar */}
      {showHistory && (
        <TaskHistory 
          tasks={swarmData?.task_history} 
          onClose={() => setShowHistory(false)} 
        />
      )}
      
      {/* Performance Charts Panel */}
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
      `}</style>
    </div>
  );
}

const styles = {
  topButton: {
    background: 'rgba(0, 255, 136, 0.1)',
    border: '1px solid rgba(0, 255, 136, 0.3)',
    color: '#00ff88',
    padding: '8px 16px',
    borderRadius: '20px',
    cursor: 'pointer',
    backdropFilter: 'blur(5px)',
    fontWeight: 'bold',
    boxShadow: '0 0 10px rgba(0, 255, 136, 0.1)',
    transition: 'all 0.2s',
  }
};

export default App;
