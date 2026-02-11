import React, { useEffect, useRef } from 'react';
import Chart from 'chart.js/auto';

const PerformanceCharts = ({ taskHistory, onClose }) => {
  const chart1Ref = useRef(null);
  const chart2Ref = useRef(null);
  const chartInstance1 = useRef(null);
  const chartInstance2 = useRef(null);

  // Process data for charts
  useEffect(() => {
    if (!taskHistory) return;

    // --- Chart 1: Tasks per Minute ---
    const taskCounts = {};
    const now = Date.now() / 1000;
    
    for (let i = 9; i >= 0; i--) {
      const t = Math.floor((now - i * 60) / 60) * 60;
      const timeLabel = new Date(t * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
      taskCounts[timeLabel] = 0;
    }

    taskHistory.forEach(task => {
      const t = Math.floor(task.created_at / 60) * 60;
      const timeLabel = new Date(t * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
      if (taskCounts[timeLabel] !== undefined) {
        taskCounts[timeLabel]++;
      }
    });

    // --- Chart 2: Success vs Fail Rate ---
    let completed = 0;
    let failed = 0;
    taskHistory.forEach(task => {
      if (task.status === 'completed') completed++;
      if (task.status === 'failed') failed++;
    });

    // Destroy existing charts if canvas is missing or we need full re-init
    // Note: updating existing instances is better for performance, but dangerous if refs change
    
    // --- Chart 1 ---
    if (chartInstance1.current) {
        // Safe update
        if (chart1Ref.current) {
             chartInstance1.current.data.labels = Object.keys(taskCounts);
             chartInstance1.current.data.datasets[0].data = Object.values(taskCounts);
             chartInstance1.current.update('none');
        } else {
            chartInstance1.current.destroy();
            chartInstance1.current = null;
        }
    } 
    
    if (!chartInstance1.current && chart1Ref.current) {
      chartInstance1.current = new Chart(chart1Ref.current, {
        type: 'line',
        data: {
          labels: Object.keys(taskCounts),
          datasets: [{
            label: 'Tasks Created',
            data: Object.values(taskCounts),
            borderColor: '#00ff88',
            tension: 0.4,
            fill: true,
            backgroundColor: 'rgba(0, 255, 136, 0.1)'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: { legend: { labels: { color: '#fff' } } },
          scales: {
            x: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.1)' } },
            y: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.1)' }, beginAtZero: true }
          }
        }
      });
    }

    // --- Chart 2 ---
    if (chartInstance2.current) {
         if (chart2Ref.current) {
            chartInstance2.current.data.datasets[0].data = [completed, failed, taskHistory.length - completed - failed];
            chartInstance2.current.update('none');
         } else {
             chartInstance2.current.destroy();
             chartInstance2.current = null;
         }
    } 
    
    if (!chartInstance2.current && chart2Ref.current) {
      chartInstance2.current = new Chart(chart2Ref.current, {
        type: 'doughnut',
        data: {
          labels: ['Completed', 'Failed', 'Active'],
          datasets: [{
            data: [completed, failed, taskHistory.length - completed - failed],
            backgroundColor: ['#00ff88', '#ff4444', '#00aaff'],
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: { legend: { position: 'right', labels: { color: '#fff' } } }
        }
      });
    }

  }, [taskHistory]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (chartInstance1.current) {
          chartInstance1.current.destroy();
          chartInstance1.current = null;
      }
      if (chartInstance2.current) {
          chartInstance2.current.destroy();
          chartInstance2.current = null;
      }
    };
  }, []);

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h2 style={styles.title}>Swarm Performance</h2>
        <button onClick={onClose} style={styles.closeBtn}>×</button>
      </div>
      
      <div style={styles.content}>
        <div style={styles.chartContainer}>
          <h3 style={styles.chartTitle}>Activity (Last 10 min)</h3>
          <div style={{ height: '200px' }}>
            <canvas ref={chart1Ref} />
          </div>
        </div>
        
        <div style={styles.chartContainer}>
          <h3 style={styles.chartTitle}>Task Outcomes</h3>
          <div style={{ height: '180px' }}>
            <canvas ref={chart2Ref} />
          </div>
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    position: 'absolute',
    bottom: '20px',
    left: '20px', 
    width: '400px',
    height: 'auto',
    maxHeight: '600px',
    backgroundColor: 'rgba(10, 15, 20, 0.95)',
    border: '1px solid rgba(0, 255, 136, 0.2)',
    borderRadius: '12px',
    display: 'flex',
    flexDirection: 'column',
    zIndex: 2000,
    backdropFilter: 'blur(10px)',
    boxShadow: '0 5px 20px rgba(0,0,0,0.5)',
  },
  header: {
    padding: '15px 20px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: 'rgba(0, 0, 0, 0.2)',
    borderTopLeftRadius: '12px',
    borderTopRightRadius: '12px',
  },
  title: {
    margin: 0,
    fontSize: '16px',
    fontWeight: '600',
    color: '#00aaff',
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
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  chartContainer: {
    background: 'rgba(255, 255, 255, 0.03)',
    borderRadius: '8px',
    padding: '10px',
  },
  chartTitle: {
    color: '#888',
    fontSize: '12px',
    margin: '0 0 10px 0',
    textTransform: 'uppercase',
  }
};

export default PerformanceCharts;
