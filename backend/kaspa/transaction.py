"""
Transaction encoding/decoding protocol for agent communication.

Since Kaspa doesn't have smart contracts, we encode messages in transaction amounts.
This module handles the encoding/decoding logic for swarm coordination.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict
import time


class MessageType(Enum):
    """Agent communication message types encoded in transactions."""
    TASK_ANNOUNCEMENT = 1    # Coordinator posts new task
    TASK_BID = 2             # Solver bids on task
    TASK_ASSIGNMENT = 3      # Coordinator assigns task  
    SOLUTION_SUBMISSION = 4  # Solver submits solution
    SOLUTION_VERIFICATION = 5 # Other agents verify
    CONSENSUS_VOTE = 6       # Voting on solution quality


@dataclass
class SwarmMessage:
    """Decoded message from transaction."""
    msg_type: MessageType
    sender: str
    task_id: Optional[int]
    data: Dict
    timestamp: int
    tx_id: str = ""


class TransactionEncoder:
    """
    Encode/decode swarm messages in Kaspa transactions.
    
    ENCODING SCHEME:
    Since Kaspa is UTXO-based without smart contracts:
    1. Use amount field for data encoding
    2. Use multiple outputs for complex messages
    3. Use address patterns for agent identification
    
    AMOUNT ENCODING FORMAT:
    [BASE_AMOUNT] + [MESSAGE_TYPE * 100] + [TASK_ID]
    
    Example:
    - Task announcement for task_id=42: 1000 + 100 + 42 = 1142 sompi
    - Bid of 500 for task 42: 500 + 200 + 42 = 742 sompi
    - Solution for task 42: 1000 + 400 + 42 = 1442 sompi
    
    For bids, the BASE_AMOUNT represents the actual bid value.
    """
    
    BASE_AMOUNT = 1000  # Minimum transaction amount in sompi
    
    @staticmethod
    def encode_task_announcement(task_id: int) -> int:
        """Encode task announcement message."""
        return TransactionEncoder.BASE_AMOUNT + (MessageType.TASK_ANNOUNCEMENT.value * 100) + task_id
    
    @staticmethod
    def encode_bid(task_id: int, bid_amount: int) -> int:
        """Encode bid message. Bid amount is embedded in the base."""
        return bid_amount + (MessageType.TASK_BID.value * 100) + task_id
    
    @staticmethod
    def encode_solution(task_id: int) -> int:
        """Encode solution submission message."""
        return TransactionEncoder.BASE_AMOUNT + (MessageType.SOLUTION_SUBMISSION.value * 100) + task_id
    
    @staticmethod
    def encode_message(msg: SwarmMessage) -> int:
        """Convert message to transaction amount."""
        amount = TransactionEncoder.BASE_AMOUNT
        amount += msg.msg_type.value * 100
        
        if msg.task_id:
            # Task ID is limited to 0-99
            amount += min(msg.task_id, 99)
        
        # For bids, add the bid value to base amount
        if msg.msg_type == MessageType.TASK_BID and "bid" in msg.data:
            amount = msg.data["bid"] + (msg.msg_type.value * 100) + (msg.task_id or 0)
        
        return amount
    
    @staticmethod
    def decode_transaction(tx_data: Dict) -> Optional[SwarmMessage]:
        """
        Parse transaction into swarm message.
        
        Expected tx_data format:
        {
            "amount": int,
            "sender": str,
            "timestamp": int,
            "tx_id": str
        }
        """
        try:
            amount = tx_data.get("amount", 0)
            
            # Extract components
            # For amounts like 742: 742 - 200 = 542 (bid), task_id = 42, msg_type = 2
            # We need to extract task_id first (last 2 digits)
            task_id = amount % 100
            remaining = amount // 100
            
            # Message type is in the hundreds place
            msg_type_code = remaining % 10
            
            # Bid amount (if it's a bid)
            bid_value = amount - (msg_type_code * 100) - task_id
            
            # Validate message type
            try:
                msg_type = MessageType(msg_type_code)
            except ValueError:
                # Not a valid swarm message
                return None
            
            data = {}
            if msg_type == MessageType.TASK_BID:
                data["bid"] = bid_value
            
            return SwarmMessage(
                msg_type=msg_type,
                sender=tx_data.get("sender", ""),
                task_id=task_id if task_id > 0 else None,
                data=data,
                timestamp=tx_data.get("timestamp", int(time.time())),
                tx_id=tx_data.get("tx_id", "")
            )
        except Exception as e:
            print(f"Error decoding transaction: {e}")
            return None
    
    @staticmethod
    def create_broadcast_address() -> str:
        """Create a special broadcast address for task announcements."""
        # Using a recognizable pattern for broadcast
        return "kaspatest:qr0000000000000000000000000000000000000000"
