import { useState } from 'react';

import { API_BASE } from '../utils/config';

export default function ControlPanel({ isConnected }) {
  const [isPaused, setIsPaused] = useState(false);
  const [taskTarget, setTaskTarget] = useState(5000);
  const [taskReward, setTaskReward] = useState(0.5);  // KAS (converted to sompi on submit)
  const [minInterval, setMinInterval] = useState(5);
  const [maxInterval, setMaxInterval] = useState(15);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [newAgentRole, setNewAgentRole] = useState('solver');
  const [newAgentSkill, setNewAgentSkill] = useState(1.0);
  const [taskType, setTaskType] = useState('prime_finding');
  const [taskPrompt, setTaskPrompt] = useState('Summarize in one sentence why Kaspa is fast.');
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
      const promptParam = taskType === 'ai_task' ? `&prompt=${encodeURIComponent(taskPrompt)}` : '';
      const rewardSompi = Math.round(taskReward * 100_000_000);  // KAS -> sompi
      const response = await fetch(`${API_BASE}/api/control/create-task?target=${taskTarget}&reward=${rewardSompi}&task_type=${taskType}${promptParam}`, {
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
    <div style={styles.panel} className="ks-card">
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
          className="ks-btn"
          style={{...styles.button, ...styles.primaryButton}}
        >
          {isPaused ? '▶️ Resume' : '⏸️ Pause'} Swarm
        </button>

        <button
          onClick={() => setShowTaskForm(!showTaskForm)}
          disabled={!isConnected}
          className="ks-btn"
          style={{...styles.button, ...styles.secondaryButton}}
        >
          ➕ Create Task
        </button>

        <button
          onClick={handleReset}
          disabled={!isConnected}
          className="ks-btn"
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
              className="ks-field"
              style={styles.select}
            >
              <option value="ai_task">🤖 AI Task (LLM agent)</option>
              <option value="prime_finding">🔢 Prime Finding</option>
              <option value="hash_cracking">🔐 Hash Cracking</option>
              <option value="sorting">📊 Sorting</option>
              <option value="data_search">🔍 Data Search</option>
            </select>
          </div>

          {taskType === 'ai_task' && (
            <div style={styles.formGroup}>
              <label style={styles.label}>Prompt (the real work the agent does)</label>
              <textarea
                value={taskPrompt}
                onChange={(e) => setTaskPrompt(e.target.value)}
                rows={3}
                className="ks-field"
                style={{ ...styles.input, resize: 'vertical', fontFamily: 'inherit' }}
                placeholder="e.g. Summarize this text / Write a Python function that…"
                required
              />
              <span style={styles.hint}>An LLM-powered solver agent will complete this and a verifier agent will grade it.</span>
            </div>
          )}

          {(taskType === 'prime_finding' || taskType === 'sorting' || taskType === 'data_search') && (
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
                className="ks-field"
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
            <label style={styles.label}>Reward (KAS)</label>
            <input
              type="number"
              value={taskReward}
              onChange={(e) => setTaskReward(Number(e.target.value))}
              min="0.2"
              max="5"
              step="0.1"
              className="ks-field"
              style={styles.input}
              required
            />
          </div>

          <div style={styles.formButtons}>
            <button type="submit" className="ks-btn" style={{...styles.button, ...styles.primaryButton}}>
              Create
            </button>
            <button
              type="button"
              onClick={() => setShowTaskForm(false)}
              className="ks-btn"
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
          className="ks-btn"
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
              className="ks-field"
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
            <button type="submit" className="ks-btn" style={{...styles.button, ...styles.primaryButton}}>
              Spawn
            </button>
            <button
              type="button"
              onClick={() => setShowAgentForm(false)}
              className="ks-btn"
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
          className="ks-btn"
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
    background: 'rgba(17, 19, 24, 0.92)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255, 255, 255, 0.10)',
    borderRadius: '14px',
    padding: '20px',
    width: '100%',
    color: '#f3f5f8',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    boxSizing: 'border-box',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  title: {
    margin: 0,
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    color: '#7d8794',
  },
  disconnected: {
    fontSize: '11px',
    fontWeight: 600,
    color: '#ff6b6b',
  },
  message: {
    background: 'rgba(0, 255, 136, 0.12)',
    border: '1px solid rgba(0, 255, 136, 0.3)',
    borderRadius: '10px',
    padding: '8px 12px',
    marginBottom: '12px',
    fontSize: '13px',
    fontWeight: 600,
    color: '#00ff88',
    animation: 'ks-fade-in 0.2s ease',
  },
  section: {
    marginBottom: '16px',
  },
  sectionTitle: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    marginBottom: '12px',
    color: '#7d8794',
  },
  button: {
    width: '100%',
    padding: '10px 16px',
    border: 'none',
    borderRadius: '10px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    marginBottom: '8px',
    fontFamily: 'inherit',
  },
  primaryButton: {
    background: 'linear-gradient(135deg, #00ff88 0%, #00cc70 100%)',
    color: '#06140d',
    boxShadow: '0 2px 12px rgba(0, 255, 136, 0.25)',
  },
  secondaryButton: {
    background: 'rgba(255, 255, 255, 0.08)',
    color: '#f3f5f8',
    border: '1px solid rgba(255, 255, 255, 0.15)',
  },
  dangerButton: {
    background: 'rgba(255, 68, 68, 0.15)',
    color: '#ff6b6b',
    border: '1px solid rgba(255, 68, 68, 0.3)',
  },
  form: {
    background: 'rgba(255, 255, 255, 0.04)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '16px',
    animation: 'ks-fade-in 0.2s ease',
  },
  formTitle: {
    fontSize: '13px',
    fontWeight: 700,
    marginBottom: '14px',
    color: '#f3f5f8',
  },
  formGroup: {
    marginBottom: '12px',
  },
  label: {
    display: 'block',
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.3px',
    marginBottom: '6px',
    color: '#9aa4b2',
  },
  input: {
    width: '100%',
    padding: '9px 12px',
    background: 'rgba(255, 255, 255, 0.08)',
    border: '1px solid rgba(255, 255, 255, 0.15)',
    borderRadius: '8px',
    color: '#f3f5f8',
    fontSize: '14px',
    fontFamily: 'inherit',
    boxSizing: 'border-box',
  },
  hint: {
    display: 'block',
    fontSize: '11px',
    color: '#7d8794',
    marginTop: '5px',
    lineHeight: 1.4,
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
    padding: '9px 12px',
    background: 'rgba(255, 255, 255, 0.08)',
    border: '1px solid rgba(255, 255, 255, 0.15)',
    borderRadius: '8px',
    color: '#f3f5f8',
    fontSize: '14px',
    fontFamily: 'inherit',
    cursor: 'pointer',
    boxSizing: 'border-box',
    appearance: 'none', // Remove default arrow in some browsers
  },
};
