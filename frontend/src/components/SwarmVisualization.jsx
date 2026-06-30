import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';

export default function SwarmVisualization({ swarmData }) {
  const containerRef = useRef();
  const sceneRef = useRef();
  const cameraRef = useRef();
  const rendererRef = useRef();
  const composerRef = useRef();
  const agentMeshesRef = useRef({});
  const transactionEdgesRef = useRef([]);
  const processedTxRef = useRef(new Set()); // O(1) dedup of already-rendered txs
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
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    containerRef.current.appendChild(renderer.domElement);

    // Bloom post-processing for a neon "command-center" glow.
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(window.innerWidth, window.innerHeight),
      0.85,  // strength
      0.5,   // radius
      0.55   // threshold (lower = more elements glow)
    );
    composer.addPass(bloomPass);
    composerRef.current = composer;

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

    // Subtle floor grid — dim, no harsh bright-green axes; fades into the dark.
    const gridHelper = new THREE.GridHelper(160, 40, 0x1e4736, 0x141821);
    gridHelper.position.y = -5;
    gridHelper.material.transparent = true;
    gridHelper.material.opacity = 0.28;
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

      // Update transaction edges - advance particles and fade out old ones.
      // Iterate backwards so removals don't shift indices we still need to visit.
      const now = Date.now();
      const maxAge = 3000; // 3 seconds
      for (let i = transactionEdgesRef.current.length - 1; i >= 0; i--) {
        const edge = transactionEdgesRef.current[i];
        const age = now - edge.timestamp;

        // Advance particle along the curve inside the single main loop
        if (edge.particles && edge.curve && edge.progress < 1) {
          edge.progress = Math.min(1, edge.progress + 0.02);
          const point = edge.curve.getPoint(edge.progress);
          edge.particles.position.copy(point);
        }

        if (age > maxAge) {
          scene.remove(edge.line);
          edge.line.geometry?.dispose();
          edge.line.material?.dispose();
          if (edge.particles) {
            scene.remove(edge.particles);
            edge.particles.geometry?.dispose();
            edge.particles.material?.dispose();
          }
          transactionEdgesRef.current.splice(i, 1);
        } else {
          // Fade out
          const opacity = 1 - (age / maxAge);
          edge.line.material.opacity = opacity;
          if (edge.particles) {
            edge.particles.material.opacity = opacity * 0.8;
          }
        }
      }

      composer.render();
    };
    animate();

    // Handle resize
    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
      composer.setSize(window.innerWidth, window.innerHeight);
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
      // Release GPU resources so remounts (HMR/route changes) don't leak WebGL
      // contexts or the bloom pass's render targets.
      composer.dispose?.();
      renderer.dispose();
      renderer.forceContextLoss?.();
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

    // Precompute each agent's index within its role group once — O(1) lookups
    // below instead of findIndex per agent (which made the loop O(n^2)).
    const idxMap = new Map();
    coordinators.forEach((a, i) => idxMap.set(a.agent_id, i));
    solvers.forEach((a, i) => idxMap.set(a.agent_id, i));

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
        sprite.scale.set(5, 1.25, 1);
        sprite.position.y = 3.6;
        sprite.material.depthWrite = false;
        sprite.material.opacity = 0.85;
        mesh.add(sprite);

        scene.add(mesh);
        agentMeshesRef.current[agentId] = mesh;
      }

      // Re-distribute positions on every update so the ring stays evenly spaced
      // when agents are added/removed (otherwise a new agent lands on top of an
      // existing one instead of redistributing the circle).
      const roleArr = agent.role === 'coordinator' ? coordinators : solvers;
      const radius = agent.role === 'coordinator' ? 15 : 25;
      const angleOffset = agent.role === 'coordinator' ? 0 : Math.PI / 4;
      const agentIndex = idxMap.get(agentId) ?? 0;
      const angle = (agentIndex / Math.max(roleArr.length, 1)) * Math.PI * 2 + angleOffset;
      mesh.position.x = Math.cos(angle) * radius;
      mesh.position.z = Math.sin(angle) * radius;
      mesh.position.y = 0;

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

    });

    // Reconcile: remove meshes for agents that no longer exist (after Terminate/Reset)
    const currentAgentIds = new Set(allAgents.map((a) => a.agent_id));
    Object.keys(agentMeshesRef.current).forEach((agentId) => {
      if (currentAgentIds.has(agentId)) return;

      const mesh = agentMeshesRef.current[agentId];
      if (!mesh) {
        delete agentMeshesRef.current[agentId];
        return;
      }

      // Dispose child decorations (ring + label sprite) attached to the mesh
      mesh.children.slice().forEach((child) => {
        mesh.remove(child);
        child.geometry?.dispose();
        // Sprite labels carry a CanvasTexture on material.map
        child.material?.map?.dispose();
        child.material?.dispose();
      });

      scene.remove(mesh);
      mesh.geometry?.dispose();
      mesh.material?.dispose();

      delete agentMeshesRef.current[agentId];
    });
  }, [swarmData]);

  // Highlight the selected agent without re-running the heavy reconcile above.
  // (Non-selected meshes are restored by the next swarmData update's active/idle
  // pass, so no explicit reset is needed here.)
  useEffect(() => {
    if (!selectedAgent) return;
    const mesh = agentMeshesRef.current[selectedAgent.agent_id];
    if (!mesh) return;
    mesh.material.emissiveIntensity = 0.8;
    if (mesh.userData.ring) mesh.userData.ring.material.opacity = 0.8;
  }, [selectedAgent]);

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

      // O(1) dedup: skip transactions we've already rendered (was an O(n) scan of
      // all live edges per tx -> quadratic during bursts).
      const txKey = `${txTimestamp}|${tx.from}`;
      if (processedTxRef.current.has(txKey)) return;
      processedTxRef.current.add(txKey);
      if (processedTxRef.current.size > 5000) processedTxRef.current.clear();

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

        // Particle progress is advanced inside the single main animate() loop
        // (see transaction-edge handling there) rather than its own RAF chain.
        transactionEdgesRef.current.push({
          line: tubeMesh,
          particles: particle,
          curve: curve,
          progress: 0,
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
    position: 'fixed',
    top: '20px',
    left: '50%',
    transform: 'translateX(-50%)',
    background: 'rgba(17, 19, 24, 0.95)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(0, 255, 136, 0.25)',
    borderRadius: '14px',
    padding: '20px',
    minWidth: '320px',
    maxWidth: 'min(420px, calc(100vw - 760px))',
    color: '#f3f5f8',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    zIndex: 2500,
    boxShadow: '0 16px 48px rgba(0, 0, 0, 0.6)',
  },
  infoPanelHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '16px',
    paddingBottom: '12px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.10)',
  },
  roleBadge: {
    padding: '4px 12px',
    borderRadius: '12px',
    fontSize: '11px',
    fontWeight: 700,
    color: '#06140d',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  agentId: {
    flex: 1,
    fontSize: '16px',
    fontWeight: 600,
    color: '#f3f5f8',
  },
  closeBtn: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    border: 'none',
    background: 'rgba(255, 255, 255, 0.1)',
    color: '#f3f5f8',
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
    gap: '12px',
  },
  infoRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoLabel: {
    fontSize: '13px',
    color: '#9aa4b2',
  },
  infoValue: {
    fontSize: '14px',
    fontWeight: 600,
    color: '#f3f5f8',
    fontVariantNumeric: 'tabular-nums',
  },
  taskInfo: {
    marginTop: '12px',
    padding: '12px',
    background: 'rgba(0, 255, 136, 0.10)',
    borderRadius: '8px',
    border: '1px solid rgba(0, 255, 136, 0.2)',
  },
  taskHeader: {
    fontSize: '11px',
    color: '#00ff88',
    fontWeight: 700,
    letterSpacing: '0.5px',
    textTransform: 'uppercase',
    marginBottom: '6px',
  },
  taskDescription: {
    fontSize: '13px',
    color: '#f3f5f8',
    lineHeight: 1.4,
  },
  killButton: {
    width: '100%',
    padding: '10px',
    marginTop: '12px',
    background: 'rgba(255, 68, 68, 0.15)',
    border: '1px solid rgba(255, 68, 68, 0.3)',
    borderRadius: '10px',
    color: '#ff6b6b',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
};
