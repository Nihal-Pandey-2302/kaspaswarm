"""
Swarm orchestrator that manages all agents.

This is the central controller that:
- Initializes all agents
- Routes messages between agents
- Monitors swarm health
- Provides statistics for visualization
"""

import asyncio
from typing import List, Dict
from collections import deque
import time

from backend.agents.base_agent import BaseAgent
from backend.agents.coordinator_agent import CoordinatorAgent
from backend.agents.solver_agent import SolverAgent
from backend.kaspa.wallet import KaspaWallet
from backend.kaspa.transaction import SwarmMessage, MessageType


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
        self.task_history: List[Dict] = []  # All tasks with lifecycle
        
        # Message routing for mock mode
        self.message_relay_enabled = mock_mode
        
    def log_task_event(self, task_id: int, event: str, data: Dict):
        """Log task lifecycle events for history panel."""
        # Find existing task or create new entry
        task_entry = next((t for t in self.task_history if t["task_id"] == task_id), None)
        
        if not task_entry:
            task_entry = {
               "task_id": task_id,
                "status": event,
                "events": [],
                "created_at": time.time(),
            }
            self.task_history.append(task_entry)
        
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
        elif event == "assigned":
            task_entry["assigned_to"] = data.get("solver", "")
            task_entry["bid_amount"] = data.get("bid_amount", 0)
        elif event == "completed":
            task_entry["solution"] = data.get("solution", 0)
            task_entry["completed_at"] = time.time()
        
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
        """Start all agents and message relay."""
        self.running = True
        
        # Start all agent decision loops
        agent_tasks = [asyncio.create_task(agent.start()) for agent in self.agents]
        
        # Start message relay if in mock mode
        if self.message_relay_enabled:
            relay_task = asyncio.create_task(self.message_relay_loop())
            agent_tasks.append(relay_task)
        
        await asyncio.gather(*agent_tasks)
    
    async def message_relay_loop(self):
        """
        In mock mode, simulate blockchain message passing.
        Intercept agent send_message calls and deliver to recipients.
        """
        print("📡 Message relay active (mock mode)")
        
        while self.running:
            await asyncio.sleep(0.1)
            
            # In mock mode, we need to intercept transactions
            # This is handled by having agents send messages through the swarm
            # For simplicity, we'll use a broadcast approach where certain
            # message types are delivered to all relevant agents
    
    async def broadcast_message(self, message: SwarmMessage, sender: BaseAgent):
        """Broadcast a message to all relevant agents."""
        # Record transaction for edge visualization
        task_type = None
        if message.msg_type == MessageType.TASK_ANNOUNCEMENT:
            task_type = message.data.get("task_type")
            
        # Log task lifecycle events
        if message.msg_type == MessageType.TASK_ANNOUNCEMENT:
            self.log_task_event(message.task_id, "created", {
                "description": message.data.get("description", ""),
                "reward": message.data.get("reward", 0),
                "task_type": message.data.get("task_type", ""),
                "coordinator": sender.state.agent_id
            })
            
        elif message.msg_type == MessageType.TASK_BID:
            # We don't create a full event for every bid to avoid spam, 
            # but we could update the task status if we wanted to show "bidding in progress"
            pass
            
        elif message.msg_type == MessageType.SOLUTION_SUBMISSION:
            self.log_task_event(message.task_id, "completed", {
                "solution": message.data.get("solution", ""),
                "solver": sender.state.agent_id
            })

        self.transaction_history.append({
            "timestamp": time.time(),
            "from": sender.state.agent_id,
            "from_address": sender.state.address.address if sender.state.address else "",
            "msg_type": message.msg_type.value,
            "task_id": message.task_id,
            "task_type": task_type
        })
        
        if message.msg_type == MessageType.TASK_ANNOUNCEMENT:
            # Deliver to all solver agents
            for agent in self.agents:
                if agent.state.role == "solver" and agent != sender:
                    await agent.receive_message(message)
        
        elif message.msg_type == MessageType.TASK_BID:
            # Deliver to the coordinator who posted the task
            for agent in self.agents:
                if (agent.state.role == "coordinator" and 
                    agent.state.address and 
                    message.sender != agent.state.address.address):
                    await agent.receive_message(message)
        
        elif message.msg_type == MessageType.SOLUTION_SUBMISSION:
            # Deliver to coordinator
            for agent in self.agents:
                if agent.state.role == "coordinator":
                    await agent.receive_message(message)
    
    async def stop_swarm(self):
        """Stop all agents."""
        self.running = False
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
            "transactions": list(self.transaction_history),  # Last 30 transactions
            "task_history": self.task_history[-50:],  # Last 50 tasks
            "agents": {
                "coordinators": coordinator_stats,
                "solvers": solver_stats
            }
        }
    
    # Control methods
    async def pause(self):
        """Pause swarm operations."""
        for agent in self.agents:
            agent.running = False
        print("⏸️  Swarm paused")
    
    async def resume(self):
        """Resume swarm operations."""
        for agent in self.agents:
            agent.running = True
        print("▶️  Swarm resumed")
    
    async def manual_task_creation(self, target: int, reward: int, task_type_str: str = "prime_finding"):
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
                array_size = max(50, min(target, 1000)) # Clamp between 50 and 1000
                input_data = {"array": [random.randint(1, 1000) for _ in range(array_size)]}
                description = f"Sort array of {array_size} integers"
            elif task_type == TaskType.DATA_SEARCH:
                dataset_size = max(100, min(target, 5000)) # Clamp
                dataset = [f"item_{i}" for i in range(dataset_size)]
                query = f"item_{random.randint(0, dataset_size-1)}"
                input_data = {"dataset": dataset, "query": query}
                description = f"Search for '{query}' in dataset"

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
                "task_type": "prime_finding"
            })
            
            await coordinator.broadcast_task(task)
            asyncio.create_task(coordinator.handle_task_lifecycle(task))
            print(f"✅ Manually created task {task.task_id}")
            return {"status": "success", "task_id": task.task_id}

    async def add_agent(self, role: str, skill_level: float = 1.0):
        """Dynamically add a new agent to the swarm."""
        from backend.agents.coordinator_agent import CoordinatorAgent
        from backend.agents.solver_agent import SolverAgent
        from backend.kaspa.wallet import KaspaWallet
        
        agent_id = f"{role}_{int(time.time()*1000)}"
        wallet = KaspaWallet() # In real app, would need new keypair
        
        if role == "coordinator":
            agent = CoordinatorAgent(wallet, agent_id)
        else:
            agent = SolverAgent(wallet, agent_id, skill_level)
            
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
