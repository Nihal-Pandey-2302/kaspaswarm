import { useState } from 'react';

import { API_BASE } from '../utils/config';

export default function ControlPanel({ isConnected }) {
  const [isPaused, setIsPaused] = useState(false);
  const [taskTarget, setTaskTarget] = useState(5000);
  const [taskReward, setTaskReward] = useState(2000);
  const [minInterval, setMinInterval] = useState(5);
  const [maxInterval, setMaxInterval] = useState(15);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [newAgentRole, setNewAgentRole] = useState('solver');
  const [newAgentSkill, setNewAgentSkill] = useState(1.0);
  const [taskType, setTaskType] = useState('prime_finding');
  const [message, setMessage] = useState('');

  const showMessage = (msg) => {
    setMessage(msg);
    setTimeout(() => setMessage(''), 3000);
  };

  const handlePauseResume = async () => {
    try {
      const endpoint = isPaused ? `${API_BASE}/api/control/resume` : `${API_BASE}/api/control/pause`;
      const response = await fetch(endpoint, { method: 'POST' });
      const data = await response.json();
      
      setIsPaused(!isPaused);
      showMessage(isPaused ? '▶️ Swarm resumed' : '⏸️ Swarm paused');
    } catch (error) {
      showMessage('❌ Error: ' + error.message);
    }
  };

  const handleAddAgent = () => {
    setShowAgentForm(true);
    setShowTaskForm(false);
  };

  const handleSubmitAgent = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_BASE}/api/control/add-agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: newAgentRole,
          skill: newAgentSkill
        })
      });
      const data = await response.json();
      
      if (data.status === 'success') {
        showMessage(`🤖 Agent ${data.agent_id} spawned!`);
        setShowAgentForm(false);
      } else {
        showMessage('❌ Failed to add agent');
      }
    } catch (error) {
      showMessage('❌ Error: ' + error.message);
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_BASE}/api/control/create-task?target=${taskTarget}&reward=${taskReward}&task_type=${taskType}`, {
        method: 'POST'
      });
      const data = await response.json();
      
      if (data && data.status === 'success') {
        showMessage(`✅ Task ${data.task_id} created!`);
        setShowTaskForm(false);
      } else {
        showMessage('❌ ' + (data?.error || 'Unknown error'));
      }
    } catch (error) {
      showMessage('❌ Error: ' + error.message);
    }
  };

  const handleUpdateFrequency = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/api/control/frequency?min_interval=${minInterval}&max_interval=${maxInterval}`,
        { method: 'POST' }
      );
      const data = await response.json();
      showMessage(`⚙️ Frequency updated: ${data.min}-${data.max}s`);
    } catch (error) {
      showMessage('❌ Error: ' + error.message);
    }
  };

  const handleReset = async () => {
    if (!confirm('Are you sure you want to reset the swarm? All progress will be lost.')) {
      return;
    }
    
    try {
      const response = await fetch(`${API_BASE}/api/control/reset`, { method: 'POST' });
      const data = await response.json();
      showMessage('🔄 Swarm reset!');
      setIsPaused(false);
    } catch (error) {
      showMessage('❌ Error: ' + error.message);
    }
  };

  return (
    <div style={styles.panel}>
      {/* Header */}
      <div style={styles.header}>
        <h3 style={styles.title}>Control Panel</h3>
        {!isConnected && <span style={styles.disconnected}>⚠️ Disconnected</span>}
      </div>

      {/* Message Toast */}
      {message && (
        <div style={styles.message}>
          {message}
        </div>
      )}

      {/* Main Controls */}
      <div style={styles.section}>
        <button 
          onClick={handlePauseResume}
          disabled={!isConnected}
          style={{...styles.button, ...styles.primaryButton}}
        >
          {isPaused ? '▶️ Resume' : '⏸️ Pause'} Swarm
        </button>

        <button 
          onClick={() => setShowTaskForm(!showTaskForm)}
          disabled={!isConnected}
          style={{...styles.button, ...styles.secondaryButton}}
        >
          ➕ Create Task
        </button>

        <button 
          onClick={handleReset}
          disabled={!isConnected}
          style={{...styles.button, ...styles.dangerButton}}
        >
          🔄 Reset Swarm
        </button>
      </div>

      {/* Task Creation Form */}
      {showTaskForm && (
        <form onSubmit={handleCreateTask} style={styles.form}>
          <div style={styles.formTitle}>Create Manual Task</div>
          
          <div style={styles.formGroup}>
            <label style={styles.label}>Task Type</label>
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
              style={styles.select}
            >
              <option value="prime_finding">🔢 Prime Finding</option>
              <option value="hash_cracking">🔐 Hash Cracking</option>
              <option value="sorting">📊 Sorting</option>
              <option value="data_search">🔍 Data Search</option>
            </select>
          </div>

          {taskType !== 'hash_cracking' && (
            <div style={styles.formGroup}>
              <label style={styles.label}>
                {taskType === 'prime_finding' && 'Target Number'}
                {taskType === 'sorting' && 'Array Size'}
                {taskType === 'data_search' && 'Dataset Size'}
              </label>
              <input
                type="number"
                value={taskTarget}
                onChange={(e) => setTaskTarget(Number(e.target.value))}
                min={taskType === 'sorting' ? "50" : "1000"}
                max={taskType === 'sorting' ? "500" : "50000"}
                style={styles.input}
                required
              />
              <span style={styles.hint}>
                {taskType === 'prime_finding' && 'Find largest prime less than this'}
                {taskType === 'sorting' && 'Number of elements to sort'}
                {taskType === 'data_search' && 'Size of dataset to search'}
              </span>
            </div>
          )}

          <div style={styles.formGroup}>
            <label style={styles.label}>Reward (sompi)</label>
            <input
              type="number"
              value={taskReward}
              onChange={(e) => setTaskReward(Number(e.target.value))}
              min="100"
              max="10000"
              style={styles.input}
              required
            />
          </div>

          <div style={styles.formButtons}>
            <button type="submit" style={{...styles.button, ...styles.primaryButton}}>
              Create
            </button>
            <button 
              type="button" 
              onClick={() => setShowTaskForm(false)}
              style={{...styles.button, ...styles.secondaryButton}}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Agent Management */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>Agent Management</div>
        <button 
          onClick={handleAddAgent}
          disabled={!isConnected}
          style={{...styles.button, ...styles.secondaryButton}}
        >
          🤖 Add Agent
        </button>
      </div>

      {/* Add Agent Form */}
      {showAgentForm && (
        <form onSubmit={handleSubmitAgent} style={styles.form}>
          <div style={styles.formTitle}>Add New Agent</div>
          
          <div style={styles.formGroup}>
            <label style={styles.label}>Role</label>
            <select
              value={newAgentRole}
              onChange={(e) => setNewAgentRole(e.target.value)}
              style={styles.select}
            >
              <option value="solver">Solver</option>
              <option value="coordinator">Coordinator</option>
            </select>
          </div>

          {newAgentRole === 'solver' && (
            <div style={styles.formGroup}>
              <label style={styles.label}>Skill Level: {newAgentSkill}</label>
              <input
                type="range"
                min="0.5"
                max="1.5"
                step="0.1"
                value={newAgentSkill}
                onChange={(e) => setNewAgentSkill(Number(e.target.value))}
                style={styles.slider}
              />
            </div>
          )}

          <div style={styles.formButtons}>
            <button type="submit" style={{...styles.button, ...styles.primaryButton}}>
              Spawn
            </button>
            <button 
              type="button" 
              onClick={() => setShowAgentForm(false)}
              style={{...styles.button, ...styles.secondaryButton}}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Frequency Control */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>Task Frequency</div>
        
        <div style={styles.sliderGroup}>
          <label style={styles.label}>
            Min Interval: {minInterval}s
          </label>
          <input
            type="range"
            min="1"
            max="30"
            value={minInterval}
            onChange={(e) => setMinInterval(Number(e.target.value))}
            disabled={!isConnected}
            style={styles.slider}
          />
        </div>

        <div style={styles.sliderGroup}>
          <label style={styles.label}>
            Max Interval: {maxInterval}s
          </label>
          <input
            type="range"
            min="5"
            max="60"
            value={maxInterval}
            onChange={(e) => setMaxInterval(Number(e.target.value))}
            disabled={!isConnected}
            style={styles.slider}
          />
        </div>

        <button 
          onClick={handleUpdateFrequency}
          disabled={!isConnected || minInterval >= maxInterval}
          style={{...styles.button, ...styles.secondaryButton, width: '100%'}}
        >
          Apply Frequency
        </button>
      </div>
    </div>
  );
}

const styles = {
  panel: {
    position: 'absolute',
    top: '20px',
    right: '20px',
    background: 'rgba(10, 10, 10, 0.9)',
    backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '16px',
    padding: '20px',
    minWidth: '300px',
    maxWidth: '350px',
    color: '#fff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    zIndex: 1000,
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  title: {
    margin: 0,
    fontSize: '18px',
    fontWeight: 'bold',
    background: 'linear-gradient(135deg, #00ff88 0%, #0088ff 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  disconnected: {
    fontSize: '12px',
    color: '#ff4444',
  },
  message: {
    background: 'rgba(0, 255, 136, 0.1)',
    border: '1px solid rgba(0, 255, 136, 0.3)',
    borderRadius: '8px',
    padding: '8px 12px',
    marginBottom: '12px',
    fontSize: '13px',
    color: '#00ff88',
  },
  section: {
    marginBottom: '16px',
  },
  sectionTitle: {
    fontSize: '14px',
    fontWeight: '600',
    marginBottom: '12px',
    color: '#ccc',
  },
  button: {
    width: '100%',
    padding: '10px 16px',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s',
    marginBottom: '8px',
    fontFamily: 'inherit',
  },
  primaryButton: {
    background: 'linear-gradient(135deg, #00ff88 0%, #00cc70 100%)',
    color: '#000',
  },
  secondaryButton: {
    background: 'rgba(255, 255, 255, 0.1)',
    color: '#fff',
    border: '1px solid rgba(255, 255, 255, 0.2)',
  },
  dangerButton: {
    background: 'rgba(255, 68, 68, 0.2)',
    color: '#ff4444',
    border: '1px solid rgba(255, 68, 68, 0.3)',
  },
  form: {
    background: 'rgba(255, 255, 255, 0.05)',
    borderRadius: '8px',
    padding: '16px',
    marginBottom: '16px',
  },
  formTitle: {
    fontSize: '14px',
    fontWeight: '600',
    marginBottom: '12px',
    color: '#fff',
  },
  formGroup: {
    marginBottom: '12px',
  },
  label: {
    display: 'block',
    fontSize: '12px',
    marginBottom: '6px',
    color: '#aaa',
  },
  input: {
    width: '100%',
    padding: '8px 12px',
    background: 'rgba(255, 255, 255, 0.1)',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    fontFamily: 'inherit',
  },
  hint: {
    display: 'block',
    fontSize: '11px',
    color: '#666',
    marginTop: '4px',
  },
  formButtons: {
    display: 'flex',
    gap: '8px',
    marginTop: '12px',
  },
  sliderGroup: {
    marginBottom: '12px',
  },
  slider: {
    width: '100%',
    marginTop: '4px',
  },
  select: {
    width: '100%',
    padding: '8px 12px',
    background: 'rgba(255, 255, 255, 0.1)',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    fontFamily: 'inherit',
    cursor: 'pointer',
    appearance: 'none', // Remove default arrow in some browsers
  },
};
