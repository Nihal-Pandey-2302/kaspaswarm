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
from backend.kcore.wallet import KaspaWallet
from backend.kcore.transaction import MessageType, SwarmMessage, TransactionEncoder
from backend.swarm.task_types import Task, TaskType, verify_solution


class CoordinatorAgent(BaseAgent):
    """
    Coordinator agent that posts tasks to the swarm.
    """

    # Each coordinator instance gets a disjoint task-id range so ids are globally
    # unique across coordinators. Without this, every coordinator minted 1,2,3…
    # and (since bids/solutions fan out to all coordinators and the shared escrow
    # is keyed by task_id) they processed and escrowed each other's tasks.
    _next_coord_index = 0
    _TASK_ID_STRIDE = 1_000_000

    def __init__(self, wallet: KaspaWallet, agent_id: str):
        super().__init__(wallet, agent_id, role="coordinator")
        self.active_tasks: Dict[int, Task] = {}
        self.coord_index = CoordinatorAgent._next_coord_index
        CoordinatorAgent._next_coord_index += 1
        self.next_task_id = self.coord_index * CoordinatorAgent._TASK_ID_STRIDE + 1
        self.broadcast_address = TransactionEncoder.create_broadcast_address()
        self.min_interval = 5.0  # Configurable task frequency
        self.max_interval = 15.0
        
    async def decision_loop(self):
        """Periodically create and post tasks."""
        while self.running:
            # Wait random interval (configurable)
            await asyncio.sleep(random.uniform(self.min_interval, self.max_interval))

            if self.paused:
                continue

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
        
        
        # Auto-generated tasks are ALWAYS deterministic compute tasks — they
        # never call the LLM. AI tasks are human-initiated only (via Create Task),
        # so API tokens are spent exclusively when a user explicitly asks for one.
        task_type = random.choice([
            TaskType.PRIME_FINDING, TaskType.HASH_CRACKING,
            TaskType.SORTING, TaskType.DATA_SEARCH,
        ])

        description = ""
        input_data = {}
        reward = 1000

        # Rewards are in sompi at REALISTIC magnitudes (~0.5–1.8 KAS) so the on-chain
        # payout actually reflects the winning bid instead of all flooring to the
        # 0.2 KAS dust minimum. 1 KAS = 100_000_000 sompi.
        if task_type == TaskType.PRIME_FINDING:
            target = random.randint(1000, 10000)
            description = f"Find largest prime less than {target}"
            input_data = {"target": target}
            reward = random.randint(50_000_000, 120_000_000)

        elif task_type == TaskType.HASH_CRACKING:
            import hashlib
            prefixes = ["00", "000", "abc", "123", "caf", "bad"]
            prefix = random.choice(prefixes)
            description = f"Crack SHA256 hash starting with '{prefix}'"
            input_data = {"prefix": prefix}
            reward = random.randint(60_000_000, 180_000_000)

        elif task_type == TaskType.SORTING:
            # Keep arrays small — the full input rides on-chain in the tx payload,
            # and payload size drives tx mass/fee.
            length = random.randint(15, 40)
            array = [random.randint(0, 1000) for _ in range(length)]
            description = f"Sort array of {length} integers"
            input_data = {"array": array}
            reward = random.randint(50_000_000, 100_000_000)

        elif task_type == TaskType.DATA_SEARCH:
            dataset = [f"item_{i}" for i in range(40)]   # small: rides on-chain
            target_idx = random.randint(0, len(dataset) - 1)
            query = f"item_{target_idx}"
            description = f"Search for '{query}' in dataset"
            input_data = {"dataset": dataset, "query": query}
            reward = random.randint(50_000_000, 90_000_000)
        
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
        
        # Broadcast announcements to the coordinator's own (valid) address — the
        # synthetic broadcast address isn't a decodable Kaspa address and would
        # fail every live send. The ChainWatcher routes announcements to all
        # solvers by message type, so the recipient address is irrelevant here.
        await self.send_message(self.state.address.address, message)
        print(f"📢 Task {task.task_id} announced by {self.state.agent_id}")
    
    async def handle_task_lifecycle(self, task: Task):
        """Manage task from announcement to completion."""
        # Wait for bidding period (10 seconds)
        await asyncio.sleep(10)

        # Respect pause: don't assign or pay out (real spend) while paused.
        while self.paused and self.running:
            await asyncio.sleep(0.5)

        # Assign to best bidder
        if task.bids:
            best_bid = task.get_best_bid()
            task.assigned_to = best_bid["agent"]
            task.winning_bid = best_bid["amount"]  # pay the agreed bid, not a flat reward

            # Give the solver a FRESH solve window from assignment time. The
            # original deadline is wall-clock from task creation, so a pause (or a
            # slow bidding phase) could otherwise leave ~no time and unfairly slash.
            task.deadline = time.time() + 30

            # Lock reward + solver stake in escrow (in-protocol now; the SilverScript
            # covenant enforces this on-chain on TN12). Stake = half the bid.
            if self.orchestrator:
                stake = max(1, task.winning_bid // 2)
                self.orchestrator.escrow.lock(
                    task.task_id, self.state.address.address, best_bid["agent"],
                    task.winning_bid, stake,
                )

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
            
            # Buffer must exceed the in-memory fallback delivery timeout (8s in
            # base_agent._deliver_if_unconfirmed) so a fallback-delivered solution
            # isn't slashed as a timeout before it arrives.
            await asyncio.sleep(9.0)

        # Don't declare failure while paused — wait out any pause first.
        while self.paused and self.running:
            await asyncio.sleep(0.5)

        # Only declare a timeout if the task is still UNRESOLVED. handle_solution
        # pops the task on any terminal outcome (accepted / rejected / payout-failed),
        # so this prevents double-slashing or slashing an already-handled task.
        if task.task_id in self.active_tasks and not task.completed:
            if self.orchestrator:
                self.orchestrator.log_task_event(task.task_id, "failed", {})
                # Timeout: the assigned solver staked and failed to deliver -> slash
                # its stake and reputation (matches the covenant timeout path).
                if task.assigned_to:
                    self.orchestrator.adjust_reputation(task.assigned_to, -15)
                    await self.orchestrator.escrow.slash(task.task_id)
            print(f"⏰ Task {task.task_id} expired without solution")
            self.active_tasks.pop(task.task_id, None)
    
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
        # Use the coordinator's AUTHORITATIVE reputation for this address, not the
        # value the solver self-reports in its bid (which it could inflate to win).
        reputation = self.orchestrator.get_reputation(message.sender) if self.orchestrator else 100.0
        task.add_bid(message.sender, bid_amount, reputation)

        print(f"💰 Bid for task {message.task_id}: {bid_amount} sompi (rep {reputation:.0f}) from {message.sender[:20]}...")
    
    async def handle_solution(self, message: SwarmMessage):
        """Verify solution and distribute reward."""
        if message.task_id not in self.active_tasks:
            return

        task = self.active_tasks[message.task_id]
        if task.completed:
            return

        solution = message.data.get("solution")
        if solution is None:
            return

        # Only the agent that was actually assigned this task can settle it.
        if task.assigned_to != message.sender:
            return

        # CLAIM the task by removing it from active_tasks BEFORE any await
        # (verification + payout). This makes settlement atomic w.r.t. the
        # handle_task_lifecycle timeout, which only acts on tasks still in
        # active_tasks — so a solution can never be both paid and slashed, and a
        # rejection can't be double-slashed.
        self.active_tasks.pop(task.task_id, None)

        # Verify the actual result: deterministic check for compute tasks, an LLM
        # verifier-agent for AI tasks. This is the gate a covenant enforces on-chain.
        is_correct = await self._check_solution(task, solution)

        if not is_correct:
            # Soft slash: failed verification costs reputation + staked collateral.
            if self.orchestrator:
                self.orchestrator.adjust_reputation(message.sender, -15)
                await self.orchestrator.escrow.slash(task.task_id)
            print(f"❌ Task {task.task_id} solution from {message.sender[:20]}... REJECTED (failed verification) — stake slashed")
            return

        # Pay the agreed (winning) bid, not a flat reward.
        payout = task.winning_bid or task.reward
        reward_tx = await self.wallet.send_transaction(
            from_addr=self.state.address,
            to_addr=message.sender,
            amount=payout,
        )
        from backend.kcore.wallet import tx_failed
        payout_ok = not tx_failed(reward_tx)

        if payout_ok:
            # Only NOW is it truly settled: credit the solver, reward reputation,
            # and release the escrow.
            task.completed = True
            task.solution = solution
            if self.orchestrator:
                self.orchestrator.log_task_event(task.task_id, "completed", {
                    "solution": solution,
                    "solver": message.sender,
                })
                self.orchestrator.adjust_reputation(message.sender, +5)
                self.orchestrator.credit_solution(message.sender)
                await self.orchestrator.escrow.release(task.task_id)
            print(f"🎉 Task {task.task_id} completed! Solution: {str(solution)[:80]} | Paid {payout} sompi to {message.sender[:20]}...")
        else:
            # Payout failed on-chain (coordinator's fault, not the solver's) ->
            # cancel the escrow (return stake, no reward, no slash).
            if self.orchestrator:
                self.orchestrator.log_task_event(task.task_id, "failed", {})
                await self.orchestrator.escrow.cancel(task.task_id)
            print(f"⚠️ Reward payout failed for task {task.task_id}: {reward_tx} — not settled")

    async def _check_solution(self, task, solution) -> bool:
        """Verify a submitted solution. LLM judge for AI tasks; deterministic otherwise."""
        if task.task_type == TaskType.AI_TASK:
            return await self._verify_ai(task, solution)
        try:
            from backend.swarm.task_types import verify_solution
            return verify_solution(task, solution)
        except Exception as e:
            # Fail CLOSED: a verifier that can't confirm correctness must reject,
            # not pay out. (Was failing open, which let bad solutions get rewarded.)
            print(f"⚠️ verification error for task {task.task_id}: {e} — rejecting")
            return False

    async def _verify_ai(self, task, solution) -> bool:
        """Use an LLM verifier-agent to grade an AI-task answer (PASS/FAIL)."""
        from backend.llm_client import get_llm
        llm = get_llm()
        answer = str(solution or "").strip()
        if not answer or answer.startswith("[AI agent produced no answer"):
            return False
        if not llm.is_available():
            # No judge configured -> we cannot verify AI work, and AI tasks require
            # an LLM to be solved anyway, so fail CLOSED rather than pay for
            # unverified output.
            print(f"⚠️ No LLM verifier configured for task {task.task_id} — rejecting AI solution")
            return False
        prompt = (task.input_data or {}).get("prompt", "")
        verdict = await llm.complete(
            system="You are a strict verifier agent. Decide whether the ANSWER correctly "
                   "and reasonably completes the TASK. Reply with ONLY 'PASS' or 'FAIL'.",
            user=f"TASK: {prompt}\n\nANSWER: {answer}",
            max_tokens=5,
            temperature=0.0,
        )
        if verdict is None:
            # A judge WAS configured but the call failed -> fail CLOSED (reject),
            # so an outage can't be exploited to extract payment for garbage.
            print(f"⚠️ AI verifier unavailable for task {task.task_id} — rejecting")
            return False
        return "PASS" in verdict.upper()
