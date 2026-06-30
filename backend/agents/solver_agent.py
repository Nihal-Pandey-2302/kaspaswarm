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
from backend.kcore.wallet import KaspaWallet
from backend.kcore.transaction import MessageType, SwarmMessage
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

            if self.paused:
                continue

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
            # Move from available to assigned — only now do we commit to working it
            self.assigned_tasks[task_id] = self.available_tasks[task_id]
            if task_id not in self.state.active_tasks:
                self.state.active_tasks.append(task_id)
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
            # Reverse auction: a LOWER bid is more competitive. Higher-skill
            # agents are more efficient, so they can profitably bid lower and
            # win more work (and the coordinator weights this by reputation).
            multiplier = 1.2 - 0.2 * self.skill_level   # skill 0.5 -> 1.10x, 1.5 -> 0.90x
            # Wider jitter so wins spread across the swarm (skill still wins on average).
            bid_amount = int(reward * 0.6 * multiplier * random.uniform(0.7, 1.3))
            # Keep bids >= ~0.2 KAS (the on-chain dust floor) so even the cheapest
            # winning bid pays a meaningful, distinct amount on-chain.
            bid_amount = max(int(reward * 0.4), min(bid_amount, reward))

            # Submit bid
            await self.submit_bid(task_id, bid_amount, message.sender)
    
    async def submit_bid(self, task_id: int, bid_amount: int, coordinator_address: str):
        """Submit a bid for a task."""
        self.state.total_bids += 1
        
        bid_message = SwarmMessage(
            msg_type=MessageType.TASK_BID,
            sender=self.state.address.address,
            task_id=task_id,
            data={"bid": bid_amount, "reputation": self.reputation},
            timestamp=int(time.time())
        )
        
        await self.send_message(coordinator_address, bid_message)
        
        print(f"🎯 {self.state.agent_id} bid {bid_amount} sompi on task {task_id}")

        # NOTE: we do NOT mark the task assigned here. A bid is not a win.
        # The task is only committed to work in handle_assignment(), once the
        # coordinator actually selects this solver. Otherwise every bidder
        # would compute every task and corrupt its own stats.
    
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
        
        if task_type == TaskType.AI_TASK:
            from backend.llm_client import get_llm
            prompt = task_info.get("input_data", {}).get("prompt", "")
            answer = await get_llm().complete(
                system="You are an autonomous AI worker agent in a decentralized swarm on "
                       "Kaspa. Complete the user's task correctly and concisely.",
                user=prompt,
            )
            solution = answer or "[AI agent produced no answer]"
        else:
            solution = solve_task(temp_task)

        print(f"💡 {self.state.agent_id} found solution for task {task_id}: {str(solution)[:80]}")

        # Don't broadcast a solution (a real spend) while the swarm is paused.
        while self.paused and self.running:
            await asyncio.sleep(0.3)

        # Submit solution
        await self.submit_solution(task_id, solution, coordinator)

        # Clean up safely
        if task_id in self.assigned_tasks:
            del self.assigned_tasks[task_id]

        # Remove from active_tasks just in case it was added back
        if task_id in self.state.active_tasks:
            self.state.active_tasks.remove(task_id)
        # NOTE: completed_tasks / successful_bids / reputation are NOT credited here.
        # The coordinator credits them only when the solution actually passes
        # verification and is paid (see SwarmOrchestrator.credit_solution /
        # adjust_reputation), so stats reflect verified work, not just submissions.

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
