import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

export default function SwarmVisualization({ swarmData }) {
  const containerRef = useRef();
  const sceneRef = useRef();
  const cameraRef = useRef();
  const rendererRef = useRef();
  const agentMeshesRef = useRef({});
  const transactionEdgesRef = useRef([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const raycasterRef = useRef(new THREE.Raycaster());
  const mouseRef = useRef(new THREE.Vector2());

  // Initialize scene once
  useEffect(() => {
    if (!containerRef.current) return;

    console.log('🎨 Initializing Three.js scene');

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a0a);
    scene.fog = new THREE.Fog(0x0a0a0a, 50, 200);

    // Camera with better positioning
    const camera = new THREE.PerspectiveCamera(
      60,
      window.innerWidth / window.innerHeight,
      0.1,
      1000
    );
    camera.position.set(0, 30, 50);
    camera.lookAt(0, 0, 0);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    containerRef.current.appendChild(renderer.domElement);

    // Better lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
    scene.add(ambientLight);

    const mainLight = new THREE.DirectionalLight(0xffffff, 0.8);
    mainLight.position.set(10, 20, 10);
    scene.add(mainLight);

    const fillLight = new THREE.DirectionalLight(0x00ff88, 0.3);
    fillLight.position.set(-10, 10, -10);
    scene.add(fillLight);

    const backLight = new THREE.PointLight(0x0088ff, 0.5);
    backLight.position.set(0, 10, -20);
    scene.add(backLight);

    // Grid for reference
    const gridHelper = new THREE.GridHelper(100, 20, 0x00ff88, 0x333333);
    gridHelper.position.y = -5;
    scene.add(gridHelper);

    // Store refs
    sceneRef.current = scene;
    cameraRef.current = camera;
    rendererRef.current = renderer;

    console.log('✅ Scene initialized');

    // Mouse click handler
    const handleClick = (event) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouseRef.current.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouseRef.current.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycasterRef.current.setFromCamera(mouseRef.current, camera);
      const intersects = raycasterRef.current.intersectObjects(
        Object.values(agentMeshesRef.current).filter(m => m),
        false
      );

      if (intersects.length > 0) {
        const clickedMesh = intersects[0].object;
        const agentData = clickedMesh.userData.agentData;
        
        console.log('🖱️ Clicked agent:', clickedMesh.userData.agentId, agentData);
        
        if (agentData) {
          setSelectedAgent(agentData);
        }
      } else {
        console.log('🖱️ Clicked empty space');
        setSelectedAgent(null);
      }
    };

    renderer.domElement.addEventListener('click', handleClick);

    // Animation loop
    let animationId;
    const animate = () => {
      animationId = requestAnimationFrame(animate);

      // Gentle camera rotation
      const time = Date.now() * 0.0001;
      camera.position.x = Math.sin(time) * 50;
      camera.position.z = Math.cos(time) * 50;
      camera.lookAt(0, 0, 0);

      // Update transaction edges - fade out old ones
      const now = Date.now();
      transactionEdgesRef.current.forEach((edge, index) => {
        const age = now - edge.timestamp;
        const maxAge = 3000; // 3 seconds
        
        if (age > maxAge) {
          scene.remove(edge.line);
          if (edge.particles) scene.remove(edge.particles);
          transactionEdgesRef.current.splice(index, 1);
        } else {
          // Fade out
          const opacity = 1 - (age / maxAge);
          edge.line.material.opacity = opacity;
          if (edge.particles) {
            edge.particles.material.opacity = opacity * 0.8;
          }
        }
      });

      renderer.render(scene, camera);
    };
    animate();

    // Handle resize
    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      console.log('🧹 Cleaning up scene');
      animationId && cancelAnimationFrame(animationId);
      window.removeEventListener('resize', handleResize);
      renderer.domElement.removeEventListener('click', handleClick);
      if (containerRef.current && containerRef.current.contains(renderer.domElement)) {
        containerRef.current.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Update agents
  useEffect(() => {
    if (!sceneRef.current || !swarmData?.agents) {
      return;
    }

    const scene = sceneRef.current;
    const coordinators = swarmData.agents.coordinators || [];
    const solvers = swarmData.agents.solvers || [];
    const allAgents = [...coordinators, ...solvers];

    allAgents.forEach((agent) => {
      const agentId = agent.agent_id;
      let mesh = agentMeshesRef.current[agentId];

      if (!mesh) {
        // Create agent spheres
        const geometry = new THREE.SphereGeometry(2, 32, 32);
        const material = new THREE.MeshPhongMaterial({
          color: agent.role === 'coordinator' ? 0x00ff88 : 0x0088ff,
          emissive: agent.role === 'coordinator' ? 0x00ff88 : 0x0088ff,
          emissiveIntensity: 0.3,
          shininess: 100,
        });
        mesh = new THREE.Mesh(geometry, material);

        // Position agents
        const radius = agent.role === 'coordinator' ? 15 : 25;
        const agentsInRole = agent.role === 'coordinator' ? coordinators.length : solvers.length;
        const angleOffset = agent.role === 'coordinator' ? 0 : Math.PI / 4;
        const agentIndex = agent.role === 'coordinator' 
          ? coordinators.findIndex(a => a.agent_id === agentId)
          : solvers.findIndex(a => a.agent_id === agentId);
        
        const angle = (agentIndex / agentsInRole) * Math.PI * 2 + angleOffset;
        mesh.position.x = Math.cos(angle) * radius;
        mesh.position.z = Math.sin(angle) * radius;
        mesh.position.y = 0;

        mesh.userData.agentId = agentId;
        mesh.userData.role = agent.role;

        // Add glow ring
        const ringGeometry = new THREE.RingGeometry(2.5, 3, 32);
        
        // Determine color based on specialization
        let ringColor = 0x00ff88; // Default Green (Prime)
        if (agent.specialization === 'hash_cracking') ringColor = 0x9d00ff; // Purple
        if (agent.specialization === 'sorting') ringColor = 0xffaa00; // Orange
        if (agent.specialization === 'data_search') ringColor = 0x00aaff; // Blue

        const ringMaterial = new THREE.MeshBasicMaterial({
          color: agent.role === 'coordinator' ? 0x00ff88 : ringColor,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0,
        });
        const ring = new THREE.Mesh(ringGeometry, ringMaterial);
        ring.rotation.x = -Math.PI / 2;
        ring.position.y = -1.9;
        mesh.add(ring);
        mesh.userData.ring = ring;

        // Add text label
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.width = 256;
        canvas.height = 64;
        context.fillStyle = '#ffffff';
        context.font = 'bold 24px Arial';
        context.textAlign = 'center';
        context.fillText(agentId, 128, 40);

        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
        const sprite = new THREE.Sprite(spriteMaterial);
        sprite.scale.set(8, 2, 1);
        sprite.position.y = 4;
        mesh.add(sprite);

        scene.add(mesh);
        agentMeshesRef.current[agentId] = mesh;
      }

      // Store current agent data
      mesh.userData.agentData = agent;

      // Animate based on activity and reputation
      const isActive = agent.active_tasks > 0 || agent.status === 'working';
      const reputationScale = agent.reputation ? Math.max(0.8, Math.min(2.0, agent.reputation / 100)) : 1.0;
      
      if (isActive) {
        const scale = (1 + Math.sin(Date.now() * 0.003) * 0.15) * reputationScale;
        mesh.scale.set(scale, scale, scale);
        mesh.material.emissiveIntensity = 0.4 + Math.sin(Date.now() * 0.005) * 0.2;
        
        if (mesh.userData.ring) {
          mesh.userData.ring.material.opacity = 0.3 + Math.sin(Date.now() * 0.005) * 0.2;
        }
      } else {
        const scale = 1.0 * reputationScale;
        mesh.scale.set(scale, scale, scale);
        mesh.material.emissiveIntensity = 0.1;
        if (mesh.userData.ring) {
          mesh.userData.ring.material.opacity = 0;
        }
      }

      // Highlight selected agent
      if (selectedAgent && selectedAgent.agent_id === agentId) {
        mesh.material.emissiveIntensity = 0.8;
        if (mesh.userData.ring) {
          mesh.userData.ring.material.opacity = 0.8;
        }
      }
    });
  }, [swarmData, selectedAgent]);

  // Update transaction edges
  useEffect(() => {
    if (!sceneRef.current || !swarmData?.transactions) {
      return;
    }

    const scene = sceneRef.current;
    const transactions = swarmData.transactions || [];

    // Process new transactions
    transactions.forEach((tx) => {
      const txTimestamp = tx.timestamp * 1000; // Convert to milliseconds
      
      // Check if we've already processed this transaction
      const alreadyExists = transactionEdgesRef.current.some(
        edge => edge.txTimestamp === txTimestamp && edge.from === tx.from
      );
      
      if (alreadyExists) return;

      // Get sender mesh
      const fromMesh = agentMeshesRef.current[tx.from];
      if (!fromMesh) return;

      // Determine color based on message type
      let color;
      switch (tx.msg_type) {
        case 'task_announcement':
          color = 0x00ff88; // Green
          break;
        case 'task_bid':
          color = 0x0088ff; // Blue
          break;
        case 'solution_submission':
          color = 0xff00ff; // Purple
          break;
        default:
          color = 0xffffff;
      }

      // For broadcast messages, create edges to all relevant agents
      let targetMeshes = [];
      
      if (tx.msg_type === 'task_announcement') {
        // To all solvers
        targetMeshes = Object.values(agentMeshesRef.current).filter(
          m => m.userData.agentData?.role === 'solver'
        );
      } else {
        // To coordinators
        targetMeshes = Object.values(agentMeshesRef.current).filter(
          m => m.userData.agentData?.role === 'coordinator' && m !== fromMesh
        );
      }

      // Create edge for each target
      targetMeshes.forEach(toMesh => {
        const points = [];
        points.push(fromMesh.position.clone());
        
        // Add arc midpoint for curved effect
        const midPoint = new THREE.Vector3()
          .addVectors(fromMesh.position, toMesh.position)
          .multiplyScalar(0.5);
        midPoint.y += 5; // Arc height
        points.push(midPoint);
        
        points.push(toMesh.position.clone());

        const curve = new THREE.CatmullRomCurve3(points);
        const tubeGeometry = new THREE.TubeGeometry(curve, 20, 0.1, 8, false);
        const material = new THREE.MeshBasicMaterial({
          color: color,
          transparent: true,
          opacity: 0.7,
        });
        
        const tubeMesh = new THREE.Mesh(tubeGeometry, material);
        scene.add(tubeMesh);

        // Add particle effect
        const particleGeometry = new THREE.SphereGeometry(0.3, 8, 8);
        const particleMaterial = new THREE.MeshBasicMaterial({
          color: color,
          transparent: true,
          opacity: 0.8,
        });
        const particle = new THREE.Mesh(particleGeometry, particleMaterial);
        particle.position.copy(fromMesh.position);
        scene.add(particle);

        // Animate particle along curve
        let progress = 0;
        const animateParticle = () => {
          if (progress < 1) {
            progress += 0.02;
            const point = curve.getPoint(progress);
            particle.position.copy(point);
            requestAnimationFrame(animateParticle);
          } else {
            scene.remove(particle);
          }
        };
        animateParticle();

        transactionEdgesRef.current.push({
          line: tubeMesh,
          particles: particle,
          timestamp: Date.now(),
          txTimestamp: txTimestamp,
          from: tx.from,
        });
      });
    });
  }, [swarmData?.transactions]);

  return (
    <>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      
      {/* Agent Info Panel */}
      {selectedAgent && (
        <div style={styles.infoPanel}>
          <div style={styles.infoPanelHeader}>
            <span style={{
              ...styles.roleBadge,
              background: selectedAgent.role === 'coordinator' 
                ? 'linear-gradient(135deg, #00ff88, #00cc70)' 
                : 'linear-gradient(135deg, #0088ff, #0066cc)'
            }}>
              {selectedAgent.role}
            </span>
            <span style={styles.agentId}>{selectedAgent.agent_id}</span>
            <button onClick={() => setSelectedAgent(null)} style={styles.closeBtn}>×</button>
          </div>
          
          <div style={styles.infoPanelContent}>
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Status:</span>
              <span style={styles.infoValue}>{selectedAgent.status || 'idle'}</span>
            </div>
            
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Active Tasks:</span>
              <span style={styles.infoValue}>{selectedAgent.active_tasks || 0}</span>
            </div>
            
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Completed:</span>
              <span style={styles.infoValue}>{selectedAgent.completed_tasks || 0}</span>
            </div>
            
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Balance:</span>
              <span style={styles.infoValue}>{selectedAgent.balance || 0} sompi</span>
            </div>
            
            {selectedAgent.role === 'solver' && selectedAgent.skill_level && (
              <div style={styles.infoRow}>
                <span style={styles.infoLabel}>Skill Level:</span>
                <span style={styles.infoValue}>{selectedAgent.skill_level.toFixed(2)}</span>
              </div>
            )}
            
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Reputation:</span>
              <span style={styles.infoValue}>{selectedAgent.reputation || 100}</span>
            </div>

            {selectedAgent.role === 'solver' && selectedAgent.specialization && (
              <div style={styles.infoRow}>
                <span style={styles.infoLabel}>Specialty:</span>
                <span style={styles.infoValue}>
                  {selectedAgent.specialization === 'prime_finding' && '🔢 Prime'}
                  {selectedAgent.specialization === 'hash_cracking' && '🔐 Hash'}
                  {selectedAgent.specialization === 'sorting' && '📊 Sort'}
                  {selectedAgent.specialization === 'data_search' && '🔍 Search'}
                </span>
              </div>
            )}
            
            {selectedAgent.current_task && (
              <div style={styles.taskInfo}>
                <div style={styles.taskHeader}>Current Task:</div>
                <div style={styles.taskDescription}>{selectedAgent.current_task}</div>
              </div>
            )}
            
            <button 
              onClick={async () => {
                if(confirm('Terminate this agent?')) {
                  await fetch('/api/control/remove-agent', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ agent_id: selectedAgent.agent_id })
                  });
                  setSelectedAgent(null);
                }
              }}
              style={styles.killButton}
            >
              💀 Terminate Agent
            </button>
          </div>
        </div>
      )}
    </>
  );
}

