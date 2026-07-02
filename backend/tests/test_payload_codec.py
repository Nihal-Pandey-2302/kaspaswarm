"""Round-trip tests for the on-chain message codec (the KSWARM1 tx payload).

This is what makes Kaspa the coordination bus, so the encode->decode contract
(including the recipient routing field) must stay stable.
"""
from backend.kcore.transaction import MessageType, SwarmMessage, TransactionEncoder


def test_payload_roundtrip_preserves_all_fields():
    msg = SwarmMessage(
        msg_type=MessageType.TASK_ASSIGNMENT,
        sender="kaspatest:coordinator",
        task_id=42,
        data={"bid_amount": 50_000_000, "note": "hello swarm"},
        timestamp=1_700_000_000,
        to_address="kaspatest:solver",
    )
    payload = TransactionEncoder.encode_payload(msg)
    assert isinstance(payload, bytes) and len(payload) > 0

    decoded = TransactionEncoder.decode_payload(payload)
    assert decoded is not None
    assert decoded.msg_type == MessageType.TASK_ASSIGNMENT
    assert decoded.sender == "kaspatest:coordinator"
    assert decoded.task_id == 42
    assert decoded.to_address == "kaspatest:solver"          # recipient routing survives
    assert decoded.data["bid_amount"] == 50_000_000
    assert decoded.data["note"] == "hello swarm"


def test_decode_rejects_non_swarm_payload():
    # Random / non-KSWARM1 payloads must decode to None (not raise), so the watcher
    # can skip unrelated transactions.
    assert TransactionEncoder.decode_payload(b"") is None
    assert TransactionEncoder.decode_payload(b"not-a-swarm-tx") is None
