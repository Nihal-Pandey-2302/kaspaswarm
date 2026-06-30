"""
Transaction encoding/decoding protocol for agent communication.

Since Kaspa doesn't have smart contracts, we encode messages in transaction amounts.
This module handles the encoding/decoding logic for swarm coordination.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict
import json
import time

# Magic prefix that marks a Kaspa tx payload as a KaspaSwarm coordination message.
# The chain watcher uses this to cheaply filter swarm txs from ordinary ones.
SWARM_PAYLOAD_MAGIC = b"KSWARM1:"


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
    to_address: str = ""  # intended recipient (carried in payload; carrier tx is a self-send)


class TransactionEncoder:
    """
    Encode/decode swarm messages in Kaspa transactions.

    Coordination messages ride entirely in the transaction PAYLOAD field (see
    encode_payload/decode_payload). The transaction amount is just a dust-floored
    carrier and is not used to encode any message data.
    """

    # ── Full-message payload codec (real on-chain coordination) ──────────
    # The payload carries the FULL message: type, sender, task_id, and arbitrary
    # data (descriptions, bids, solutions, input data). This is what makes Kaspa
    # the actual coordination medium rather than a decorative anchor.

    @staticmethod
    def encode_payload(msg: "SwarmMessage") -> bytes:
        """Serialize a full SwarmMessage into tx payload bytes."""
        body = {
            "t": msg.msg_type.value,
            "s": msg.sender,
            "to": msg.to_address,   # intended recipient (carrier tx is a self-send)
            "id": msg.task_id,
            "d": msg.data,
            "ts": msg.timestamp,
        }
        return SWARM_PAYLOAD_MAGIC + json.dumps(body, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def decode_payload(payload: bytes, tx_id: str = "") -> Optional["SwarmMessage"]:
        """Parse a tx payload back into a SwarmMessage, or None if not a swarm msg."""
        if not payload or not payload.startswith(SWARM_PAYLOAD_MAGIC):
            return None
        try:
            body = json.loads(payload[len(SWARM_PAYLOAD_MAGIC):].decode("utf-8"))
            return SwarmMessage(
                msg_type=MessageType(body["t"]),
                sender=body.get("s", ""),
                task_id=body.get("id"),
                data=body.get("d", {}) or {},
                timestamp=body.get("ts", int(time.time())),
                tx_id=tx_id,
                to_address=body.get("to", ""),
            )
        except Exception as e:
            print(f"Error decoding swarm payload: {e}")
            return None

    @staticmethod
    def create_broadcast_address() -> str:
        """Create a special broadcast address for task announcements."""
        # Using a recognizable pattern for broadcast
        return "kaspatest:qr0000000000000000000000000000000000000000"
