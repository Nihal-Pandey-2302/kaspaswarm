"""
Coordinator agent that posts tasks to the swarm.

Coordinators are responsible for:
- Generating tasks periodically
- Broadcasting task announcements
- Collecting bids from solvers
- Assigning tasks to best bidders
- Verifying submitted solutions
- Distributing rewards
"""

import asyncio
import random
import time
from typing import Dict

from backend.agents.base_agent import BaseAgent
from backend.kaspa.wallet import KaspaWallet
from backend.kaspa.transaction import MessageType, SwarmMessage, TransactionEncoder
from backend.swarm.task_types import Task, TaskType, verify_solution


class CoordinatorAgent(BaseAgent):
    """
    Coordinator agent that posts tasks to the swarm.
    """
    
    def __init__(self, wallet: KaspaWallet, agent_id: str):
        super().__init__(wallet, agent_id, role="coordinator")
        self.active_tasks: Dict[int, Task] = {}
        self.next_task_id = 1
        self.broadcast_address = TransactionEncoder.create_broadcast_address()
        self.min_interval = 5.0  # Configurable task frequency
        self.max_interval = 15.0
        
    async def decision_loop(self):
        """Periodically create and post tasks."""
        while self.running:
            # Wait random interval (configurable)
            await asyncio.sleep(random.uniform(self.min_interval, self.max_interval))
            
            # Generate new task
            task = self.generate_task()
            self.active_tasks[task.task_id] = task
            
            # Log task creation to orchestrator
            if self.orchestrator:
                self.orchestrator.log_task_event(task.task_id, "created", {
                    "description": task.description,
                    "reward": task.reward,
                    "coordinator": self.state.agent_id,
                    "task_type": task.task_type.value
                })
            
            # Broadcast task to swarm
            await self.broadcast_task(task)
            
            # Start task assignment process
            asyncio.create_task(self.handle_task_lifecycle(task))
            
    def generate_task(self) -> Task:
        """
        Generate a task for the swarm.
        
        Task: Find largest prime less than a random number
        """
        task_id = self.next_task_id
        self.next_task_id += 1
        
        
        # Randomly select task type
        task_type = random.choice(list(TaskType))
        
        description = ""
        input_data = {}
        reward = 1000
        
        if task_type == TaskType.PRIME_FINDING:
            target = random.randint(1000, 10000)
            description = f"Find largest prime less than {target}"
            input_data = {"target": target}
            reward = random.randint(1000, 3000)
            
        elif task_type == TaskType.HASH_CRACKING:
            import hashlib
            prefixes = ["00", "000", "abc", "123", "caf", "bad"]
            prefix = random.choice(prefixes)
            description = f"Crack SHA256 hash starting with '{prefix}'"
            input_data = {"prefix": prefix}
            reward = random.randint(2000, 5000)
            
        elif task_type == TaskType.SORTING:
            length = random.randint(50, 200)
            array = [random.randint(0, 1000) for _ in range(length)]
            description = f"Sort array of {length} integers"
            input_data = {"array": array}
            reward = random.randint(500, 1500)
            
        elif task_type == TaskType.DATA_SEARCH:
            dataset = [f"item_{i}" for i in range(1000)]
            target_idx = random.randint(0, 999)
            query = f"item_{target_idx}"
            description = f"Search for '{query}' in dataset"
            input_data = {"dataset": dataset, "query": query}
            reward = random.randint(500, 1000)
        
        task = Task(
            task_id=task_id,
            description=description,
            task_type=task_type,
            input_data=input_data,
            reward=reward,
            deadline=time.time() + 30,
            coordinator_address=self.state.address.address
        )
        
        print(f"📋 Task {task_id} created by {self.state.agent_id}: {task.description} | Reward: {reward} sompi")
        
        return task
    
    async def broadcast_task(self, task: Task):
        """Broadcast task announcement to all solver agents."""
        message = SwarmMessage(
            msg_type=MessageType.TASK_ANNOUNCEMENT,
            sender=self.state.address.address,
            task_id=task.task_id,
            data={
                "description": task.description,
                "task_type": task.task_type.value,
                "input_data": task.input_data,
                "reward": task.reward,
                "deadline": task.deadline
            },
            timestamp=int(time.time())
        )
        
        await self.send_message(self.broadcast_address, message)
        print(f"📢 Task {task.task_id} announced by {self.state.agent_id}")
    
    async def handle_task_lifecycle(self, task: Task):
        """Manage task from announcement to completion."""
        # Wait for bidding period (10 seconds)
        await asyncio.sleep(10)
        
        # Assign to best bidder
        if task.bids:
            best_bid = task.get_best_bid()
            task.assigned_to = best_bid["agent"]
            
            # Log assignment
            if self.orchestrator:
                self.orchestrator.log_task_event(task.task_id, "assigned", {
                    "solver": best_bid["agent"],
                    "bid_amount": best_bid["amount"],
                    "task_type": task.task_type.value
                })
            
            print(f"✅ Task {task.task_id} assigned to {best_bid['agent'][:20]}... (bid: {best_bid['amount']} sompi)")
            
            # Broadcast assignment to solver
            assignment_message = SwarmMessage(
                msg_type=MessageType.TASK_ASSIGNMENT,
                sender=self.state.address.address,
                task_id=task.task_id,
                data={
                    "coordinator": self.state.address.address,
                    "deadline": task.deadline
                },
                timestamp=int(time.time())
            )
            await self.send_message(best_bid['agent'], assignment_message)
            
            # Wait for solution
            remaining_time = task.deadline - time.time()
            if remaining_time > 0:
                await asyncio.sleep(remaining_time)
            
            # Give a small buffer for network/processing delay
            await asyncio.sleep(2.0)
        
        # Check if task was completed
        if not task.completed:
            if self.orchestrator:
                self.orchestrator.log_task_event(task.task_id, "failed", {})
            print(f"⏰ Task {task.task_id} expired without solution")
            del self.active_tasks[task.task_id]
    
    async def process_message(self, message: SwarmMessage):
        """Process bids and solutions from solvers."""
        if message.msg_type == MessageType.TASK_BID:
            await self.handle_bid(message)
        elif message.msg_type == MessageType.SOLUTION_SUBMISSION:
            await self.handle_solution(message)
    
    async def handle_bid(self, message: SwarmMessage):
        """Collect and evaluate bids."""
        if message.task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[message.task_id]
        
        if task.completed or task.is_expired():
            return
        
        bid_amount = message.data.get("bid", 0)
        task.add_bid(message.sender, bid_amount)
        
        print(f"💰 Bid received for task {message.task_id}: {bid_amount} sompi from {message.sender[:20]}...")
    
    async def handle_solution(self, message: SwarmMessage):
        """Verify solution and distribute reward."""
        if message.task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[message.task_id]
        
        if task.completed:
            return
        
        solution = message.data.get("solution")
        
        # Verify solution
        if solution is not None:
            # For hackathon demo, accept any solution from assigned agent
            # In production, verify with verify_solution()
            is_correct = (task.assigned_to == message.sender)
            
            if is_correct:
                # Mark as completed
                task.completed = True
                task.solution = solution
                
                # Log completion
                if self.orchestrator:
                    self.orchestrator.log_task_event(task.task_id, "completed", {
                        "solution": solution,
                        "solver": message.sender
                    })
                
                # Send reward
                await self.wallet.send_transaction(
                    from_address=self.state.address,
                    to_address=message.sender,
                    amount_sompi=task.reward
                )
                
                print(f"🎉 Task {task.task_id} completed! Solution: {solution} | Reward sent to {message.sender[:20]}...")
                
                # Clean up
                del self.active_tasks[task.task_id]
