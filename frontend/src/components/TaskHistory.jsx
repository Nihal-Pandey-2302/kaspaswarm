import React, { useState, useEffect } from 'react';

const TaskHistory = ({ tasks, onClose }) => {
  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.container} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
        <h2 style={styles.title}>Task History</h2>
        <button onClick={onClose} className="ks-icon-btn" style={styles.closeBtn}>×</button>
      </div>

      <div style={styles.content} className="ks-scroll">
        {tasks && tasks.length > 0 ? (
          [...tasks].reverse().map((task) => (
            <div key={task.task_id} style={styles.taskCard} className="ks-list-item">
              <div style={styles.taskHeader}>
                <span style={styles.taskId}>#{task.task_id}</span>
                <span style={styles.headRight}>
                  {task.source === 'mcp' && <span style={styles.mcpBadge}>🔌 via MCP</span>}
                  <span style={{
                    ...styles.statusBadge,
                    backgroundColor: getStatusColor(task.status)
                  }}>
                    {task.status}
                  </span>
                </span>
              </div>
              
              <div style={styles.description}>{task.description}</div>
              
              <div style={styles.details}>
                <div style={styles.detailRow}>
                  <span>Reward:</span>
                  <span style={styles.reward}>{kas(task.reward)}</span>
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
                    <span>{task.assigned_to.split('_')[1] || task.assigned_to.slice(-6)}</span>
                  </div>
                )}

                {task.bid_amount ? (
                  <div style={styles.detailRow}>
                    <span>Winning bid:</span>
                    <span style={styles.reward}>{kas(task.bid_amount)}</span>
                  </div>
                ) : null}
                
                {task.solution !== undefined && task.solution !== null && task.solution !== '' && (
                  <div style={styles.solution}>
                    <div style={styles.solutionLabel}>
                      {task.task_type === 'ai_task' ? '🤖 Agent answer' : 'Solution'}
                    </div>
                    <div style={styles.solutionText}>{String(task.solution)}</div>
                  </div>
                )}
              </div>
              
              <div style={styles.timestamp}>
                {new Date(task.created_at * 1000).toLocaleTimeString()}
              </div>
            </div>
          ))
        ) : (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>📜</div>
            <div>No tasks recorded yet</div>
          </div>
        )}
        </div>
      </div>
    </div>
  );
};

// Helper functions
const kas = (sompi) => `${(Number(sompi || 0) / 1e8).toFixed(3)} KAS`;

const getStatusColor = (status) => {
  switch (status) {
    case 'created': return '#4f9eff'; // Blue
    case 'assigned': return '#ffaa00'; // Orange
    case 'completed': return '#00ff88'; // Green
    case 'rejected': return '#ff8800'; // Amber — answer produced but failed verification
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
    case 'ai_task': return '🤖';
    default: return '📝';
  }
};

const styles = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 3000,
    background: 'rgba(3, 5, 8, 0.6)',
    backdropFilter: 'blur(2px)',
    padding: '20px',
    boxSizing: 'border-box',
    animation: 'ks-fade-in 0.18s ease',
  },
  container: {
    width: '420px',
    maxWidth: 'calc(100vw - 40px)',
    height: '80vh',
    maxHeight: '80vh',
    backgroundColor: 'rgba(17, 19, 24, 0.97)',
    border: '1px solid rgba(255, 255, 255, 0.10)',
    borderRadius: '16px',
    display: 'flex',
    flexDirection: 'column',
    backdropFilter: 'blur(12px)',
    boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    color: '#f3f5f8',
    overflow: 'hidden',
  },
  header: {
    padding: '20px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.10)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: 'rgba(0, 0, 0, 0.2)',
  },
  title: {
    margin: 0,
    fontSize: '13px',
    fontWeight: 700,
    color: '#00ff88',
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#9aa4b2',
    fontSize: '22px',
    lineHeight: 1,
    cursor: 'pointer',
    opacity: 0.8,
    width: '30px',
    height: '30px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px',
  },
  taskCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderRadius: '12px',
    padding: '14px',
    marginBottom: '12px',
    border: '1px solid rgba(255, 255, 255, 0.08)',
  },
  taskHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '8px',
  },
  taskId: {
    fontFamily: 'monospace',
    color: '#9aa4b2',
    fontSize: '12px',
    fontWeight: 600,
  },
  headRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  mcpBadge: {
    fontSize: '9px',
    fontWeight: 700,
    color: '#4f9eff',
    background: 'rgba(79,158,255,0.12)',
    border: '1px solid rgba(79,158,255,0.35)',
    borderRadius: '20px',
    padding: '2px 7px',
  },
  statusBadge: {
    padding: '3px 9px',
    borderRadius: '20px',
    fontSize: '9px',
    fontWeight: 700,
    letterSpacing: '0.5px',
    color: '#06140d',
    textTransform: 'uppercase',
  },
  description: {
    fontSize: '14px',
    marginBottom: '10px',
    lineHeight: '1.4',
    color: '#f3f5f8',
  },
  details: {
    fontSize: '12px',
    color: '#9aa4b2',
    backgroundColor: 'rgba(0, 0, 0, 0.25)',
    padding: '10px',
    borderRadius: '8px',
  },
  detailRow: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: '5px',
  },
  reward: {
    color: '#ffc94d',
    fontWeight: 700,
  },
  solution: {
    marginTop: '8px',
    paddingTop: '8px',
    borderTop: '1px solid rgba(255, 255, 255, 0.10)',
  },
  solutionLabel: {
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '0.5px',
    textTransform: 'uppercase',
    color: '#7d8794',
    marginBottom: '4px',
  },
  solutionText: {
    fontSize: '12px',
    color: '#00ff88',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    maxHeight: '160px',
    overflowY: 'auto',
  },
  timestamp: {
    fontSize: '10px',
    color: '#7d8794',
    marginTop: '8px',
    textAlign: 'right',
  },
  emptyState: {
    textAlign: 'center',
    color: '#9aa4b2',
    marginTop: '60px',
    fontSize: '13px',
  },
  emptyIcon: {
    fontSize: '32px',
    opacity: 0.25,
    marginBottom: '12px',
  },
};

export default TaskHistory;
