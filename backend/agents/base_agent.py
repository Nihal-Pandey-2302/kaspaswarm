"""
Base agent class for all swarm agents.

All agents inherit from this class and implement their own decision-making logic.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from backend.kaspa.wallet import KaspaWallet, KaspaAddress
from backend.kaspa.transaction import SwarmMessage


@dataclass
class AgentState:
    """Current state of an agent."""
    agent_id: str
    address: Optional[KaspaAddress]
    role: str  # "coordinator" or "solver"
    reputation: float = 1.0
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
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.orchestrator = None  # Will be set by orchestrator
        
    async def initialize(self):
        """Set up agent wallet and start monitoring."""
        self.state.address = await self.wallet.create_address()
        print(f"🤖 Agent {self.state.agent_id} initialized | {self.state.role} | {self.state.address.address}")
        
    async def start(self):
        """Start agent operation loop."""
        self.running = True
        
        # Start decision-making loop
        decision_task = asyncio.create_task(self.decision_loop())
        
        # Start message processing loop
        message_task = asyncio.create_task(self.message_processing_loop())
        
        await asyncio.gather(decision_task, message_task)
    
    async def stop(self):
        """Stop agent operation."""
        self.running = False
        print(f"🛑 Agent {self.state.agent_id} stopping...")

    async def message_processing_loop(self):
        """Process messages from the queue."""
        while self.running:
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
        from backend.kaspa.transaction import TransactionEncoder
        
        amount = TransactionEncoder.encode_message(message)
        
        # DEBUG
        print(f"DEBUG: calling send_transaction. wallet type: {type(self.wallet)}")
        print(f"DEBUG: send_transaction varnames: {self.wallet.send_transaction.__code__.co_varnames}")

        # Send through blockchain
        tx_id = await self.wallet.send_transaction(
            from_addr=self.state.address,
            to_addr=to_address,
            amount=amount
        )
        
        # If we have an orchestrator (mock mode), also route through it
        if self.orchestrator:
            await self.orchestrator.broadcast_message(message, self)
        
        return tx_id
    
    async def stop(self):
        """Stop the agent."""
        self.running = False
    
    def get_stats(self) -> Dict:
        """Get agent statistics for monitoring."""
        return {
            "agent_id": self.state.agent_id,
            "role": self.state.role,
            "address": self.state.address.address if self.state.address else "",
            "reputation": self.state.reputation,
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
