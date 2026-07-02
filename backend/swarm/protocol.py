"""
Swarm orchestrator that manages all agents.

This is the central controller that:
- Initializes all agents
- Routes messages between agents
- Monitors swarm health
- Provides statistics for visualization
"""

import asyncio
import os
from typing import List, Dict, Optional
from collections import deque
import time

from backend.agents.base_agent import BaseAgent
from backend.agents.coordinator_agent import CoordinatorAgent
from backend.agents.solver_agent import SolverAgent
from backend.kcore.wallet import KaspaWallet
from backend.kcore.transaction import SwarmMessage, MessageType
from backend.kcore.chain_watcher import ChainWatcher
from backend.kcore.covenant import InProtocolEscrow


class SwarmOrchestrator:
    """
    Manages the entire swarm of agents.
    
    In mock mode, handles message routing internally instead of using blockchain.
    """
    
    def __init__(
        self,
        wallet: KaspaWallet,
        num_coordinators: int = 2,
        num_solvers: int = 8,
        mock_mode: bool = True
    ):
        self.wallet = wallet
        self.agents: List[BaseAgent] = []
        self.num_coordinators = num_coordinators
        self.num_solvers = num_solvers
        self.mock_mode = mock_mode
        self.running = False
        self.transaction_history = deque(maxlen=30)  # Last 30 transactions
        self.task_history: List[Dict] = []  # Recent tasks (bounded by max_task_history)
        self.task_index: Dict[int, Dict] = {}  # task_id -> entry, for O(1) lookup
        self.max_task_history = 200
        
        # Message routing for mock mode
        self.message_relay_enabled = mock_mode
        # Live mode: the SDK transport (preferred) or ChainWatcher delivers
        # messages decoded from real blocks.
        self.chain_watcher: Optional[ChainWatcher] = None
        self.sdk = None  # SdkTransport in live mode
        # Escrow / stake-slash layer. Default = fast in-protocol bookkeeping.
        # COVENANT_ESCROW=true routes each task's reward through a REAL per-task
        # KIP-10 covenant on testnet-10 (settle -> solver / refund -> coordinator),
        # at the cost of a funding + confirmation tx per task.
        if not mock_mode and os.getenv("COVENANT_ESCROW", "false").lower() == "true":
            from backend.kcore.covenant import CovenantEscrow
            self.escrow = CovenantEscrow()
            print("🛡️ Settlement backend: on-chain CovenantEscrow (per-task covenant)")
        else:
            self.escrow = InProtocolEscrow()
        
    def log_task_event(self, task_id: int, event: str, data: Dict):
        """Log task lifecycle events for history panel."""
        # Find existing task (O(1)) or create new entry
        task_entry = self.task_index.get(task_id)

        if not task_entry:
            task_entry = {
               "task_id": task_id,
                "status": event,
                "events": [],
                "created_at": time.time(),
            }
            self.task_history.append(task_entry)
            self.task_index[task_id] = task_entry
            # Bound memory: drop the oldest entry once over the cap
            if len(self.task_history) > self.max_task_history:
                oldest = self.task_history.pop(0)
                self.task_index.pop(oldest["task_id"], None)
        
        # Update task entry
        task_entry["status"] = event
        task_entry["events"].append({
            "type": event,
            "timestamp": time.time(),
            "data": data
        })
        
        # Store relevant metadata
        if event == "created":
            task_entry["description"] = data.get("description", "")
            task_entry["reward"] = data.get("reward", 0)
            task_entry["coordinator"] = data.get("coordinator", "")
            # Preserve a source already set by an earlier "created" event (e.g.
            # manual_task_creation tagging source="mcp"); the broadcast re-log
            # carries no source key and must not clobber it back to "auto".
            task_entry["source"] = data.get("source", task_entry.get("source", "auto"))
        elif event == "assigned":
            task_entry["assigned_to"] = data.get("solver", "")
            task_entry["bid_amount"] = data.get("bid_amount", 0)
        elif event == "completed":
            task_entry["solution"] = data.get("solution", 0)
            task_entry["completed_at"] = time.time()

        # Always surface a produced answer (even on a rejected/failed task) so the
        # UI can show what the agent actually output, not just paid-out work.
        if "solution" in data and data["solution"] not in (None, ""):
            task_entry["solution"] = data["solution"]
        
    async def initialize_swarm(self):
        """Create and initialize all agents."""
        print("🚀 Initializing KaspaSwarm...")
        print(f"   Mode: {'MOCK (Development)' if self.mock_mode else 'LIVE (Testnet)'}")
        print(f"   Coordinators: {self.num_coordinators}")
        print(f"   Solvers: {self.num_solvers}")
        print("=" * 60)
        
        # Create coordinator agents
        for i in range(self.num_coordinators):
            agent = CoordinatorAgent(
                wallet=self.wallet,
                agent_id=f"coordinator_{i}"
            )
            await agent.initialize()
            agent.orchestrator = self
            self.agents.append(agent)
        
        # Create solver agents with varying skill levels
        for i in range(self.num_solvers):
            # Distribute skill levels from 0.5 to 1.5
            skill = 0.5 + (i / max(self.num_solvers - 1, 1)) * 1.0
            agent = SolverAgent(
                wallet=self.wallet,
                agent_id=f"solver_{i}",
                skill_level=skill
            )
            await agent.initialize()
            agent.orchestrator = self
            self.agents.append(agent)
        
        print("=" * 60)
        print(f"✅ Swarm initialized: {len(self.agents)} agents ready")
        print("=" * 60)
    
    async def start_swarm(self):
        """Start all agents and the coordination transport."""
        self.running = True

        # Live mode: read coordination messages off the chain (Kaspa is the bus)
        # via the SDK transport (Resolver -> community node). Falls back to the
        # hand-rolled ChainWatcher if the SDK path can't start.
        if not self.mock_mode:
            try:
                from backend.kcore.sdk_transport import get_transport
                self.sdk = get_transport()
                await self.sdk.subscribe(self._on_chain_message)
            except Exception as e:
                print(f"⚠️ SDK transport subscribe failed ({e}); falling back to ChainWatcher")
                # Drop the dead SDK handle so stats + delivery dedup (base_agent
                # picks `sdk or chain_watcher`) use the live watcher, not the
                # half-connected transport that just failed to subscribe.
                try:
                    await self.sdk.close()
                except Exception:
                    pass
                self.sdk = None
                ws_url = os.getenv("KASPA_WS_URL", "ws://127.0.0.1:18210")
                self.chain_watcher = ChainWatcher(ws_url, self._on_chain_message)
                await self.chain_watcher.start()

        # Start all agent decision loops. (Mock-mode delivery happens synchronously
        # in BaseAgent.send_message -> deliver_message; no relay loop needed.)
        agent_tasks = [asyncio.create_task(agent.start()) for agent in self.agents]

        await asyncio.gather(*agent_tasks)

    def record_message(self, message: SwarmMessage, sender: BaseAgent,
                       tx_id: str = "", onchain: bool = False):
        """Record a message for the UI (history + lifecycle log).

        Always called at send time, regardless of transport, so the
        visualization reflects activity immediately. Delivery to recipients is
        separate (see deliver_message) and, in live mode, is driven by the
        ChainWatcher once the message is observed on-chain.
        """
        task_type = None
        if message.msg_type == MessageType.TASK_ANNOUNCEMENT:
            task_type = message.data.get("task_type")
            self.log_task_event(message.task_id, "created", {
                "description": message.data.get("description", ""),
                "reward": message.data.get("reward", 0),
                "task_type": message.data.get("task_type", ""),
                "coordinator": sender.state.agent_id
            })

        self.transaction_history.append({
            "timestamp": time.time(),
            "from": sender.state.agent_id,
            "from_address": sender.state.address.address if sender.state.address else "",
            "msg_type": message.msg_type.value,
            "task_id": message.task_id,
            "task_type": task_type,
            "tx_id": tx_id,
            "onchain": onchain,
        })

    async def deliver_message(self, message: SwarmMessage,
                              to_address: Optional[str] = None,
                              exclude_address: Optional[str] = None):
        """Route a message to the relevant agent(s) by type.

        Broadcasts (announcement) fan out by role; directed messages
        (assignment) are routed to the agent at `to_address`.
        """
        mt = message.msg_type

        if mt == MessageType.TASK_ANNOUNCEMENT:
            targets = [a for a in self.agents if a.state.role == "solver"]
        elif mt in (MessageType.TASK_BID, MessageType.SOLUTION_SUBMISSION):
            targets = [a for a in self.agents if a.state.role == "coordinator"]
        elif mt == MessageType.TASK_ASSIGNMENT:
            targets = [a for a in self.agents
                       if a.state.address and a.state.address.address == to_address]
        else:
            targets = []

        for agent in targets:
            addr = agent.state.address.address if agent.state.address else None
            if exclude_address and addr == exclude_address:
                continue
            await agent.receive_message(message)

    async def _on_chain_message(self, message: SwarmMessage, to_address: Optional[str]):
        """ChainWatcher callback: deliver a message decoded from a real block."""
        await self.deliver_message(message, to_address=to_address,
                                   exclude_address=message.sender)
    
    async def stop_swarm(self):
        """Stop all agents."""
        self.running = False
        if self.chain_watcher is not None:
            await self.chain_watcher.stop()
            self.chain_watcher = None
        if self.sdk is not None:
            await self.sdk.close()
            self.sdk = None
        for agent in self.agents:
            await agent.stop()
    
    def get_swarm_stats(self) -> Dict:
        """Get current swarm statistics for visualization."""
        coordinator_stats = [a.get_stats() for a in self.agents if a.state.role == "coordinator"]
        solver_stats = [a.get_stats() for a in self.agents if a.state.role == "solver"]
        
        total_active_tasks = sum(len(a.state.active_tasks) for a in self.agents)
        total_completed = sum(a.state.completed_tasks for a in self.agents)
        
        # Calculate global success rate based on task history
        completed_count = sum(1 for t in self.task_history if t.get("status") == "completed")
        failed_count = sum(1 for t in self.task_history if t.get("status") == "failed")
        total_finished = completed_count + failed_count
        
        success_rate = (completed_count / total_finished * 100) if total_finished > 0 else 0.0
        
        return {
            "timestamp": time.time(),
            "total_agents": len(self.agents),
            "coordinators_count": self.num_coordinators,
            "solvers_count": self.num_solvers,
            "active_tasks": total_active_tasks,
            "completed_tasks": total_completed,
            "success_rate": success_rate,
            "mode": "mock" if self.mock_mode else "live",
            "chain": (self.sdk.stats if self.sdk else (self.chain_watcher.stats if self.chain_watcher else None)),
            "escrow": self.escrow.stats(),
            "transactions": list(self.transaction_history),  # Last 30 transactions
            "task_history": self.task_history[-50:],  # Last 50 tasks
            "agents": {
                "coordinators": coordinator_stats,
                "solvers": solver_stats
            }
        }
    
    # Control methods
    async def pause(self):
        """Pause swarm operations (agents stay alive; decision loops idle)."""
        for agent in self.agents:
            agent.paused = True
        print("⏸️  Swarm paused")

    async def resume(self):
        """Resume swarm operations."""
        for agent in self.agents:
            agent.paused = False
        print("▶️  Swarm resumed")
    
    async def manual_task_creation(self, target: int, reward: int, task_type_str: str = "prime_finding", prompt: str = "", source: str = "ui"):
        """Manually create a task (for testing)."""
        # Find first coordinator
        coordinator = next((a for a in self.agents if a.state.role == "coordinator"), None)
        if coordinator:
            from backend.swarm.task_types import Task, TaskType
            import random
            
            try:
                task_type = TaskType(task_type_str)
            except ValueError:
                task_type = TaskType.PRIME_FINDING
                
            # Generate input data based on type
            input_data = {}
            description = ""
            
            if task_type == TaskType.PRIME_FINDING:
                input_data = {"target": target}
                description = f"Find largest prime less than {target}"
            elif task_type == TaskType.HASH_CRACKING:
                prefix = random.choice(["00", "000", "abc", "bad", "caf"])
                input_data = {"prefix": prefix}
                description = f"Crack SHA256 hash starting with '{prefix}'"
            elif task_type == TaskType.SORTING:
                # Keep arrays small — the full input rides on-chain in the tx
                # payload, and payload size drives tx mass/fee (matches the auto
                # generate_task path; larger sizes get the carrier tx rejected).
                array_size = max(10, min(target, 40))
                input_data = {"array": [random.randint(1, 1000) for _ in range(array_size)]}
                description = f"Sort array of {array_size} integers"
            elif task_type == TaskType.DATA_SEARCH:
                dataset_size = max(10, min(target, 40))  # small: rides on-chain
                dataset = [f"item_{i}" for i in range(dataset_size)]
                query = f"item_{random.randint(0, dataset_size-1)}"
                input_data = {"dataset": dataset, "query": query}
                description = f"Search for '{query}' in dataset"
            elif task_type == TaskType.AI_TASK:
                from backend.swarm.task_types import get_ai_prompt
                p = (prompt or "").strip() or get_ai_prompt()
                input_data = {"prompt": p}
                description = f"AI task: {p[:60]}{'…' if len(p) > 60 else ''}"

            task = Task(
                task_id=coordinator.next_task_id,
                description=description,
                task_type=task_type,
                input_data=input_data,
                reward=reward,
                deadline=time.time() + 30,
                coordinator_address=coordinator.state.address.address
            )
            coordinator.next_task_id += 1
            coordinator.active_tasks[task.task_id] = task
            
            # Log task creation
            self.log_task_event(task.task_id, "created", {
                "description": task.description,
                "reward": task.reward,
                "coordinator": coordinator.state.agent_id,
                "task_type": task_type.value,
                "source": source,
            })
            
            await coordinator.broadcast_task(task)
            asyncio.create_task(coordinator.handle_task_lifecycle(task))
            print(f"✅ Manually created task {task.task_id}")
            return {"status": "success", "task_id": task.task_id}

    async def add_agent(self, role: str, skill_level: float = 1.0):
        """Dynamically add a new agent to the swarm."""
        from backend.agents.coordinator_agent import CoordinatorAgent
        from backend.agents.solver_agent import SolverAgent

        agent_id = f"{role}_{int(time.time()*1000)}"

        # Share the swarm's wallet (same mode/node) like initialize_swarm does.
        if role == "coordinator":
            agent = CoordinatorAgent(self.wallet, agent_id)
        else:
            agent = SolverAgent(self.wallet, agent_id, skill_level)

        # CRITICAL: initialize() sets up the agent's address. Without it the agent
        # has no state.address and crashes (swallowed) the first time it tries to
        # bid/send — leaving it idle forever, never joining a coordinator.
        await agent.initialize()
        agent.orchestrator = self
        self.agents.append(agent)

        if role == "coordinator":
            self.num_coordinators += 1
        else:
            self.num_solvers += 1

        # Start agent loop
        asyncio.create_task(agent.start())
        print(f"➕ Added new agent: {agent_id} (Role: {role}, Skill: {skill_level})")
        return agent_id

    async def remove_agent(self, agent_id: str):
        """Dynamically remove an agent from the swarm."""
        agent = next((a for a in self.agents if a.state.agent_id == agent_id), None)
        if not agent:
            print(f"❌ Cannot remove agent {agent_id}: Not found")
            return False
            
        # Stop agent
        await agent.stop()
        self.agents.remove(agent)
        
        if agent.state.role == "coordinator":
            self.num_coordinators -= 1
        else:
            self.num_solvers -= 1
            
        print(f"➖ Removed agent: {agent_id}")
        return True
    
    def _find_agent(self, address: str):
        for agent in self.agents:
            if agent.state.address and agent.state.address.address == address:
                return agent
        return None

    def get_reputation(self, address: str) -> float:
        """Authoritative reputation for an address. Unknown/external addresses get
        LOW trust (not the 100 baseline), so a spoofed or removed sender can't win
        the reputation-weighted auction by being unrecognized."""
        agent = self._find_agent(address)
        if not agent:
            return 1.0
        return float(getattr(agent, "reputation", 100.0))

    def adjust_reputation(self, address: str, delta: float):
        """Adjust a solver's reputation by address (reward on success, slash on fail)."""
        agent = self._find_agent(address)
        if agent and hasattr(agent, "reputation"):
            agent.reputation = max(0.0, min(200.0, agent.reputation + delta))
            tag = "📈" if delta >= 0 else "📉"
            print(f"{tag} Reputation of {agent.state.agent_id}: {agent.reputation:.0f} ({'+' if delta>=0 else ''}{delta})")

    def credit_solution(self, address: str):
        """Credit a solver's verified-and-paid work (stats reflect real success)."""
        agent = self._find_agent(address)
        if agent:
            agent.state.completed_tasks += 1
            agent.state.successful_bids += 1

    async def set_task_frequency(self, min_interval: float, max_interval: float):
        """Adjust task creation frequency."""
        for agent in self.agents:
            if hasattr(agent, 'min_interval'):
                agent.min_interval = min_interval
                agent.max_interval = max_interval
        print(f"⏱️  Task frequency: {min_interval}-{max_interval}s")
    
    async def reset_swarm(self):
        """Reset swarm state."""
        print("🔄 Resetting swarm...")
        # Clear task history
        self.task_history.clear()
        self.transaction_history.clear()
        
        # Reset agent states
        for agent in self.agents:
            agent.state.completed_tasks = 0
            agent.state.total_earnings = 0
            agent.state.total_bids = 0
            agent.state.successful_bids = 0
            if hasattr(agent, 'active_tasks'):
                agent.active_tasks.clear()
        
        print("✅ Swarm reset complete")
