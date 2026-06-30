"""
End-to-end LIVE test of the on-chain coordination bus.

Sends ONE real coordination message as a Kaspa transaction (payload-encoded) from
the funded coordinator address, while a ChainWatcher is subscribed to blocks. If
the watcher decodes that exact message back out of a real block, the full
"Kaspa is the bus" loop is proven against your node.

Usage (from project root, with a synced testnet node + .env populated):
    python backend/live_test.py

Required env: COORDINATOR_ADDRESS, COORDINATOR_PRIVATE_KEY, KASPA_WS_URL (optional).
"""
import asyncio
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from backend.kcore.wallet import KaspaWallet, KaspaAddress  # noqa: E402
from backend.kcore.chain_watcher import ChainWatcher  # noqa: E402
from backend.kcore.transaction import TransactionEncoder, SwarmMessage, MessageType  # noqa: E402
from backend.kcore.schnorr import get_public_key  # noqa: E402

TIMEOUT_S = 120


async def main():
    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_key = os.getenv("COORDINATOR_PRIVATE_KEY")
    ws_url = os.getenv("KASPA_WS_URL", "ws://127.0.0.1:18210")
    if not (coord_addr and coord_key):
        sys.exit("Set COORDINATOR_ADDRESS and COORDINATOR_PRIVATE_KEY in .env")

    wallet = KaspaWallet(mock_mode=False)
    coord = KaspaAddress(
        address=coord_addr, private_key=coord_key,
        public_key=get_public_key(bytes.fromhex(coord_key)).hex(), balance=0,
    )

    received = []

    async def on_message(msg: SwarmMessage, to_addr):
        received.append((msg, to_addr))
        print(f"👁️  watcher decoded from block: type={msg.msg_type.name} "
              f"task={msg.task_id} tx={msg.tx_id} data={msg.data}")

    watcher = ChainWatcher(ws_url, on_message)
    await watcher.start()
    await asyncio.sleep(2)  # let the subscription establish

    # A unique marker so we only match OUR message, not unrelated swarm traffic.
    marker = int(time.time())
    msg = SwarmMessage(
        msg_type=MessageType.TASK_ANNOUNCEMENT,
        sender=coord_addr,
        task_id=marker % 1_000_000,
        data={"live_test": marker, "description": "live bus probe"},
        timestamp=marker,
    )
    payload = TransactionEncoder.encode_payload(msg)

    print(f"📤 broadcasting probe tx (marker={marker})...")
    tx_id = await wallet.send_transaction(
        from_addr=coord, to_addr=coord_addr, amount=20_000_000, payload=payload
    )
    if not isinstance(tx_id, str) or tx_id.startswith("failed"):
        await watcher.stop()
        sys.exit(f"❌ broadcast failed: {tx_id} (node down? insufficient funds?)")
    print(f"   broadcast tx_id={tx_id}; waiting up to {TIMEOUT_S}s for it in a block...")

    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        if any(m.data.get("live_test") == marker for m, _ in received):
            print(f"\n✅ PASS — probe round-tripped through Kaspa in "
                  f"{TIMEOUT_S - int(deadline - time.time())}s. "
                  f"Watcher stats: {watcher.stats}")
            await watcher.stop()
            return
        await asyncio.sleep(1)

    print(f"\n❌ FAIL — probe not seen in a block within {TIMEOUT_S}s. "
          f"Watcher stats: {watcher.stats}")
    print("   Check: is the node synced? does notifyBlockAdded stream blocks? "
          "do block txs include the 'payload' field on this node version?")
    await watcher.stop()
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
