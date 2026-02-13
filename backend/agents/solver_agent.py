"""
Solver agent that bids on and completes tasks.

Solvers are responsible for:
- Monitoring for task announcements
- Evaluating task difficulty and reward
- Submitting bids for attractive tasks
- Solving assigned tasks
- Submitting solutions
"""

import asyncio
import random
import time
from typing import Dict

from backend.agents.base_agent import BaseAgent
from backend.kaspa.wallet import KaspaWallet
from backend.kaspa.transaction import MessageType, SwarmMessage
from backend.swarm.task_types import find_largest_prime


class SolverAgent(BaseAgent):
    """
    Solver agent that bids on and completes tasks.
    """
    
    def __init__(self, wallet: KaspaWallet, agent_id: str, skill_level: float = 1.0):
        super().__init__(wallet, agent_id, role="solver")
        self.skill_level = skill_level  # 0.5 to 1.5 (affects solve speed and bid aggressiveness)
        self.reputation = 100.0
        
        # Assign random specialization
        specializations = ["prime_finding", "hash_cracking", "sorting", "data_search"]
        self.specialization = random.choice(specializations)
        
        self.available_tasks: Dict[int, dict] = {}
        self.assigned_tasks: Dict[int, dict] = {}
        
    async def decision_loop(self):
        """Continuously evaluate and work on tasks."""
        while self.running:
            await asyncio.sleep(2)
            
            # Work on assigned tasks
            for task_id in list(self.state.active_tasks):
                if task_id in self.assigned_tasks:
                    asyncio.create_task(self.work_on_task(task_id))
                    # Remove from active list to avoid duplicate work
                    self.state.active_tasks.remove(task_id)
    
    async def process_message(self, message: SwarmMessage):
        """Process task announcements and assignments."""
        if message.msg_type == MessageType.TASK_ANNOUNCEMENT:
            await self.evaluate_task(message)
        elif message.msg_type == MessageType.TASK_ASSIGNMENT:
            await self.handle_assignment(message)

    async def handle_assignment(self, message: SwarmMessage):
        """Handle task assignment."""
        task_id = message.task_id
        if task_id in self.available_tasks:
            # Move from available to assigned
            self.assigned_tasks[task_id] = self.available_tasks[task_id]
            print(f"📥 {self.state.agent_id} received assignment for task {task_id}")
    
    async def evaluate_task(self, message: SwarmMessage):
        """Decide whether to bid on task."""
        task_id = message.task_id
        reward = message.data.get("reward", 0)
        deadline = message.data.get("deadline", 0)
        
        # Store task info if not already known
        if task_id in self.available_tasks:
            return
            
        self.available_tasks[task_id] = {
            "reward": reward,
            "description": message.data.get("description", ""),
            "task_type": message.data.get("task_type", "prime_finding"),
            "input_data": message.data.get("input_data", {}),
            "deadline": deadline,
            "coordinator": message.sender
        }
        
        # Simple bidding strategy: bid if reward > threshold
        # Threshold depends on skill level (higher skill = lower threshold)
        bid_threshold = 800 / self.skill_level
        
        if reward > bid_threshold:
            # Calculate bid amount based on skill and confidence
            # Higher skill = higher bid (more confident)
            bid_amount = int(reward * 0.6 * self.skill_level)
            
            # Add some randomness
            bid_amount = int(bid_amount * random.uniform(0.8, 1.2))
            
            # Submit bid
            await self.submit_bid(task_id, bid_amount, message.sender)
    
    async def submit_bid(self, task_id: int, bid_amount: int, coordinator_address: str):
        """Submit a bid for a task."""
        self.state.total_bids += 1
        
        bid_message = SwarmMessage(
            msg_type=MessageType.TASK_BID,
            sender=self.state.address.address,
            task_id=task_id,
            data={"bid": bid_amount},
            timestamp=int(time.time())
        )
        
        await self.send_message(coordinator_address, bid_message)
        
        print(f"🎯 {self.state.agent_id} bid {bid_amount} sompi on task {task_id}")
        
        # Mark as active and assigned (if not already)
        if task_id not in self.state.active_tasks and task_id not in self.assigned_tasks:
            self.state.active_tasks.append(task_id)
            self.assigned_tasks[task_id] = self.available_tasks.get(task_id, {})
    
    async def work_on_task(self, task_id: int):
        """
        Solve the task (find largest prime).
        """
        if task_id not in self.assigned_tasks:
            return
        
        task_info = self.assigned_tasks[task_id]
        coordinator = task_info["coordinator"]
        task_type_str = task_info.get("task_type", "unknown")
        
        print(f"🔨 {self.state.agent_id} working on task {task_id} ({task_type_str})...")
        
        # Check specialization bonus
        is_specialized = task_type_str == self.specialization
        speed_multiplier = 0.5 if is_specialized else 1.0
        
        if is_specialized:
            print(f"⚡ {self.state.agent_id} using SPECIALIZATION bonus for {task_type_str}!")
        
        # Simulate work time based on skill and specialization
        # Higher skill + Specialization = much faster execution
        base_work_time = random.uniform(0.5, 1.5)
        work_time = (base_work_time / self.skill_level) * speed_multiplier
        
        await asyncio.sleep(work_time)
        
        # Find solution using helper
        from backend.swarm.task_types import Task, TaskType, solve_task
        
        # reconstruct temp task
        task_type_str = task_info.get("task_type", "prime_finding")
        try:
            task_type = TaskType(task_type_str)
        except ValueError:
            task_type = TaskType.PRIME_FINDING
            
        temp_task = Task(
            task_id=task_id,
            description=task_info.get("description", ""),
            task_type=task_type,
            input_data=task_info.get("input_data", {}),
            reward=task_info.get("reward", 0),
            deadline=0,
            coordinator_address=""
        )
        
        solution = solve_task(temp_task)
        
        print(f"💡 {self.state.agent_id} found solution for task {task_id}: {solution}")
        
        # Submit solution
        await self.submit_solution(task_id, solution, coordinator)
        
        # Clean up safely
        if task_id in self.assigned_tasks:
            del self.assigned_tasks[task_id]
        
        # Remove from active_tasks just in case it was added back
        if task_id in self.state.active_tasks:
            self.state.active_tasks.remove(task_id)
        self.state.completed_tasks += 1
        self.state.successful_bids += 1
        
        # Increase reputation
        self.reputation = min(200.0, self.reputation + 1.5)
    
    async def submit_solution(self, task_id: int, solution: int, coordinator_address: str):
        """Submit solution to coordinator."""
        solution_message = SwarmMessage(
            msg_type=MessageType.SOLUTION_SUBMISSION,
            sender=self.state.address.address,
            task_id=task_id,
            data={"solution": solution},
            timestamp=int(time.time())
        )
        
        await self.send_message(coordinator_address, solution_message)
        
        print(f"📤 {self.state.agent_id} submitted solution for task {task_id}")
    
    def get_stats(self) -> Dict:
        """Override to include skill_level and specialization."""
        stats = super().get_stats()
        stats["skill_level"] = self.skill_level
        stats["specialization"] = self.specialization
        return stats