const styles = {
  infoPanel: {
    position: 'absolute',
    bottom: '20px',
    left: '20px',
    background: 'rgba(10, 10, 10, 0.95)',
    backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    borderRadius: '16px',
    padding: '20px',
    minWidth: '320px',
    color: '#fff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    zIndex: 1000,
  },
  infoPanelHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '16px',
    paddingBottom: '12px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
  },
  roleBadge: {
    padding: '4px 12px',
    borderRadius: '12px',
    fontSize: '11px',
    fontWeight: 'bold',
    color: '#000',
    textTransform: 'uppercase',
  },
  agentId: {
    flex: 1,
    fontSize: '16px',
    fontWeight: '600',
  },
  closeBtn: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    border: 'none',
    background: 'rgba(255, 255, 255, 0.1)',
    color: '#fff',
    fontSize: '20px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    lineHeight: '1',
  },
  infoPanelContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  infoRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoLabel: {
    fontSize: '13px',
    color: '#888',
  },
  infoValue: {
    fontSize: '14px',
    fontWeight: '600',
    color: '#fff',
  },
  taskInfo: {
    marginTop: '12px',
    padding: '12px',
    background: 'rgba(0, 255, 136, 0.1)',
    borderRadius: '8px',
    border: '1px solid rgba(0, 255, 136, 0.2)',
  },
  taskHeader: {
    fontSize: '12px',
    color: '#00ff88',
    fontWeight: '600',
    marginBottom: '6px',
  },
  taskDescription: {
    fontSize: '13px',
    color: '#fff',
  },
  killButton: {
    width: '100%',
    padding: '8px',
    marginTop: '12px',
    background: 'rgba(255, 68, 68, 0.1)',
    border: '1px solid rgba(255, 68, 68, 0.3)',
    borderRadius: '8px',
    color: '#ff4444',
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
};
