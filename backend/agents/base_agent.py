"""
Base agent class for all swarm agents.

All agents inherit from this class and implement their own decision-making logic.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from backend.kcore.wallet import KaspaWallet, KaspaAddress
from backend.kcore.transaction import SwarmMessage


@dataclass
class AgentState:
    """Current state of an agent."""
    agent_id: str
    address: Optional[KaspaAddress]
    role: str  # "coordinator" or "solver"
    reputation: float = 100.0  # baseline (coordinators read this via get_stats)
    active_tasks: List[int] = field(default_factory=list)
    completed_tasks: int = 0
    total_earnings: int = 0  # in sompi
    total_bids: int = 0
    successful_bids: int = 0


class BaseAgent(ABC):
    """
    Abstract base class for all swarm agents.
    
    AGENT LIFECYCLE:
    1. Initialize with Kaspa wallet
    2. Start monitoring blockchain
    3. React to relevant transactions
    4. Make decisions based on swarm protocol
    5. Submit transactions to coordinate
    """
    
    def __init__(self, wallet: KaspaWallet, agent_id: str, role: str):
        self.wallet = wallet
        self.state = AgentState(
            agent_id=agent_id,
            address=None,  # Will be set in initialize()
            role=role
        )
        self.running = False
        self.paused = False
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.orchestrator = None  # Will be set by orchestrator
        self._pending_deliveries = set()  # in-flight _deliver_if_unconfirmed tasks
        
    async def initialize(self):
        """Set up agent wallet and start monitoring."""
        self.state.address = await self.wallet.create_address(seed_id=self.state.agent_id)
        print(f"🤖 Agent {self.state.agent_id} initialized | {self.state.role} | {self.state.address.address}")
        
    async def start(self):
        """Start agent operation loop."""
        self.running = True
        
        # Start decision-making loop
        decision_task = asyncio.create_task(self.decision_loop())
        
        # Start message processing loop
        message_task = asyncio.create_task(self.message_processing_loop())
        
        await asyncio.gather(decision_task, message_task)
    
    async def message_processing_loop(self):
        """Process messages from the queue."""
        while self.running:
            # While paused, leave messages queued and process nothing — this is
            # what makes pause actually halt bids/assignments/payouts (real spend).
            if self.paused:
                await asyncio.sleep(0.2)
                continue
            try:
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )
                await self.process_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Error processing message in {self.state.agent_id}: {e}")
    
    async def receive_message(self, message: SwarmMessage):
        """Called by orchestrator to deliver messages to agent."""
        await self.message_queue.put(message)
    
    @abstractmethod
    async def process_message(self, message: SwarmMessage):
        """Process swarm message - implemented by subclasses."""
        pass
    
    @abstractmethod
    async def decision_loop(self):
        """Agent's autonomous decision-making - implemented by subclasses."""
        pass
    
    async def send_message(
        self,
        to_address: str,
        message: SwarmMessage
    ) -> str:
        """Send message to another agent or broadcast."""
        from backend.kcore.transaction import TransactionEncoder

        # The full message rides on-chain in the tx payload field, including the
        # intended recipient. The carrier tx is a SELF-SEND so coordination moves
        # no funds (change returns to the sender, minus fee) — only the reward
        # payout actually transfers KAS. The watcher routes by the payload's
        # recipient, not the tx output.
        message.to_address = to_address
        payload = TransactionEncoder.encode_payload(message)

        # Send through blockchain (self-send carrier; amount floored to dust min)
        tx_id = await self.wallet.send_transaction(
            from_addr=self.state.address,
            to_addr=self.state.address.address,
            amount=0,
            payload=payload
        )

        if self.orchestrator:
            from backend.kcore.wallet import tx_failed
            broadcast_ok = not tx_failed(tx_id)

            # Always record for the live UI/history, regardless of transport.
            self.orchestrator.record_message(
                message, self,
                tx_id=tx_id if broadcast_ok else "",
                onchain=broadcast_ok and not self.orchestrator.message_relay_enabled,
            )

            if self.orchestrator.message_relay_enabled or not broadcast_ok:
                # Mock mode, or live-mode broadcast failure -> deliver in-memory now.
                await self.orchestrator.deliver_message(
                    message,
                    to_address=to_address,
                    exclude_address=self.state.address.address if self.state.address else None,
                )
            else:
                # Live + broadcast accepted: the ChainWatcher delivers this once it
                # appears in a block. Safety net: if it never confirms, deliver
                # in-memory after a timeout (deduped against the watcher).
                task = asyncio.create_task(self._deliver_if_unconfirmed(tx_id, message, to_address))
                self._pending_deliveries.add(task)
                task.add_done_callback(self._pending_deliveries.discard)

        return tx_id

    async def _deliver_if_unconfirmed(self, tx_id: str, message: SwarmMessage,
                                      to_address: str, timeout: float = 8.0):
        """Safety net for live mode: if a broadcast tx is never seen on-chain
        within `timeout`, deliver it in-memory so the swarm never stalls. Claims the
        tx id in the ChainWatcher so a later on-chain sighting won't double-deliver."""
        try:
            await asyncio.sleep(timeout)
            watcher = getattr(self.orchestrator, "sdk", None) or getattr(self.orchestrator, "chain_watcher", None)
            # Atomically claim the tx id. If the watcher already saw it on-chain,
            # mark_seen returns False and we skip — no double-delivery either way.
            if watcher is not None and not watcher.mark_seen(tx_id):
                return
            await self.orchestrator.deliver_message(
                message,
                to_address=to_address,
                exclude_address=self.state.address.address if self.state.address else None,
            )
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """Stop the agent."""
        self.running = False
        print(f"🛑 Agent {self.state.agent_id} stopping...")
        # Cancel any pending fallback-delivery timers so they don't fire post-stop.
        for t in list(self._pending_deliveries):
            t.cancel()
        self._pending_deliveries.clear()
    
    def get_stats(self) -> Dict:
        """Get agent statistics for monitoring."""
        return {
            "agent_id": self.state.agent_id,
            "role": self.state.role,
            "address": self.state.address.address if self.state.address else "",
            # Reputation lives on the agent (updated by the coordinator on
            # success/slash); fall back to state for agents without it.
            "reputation": getattr(self, "reputation", self.state.reputation),
            "skill_level": getattr(self, "skill_level", None),
            "specialization": getattr(self, "specialization", None),
            "active_tasks": len(self.state.active_tasks),
            "completed_tasks": self.state.completed_tasks,
            "balance": self.state.total_earnings,
            "status": "working" if len(self.state.active_tasks) > 0 else "idle",
            "total_bids": self.state.total_bids,
            "successful_bids": self.state.successful_bids,
            "success_rate": (
                self.state.successful_bids / self.state.total_bids 
                if self.state.total_bids > 0 else 0
            )
        }
