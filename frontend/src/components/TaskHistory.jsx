import React, { useState, useEffect } from 'react';

const TaskHistory = ({ tasks, onClose }) => {
  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h2 style={styles.title}>Task History</h2>
        <button onClick={onClose} style={styles.closeBtn}>×</button>
      </div>
      
      <div style={styles.content}>
        {tasks && tasks.length > 0 ? (
          [...tasks].reverse().map((task) => (
            <div key={task.task_id} style={styles.taskCard}>
              <div style={styles.taskHeader}>
                <span style={styles.taskId}>#{task.task_id}</span>
                <span style={{
                  ...styles.statusBadge,
                  backgroundColor: getStatusColor(task.status)
                }}>
                  {task.status}
                </span>
              </div>
              
              <div style={styles.description}>{task.description}</div>
              
              <div style={styles.details}>
                <div style={styles.detailRow}>
                  <span>Reward:</span>
                  <span style={styles.reward}>{task.reward} sompi</span>
                </div>
                
                {task.task_type && (
                  <div style={styles.detailRow}>
                    <span>Type:</span>
                    <span>{getTaskTypeIcon(task.task_type)} {task.task_type}</span>
                  </div>
                )}
                
                {task.assigned_to && (
                  <div style={styles.detailRow}>
                    <span>Solver:</span>
                    <span>{task.assigned_to.split('_')[1]}</span>
                  </div>
                )}
                
                {task.solution && (
                  <div style={styles.solution}>
                    Solution: {task.solution}
                  </div>
                )}
              </div>
              
              <div style={styles.timestamp}>
                {new Date(task.created_at * 1000).toLocaleTimeString()}
              </div>
            </div>
          ))
        ) : (
          <div style={styles.emptyState}>No tasks recorded yet</div>
        )}
      </div>
    </div>
  );
};

// Helper functions
const getStatusColor = (status) => {
  switch (status) {
    case 'created': return '#00aaff'; // Blue
    case 'assigned': return '#ffaa00'; // Orange
    case 'completed': return '#00ff88'; // Green
    case 'failed': return '#ff4444'; // Red
    default: return '#888';
  }
};

const getTaskTypeIcon = (type) => {
  switch (type) {
    case 'prime_finding': return '🔢';
    case 'hash_cracking': return '🔐';
    case 'sorting': return '📊';
    case 'data_search': return '🔍';
    default: return '📝';
  }
};

const styles = {
  container: {
    position: 'absolute',
    top: 0,
    right: 0,
    width: '320px',
    height: '100vh',
    backgroundColor: 'rgba(10, 15, 20, 0.95)',
    borderLeft: '1px solid rgba(0, 255, 136, 0.2)',
    display: 'flex',
    flexDirection: 'column',
    zIndex: 2000,
    backdropFilter: 'blur(10px)',
    boxShadow: '-5px 0 20px rgba(0,0,0,0.5)',
  },
  header: {
    padding: '20px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: 'rgba(0, 0, 0, 0.2)',
  },
  title: {
    margin: 0,
    fontSize: '18px',
    fontWeight: '600',
    color: '#00ff88',
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#fff',
    fontSize: '24px',
    cursor: 'pointer',
    opacity: 0.7,
    padding: '0 5px',
  },
  content: {
    flex: 1,
    overflowY: 'auto',
    padding: '15px',
  },
  taskCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: '8px',
    padding: '12px',
    marginBottom: '12px',
    border: '1px solid rgba(255, 255, 255, 0.05)',
    transition: 'transform 0.2s',
  },
  taskHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '8px',
  },
  taskId: {
    fontFamily: 'monospace',
    color: '#888',
    fontSize: '12px',
  },
  statusBadge: {
    padding: '2px 8px',
    borderRadius: '10px',
    fontSize: '10px',
    fontWeight: 'bold',
    color: '#000',
    textTransform: 'uppercase',
  },
  description: {
    fontSize: '14px',
    marginBottom: '10px',
    lineHeight: '1.4',
  },
  details: {
    fontSize: '12px',
    color: '#ccc',
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    padding: '8px',
    borderRadius: '4px',
  },
  detailRow: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: '4px',
  },
  reward: {
    color: '#ffd700',
    fontWeight: 'bold',
  },
  solution: {
    marginTop: '8px',
    paddingTop: '8px',
    borderTop: '1px solid rgba(255, 255, 255, 0.1)',
    fontFamily: 'monospace',
    color: '#00ff88',
    wordBreak: 'break-all',
  },
  timestamp: {
    fontSize: '10px',
    color: '#666',
    marginTop: '8px',
    textAlign: 'right',
  },
  emptyState: {
    textAlign: 'center',
    color: '#666',
    marginTop: '50px',
    fontStyle: 'italic',
  }
};

export default TaskHistory;
