"""
FastAPI WebSocket server for real-time swarm visualization.

Provides:
- WebSocket endpoint for real-time updates
- REST API for swarm stats
- Health check endpoints
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import json
from typing import List
import os

from backend.swarm.protocol import SwarmOrchestrator
from backend.kaspa.wallet import KaspaWallet


app = FastAPI(
    title="KaspaSwarm API",
    description="Decentralized AI Agent Coordination on Kaspa Blockchain",
    version="1.0.0"
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🔌 WebSocket client connected (total: {len(self.active_connections)})")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"🔌 WebSocket client disconnected (total: {len(self.active_connections)})")
    
    async def broadcast(self, message: str):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)


class SwarmBroadcaster:
    """Broadcasts swarm state to all connected clients."""
    
    def __init__(self, orchestrator: SwarmOrchestrator, manager: ConnectionManager):
        self.orchestrator = orchestrator
        self.manager = manager
        self.running = False
        
    async def broadcast_loop(self):
        """Continuously broadcast swarm state."""
        self.running = True
        
        while self.running:
            if self.manager.active_connections:
                stats = self.orchestrator.get_swarm_stats()
                message = json.dumps({
                    "type": "swarm_update",
                    "data": stats
                })
                
                await self.manager.broadcast(message)
            
            await asyncio.sleep(0.5)  # 2 updates per second
    
    def stop(self):
        """Stop broadcasting."""
        self.running = False


# Global instances
wallet = None
orchestrator = None
broadcaster = None
manager = ConnectionManager()


@app.get("/api/address")
async def get_coordinator_address():
    """Get the current coordinator address for funding."""
    address = os.getenv("COORDINATOR_ADDRESS", "Not Configured")
    return {"address": address}

@app.get("/api/coordinator-balance")
async def get_coordinator_balance():
    """Get the coordinator's balance from the swarm state."""
    try:
        if orchestrator:
            for agent in orchestrator.agents:
                if agent.state.role == "coordinator" and agent.state.address:
                    balance_sompi = agent.state.address.balance
                    balance_kas = balance_sompi / 100_000_000
                    return {"balance": balance_sompi, "balance_kas": f"{balance_kas:.2f}"}
    except Exception:
        pass
    return {"balance": 0, "balance_kas": "0.00"}

@app.on_event("startup")
async def startup():
    """Initialize swarm on startup."""
    global wallet, orchestrator, broadcaster
    
    # Get configuration from environment
    mock_mode = os.getenv("MOCK_MODE", "true").lower() == "true"
    num_coordinators = int(os.getenv("NUM_COORDINATORS", "2"))
    num_solvers = int(os.getenv("NUM_SOLVERS", "8"))
    rpc_url = os.getenv("KASPA_RPC_URL", "https://api.kaspa.org")
    
    # Initialize wallet
    wallet = KaspaWallet(rpc_url=rpc_url, mock_mode=mock_mode)
    
    # Initialize orchestrator
    orchestrator = SwarmOrchestrator(
        wallet=wallet,
        num_coordinators=num_coordinators,
        num_solvers=num_solvers,
        mock_mode=mock_mode
    )
    
    await orchestrator.initialize_swarm()
    
    # Start swarm in background
    asyncio.create_task(orchestrator.start_swarm())
    
    # Start broadcaster
    broadcaster = SwarmBroadcaster(orchestrator, manager)
    asyncio.create_task(broadcaster.broadcast_loop())
    
    print("🌐 API server ready at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    """Clean shutdown."""
    global orchestrator, broadcaster, wallet
    
    if broadcaster:
        broadcaster.stop()
    
    if orchestrator:
        await orchestrator.stop_swarm()
    
    if wallet:
        await wallet.close()


@app.get("/")
async def root():
    """API status."""
    return {
        "status": "running",
        "service": "KaspaSwarm API",
        "version": "1.0.0",
        "endpoints": {
            "websocket": "/ws",
            "stats": "/stats",
            "health": "/health"
        }
    }


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "swarm_running": orchestrator.running if orchestrator else False,
        "connected_clients": len(manager.active_connections)
    }


@app.get("/stats")
async def get_stats():
    """Get current swarm statistics."""
    if not orchestrator:
        return JSONResponse(
            status_code=503,
            content={"error": "Swarm not initialized"}
        )
    
    return orchestrator.get_swarm_stats()


@app.post("/control/pause")
async def pause_swarm():
    """Pause all agent activities."""
    if not orchestrator:
        return JSONResponse(
            status_code=503,
            content={"error": "Swarm not initialized"}
        )
    
    orchestrator.pause_swarm()
    return {"status": "paused"}


@app.post("/control/resume")
async def resume_swarm():
    """Resume all agent activities."""
    if not orchestrator:
        return JSONResponse(
            status_code=503,
            content={"error": "Swarm not initialized"}
        )
    
    orchestrator.resume_swarm()
    return {"status": "resumed"}


@app.post("/control/create-task")
async def create_task(target: int, reward: int, task_type: str = "prime_finding"):
    """Manually create a task."""
    if not orchestrator:
        return JSONResponse(
            status_code=503,
            content={"error": "Swarm not initialized"}
        )
    
    if task_type not in ["prime_finding", "hash_cracking", "sorting", "data_search"]:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid task type"}
        )
    
    result = await orchestrator.manual_task_creation(target, reward, task_type)
    return result


@app.post("/control/frequency")
async def set_frequency(min_interval: float = 5.0, max_interval: float = 15.0):
    """Set task creation frequency."""
    if not orchestrator:
        return JSONResponse(
            status_code=503,
            content={"error": "Swarm not initialized"}
        )
    
    orchestrator.set_task_frequency(min_interval, max_interval)
    return {"status": "updated", "min": min_interval, "max": max_interval}


@app.post("/control/reset")
async def reset_swarm():
    """Reset the swarm."""
    if not orchestrator:
        return JSONResponse(
            status_code=503,
            content={"error": "Swarm not initialized"}
        )
    
    await orchestrator.reset_swarm()
    return {"status": "reset"}


@app.post("/control/add-agent")
async def add_agent(data: dict):
    """Add a new agent to the swarm."""
    if not orchestrator:
        return JSONResponse(status_code=503, content={"error": "Swarm not initialized"})
        
    role = data.get("role", "solver")
    skill = float(data.get("skill", 1.0))
    agent_id = await orchestrator.add_agent(role, skill)
    return {"status": "success", "agent_id": agent_id}


@app.post("/control/remove-agent")
async def remove_agent(data: dict):
    """Remove an agent from the swarm."""
    if not orchestrator:
        return JSONResponse(status_code=503, content={"error": "Swarm not initialized"})
        
    agent_id = data.get("agent_id")
    success = await orchestrator.remove_agent(agent_id)
    return {"status": "success" if success else "failed"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    
    try:
        # Send initial state
        if orchestrator:
            stats = orchestrator.get_swarm_stats()
            await websocket.send_text(json.dumps({
                "type": "initial_state",
                "data": stats
            }))
        
        # Keep connection alive
        while True:
            try:
                # Receive messages from client (for future interactive features)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo for now
                await websocket.send_text(json.dumps({
                    "type": "echo",
                    "data": data
                }))
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping"}))
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port)
