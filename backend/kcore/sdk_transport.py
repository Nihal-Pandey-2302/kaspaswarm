"""
SDK-backed live transport — real on-chain coordination via the official Kaspa
Python SDK + Resolver (community node auto-selection) on testnet-10.

Validated end-to-end against TN10 (see backend/sdk_live_test.py):
  - connect:  RpcClient(resolver=Resolver(), network_id="testnet-10")
  - send:     create_transactions(...).sign([PrivateKey]).submit(rpc)   (change-aware)
  - watch:    add_event_listener("all", cb) + subscribe_block_added
              events arrive as {"type":"BlockAdded","data":{"block":{...}}}

Two SEPARATE long-lived connections: one for the block-stream subscription, one
for request/response (send + balance) — sharing a single socket made block
streaming and submits contend and drop. Sends are serialized PER SENDER ADDRESS
(UTXO races are per-address), so different agents send concurrently.

NOTE: imports the installed `kaspa` SDK. The local package was renamed to
`kcore` precisely so this `import kaspa` resolves to the SDK, not our package.
"""
import asyncio
import os
import re
from collections import defaultdict, deque
from typing import Awaitable, Callable, Optional

from kaspa import Resolver, RpcClient, PrivateKey, PaymentOutput, create_transactions, Address

from backend.kcore.transaction import TransactionEncoder, SWARM_PAYLOAD_MAGIC

NETWORK_ID = os.getenv("KASPA_NETWORK_ID", "testnet-10")
MIN_OUTPUT = 20_000_000       # 0.2 KAS dust floor
PRIORITY_FEE = 2_000_000      # 0.02 KAS — covers payload compute-mass minimum
MAX_FEE_GUARD = 100_000_000   # never submit a tx whose fee exceeds 1 KAS

# Callback: (decoded message, recipient address or None) -> awaitable
OnMessage = Callable[["object", Optional[str]], Awaitable[None]]


class SdkTransport:
    def __init__(self):
        self._sub_rpc: Optional[RpcClient] = None     # block-stream subscription
        self._req_rpc: Optional[RpcClient] = None     # request/response (send, balance)
        self._sub_lock = asyncio.Lock()
        self._req_lock = asyncio.Lock()
        self._addr_locks: dict = defaultdict(asyncio.Lock)  # per-address send serialization
        self._on_message: Optional[OnMessage] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed = False
        # Dedup by tx id: a tx is referenced by multiple blocks on a blockDAG.
        self._seen_tx: set = set()
        self._seen_order: deque = deque(maxlen=50000)
        self.stats = {"blocks": 0, "swarm_msgs": 0, "errors": 0, "connected": False}

    def mark_seen(self, tx_id: str) -> bool:
        if not tx_id:
            return True
        if tx_id in self._seen_tx:
            return False
        if len(self._seen_order) >= (self._seen_order.maxlen or 50000):
            self._seen_tx.discard(self._seen_order[0])
        self._seen_order.append(tx_id)
        self._seen_tx.add(tx_id)
        return True

    # ── request/response client (send + balance), reused; no per-call churn ──
    async def _ensure_req_rpc(self) -> RpcClient:
        if self._req_rpc is not None and self._req_rpc.is_connected:
            return self._req_rpc
        async with self._req_lock:
            if self._req_rpc is not None and self._req_rpc.is_connected:
                return self._req_rpc
            if self._req_rpc is not None:
                try:
                    await self._req_rpc.disconnect()
                except Exception:
                    pass
            self._req_rpc = RpcClient(resolver=Resolver(), network_id=NETWORK_ID)
            await self._req_rpc.connect()
            return self._req_rpc

    async def _reset_req_rpc(self):
        async with self._req_lock:
            if self._req_rpc is not None:
                try:
                    await self._req_rpc.disconnect()
                except Exception:
                    pass
            self._req_rpc = None

    async def send(self, priv_hex: str, from_addr: str, to_addr: str,
                   amount: int, payload: bytes) -> str:
        """Build (change-aware) + sign + submit a real tx on the reused request
        client. Serialized PER from_addr (UTXO races are per-address); different
        addresses proceed concurrently. Retries on a dropped node."""
        amount = max(int(amount), MIN_OUTPUT)
        priority = PRIORITY_FEE  # bumped adaptively if the node wants more (mass-based)
        async with self._addr_locks[from_addr]:
            for attempt in range(4):
                try:
                    rpc = await self._ensure_req_rpc()
                    resp = await rpc.get_utxos_by_addresses({"addresses": [from_addr]})
                    entries = resp["entries"] if isinstance(resp, dict) else resp
                    if not entries:
                        return "failed_no_utxos"
                    built = create_transactions(
                        network_id=NETWORK_ID,
                        entries=entries,
                        change_address=Address(from_addr),
                        outputs=[PaymentOutput(Address(to_addr), amount)],
                        payload=payload,
                        priority_fee=priority,
                    )
                    pendings = built["transactions"]
                    if not pendings:
                        return "failed_build"
                    pk = PrivateKey(priv_hex)
                    last_txid = ""
                    for pending in pendings:
                        fee = pending.fee_amount
                        if fee is None or fee > MAX_FEE_GUARD:
                            print(f"⚠️ SDK send aborted: fee={fee} exceeds guard")
                            return "failed_fee_guard"
                        pending.sign([pk])
                        last_txid = await pending.submit(rpc)
                    return last_txid
                except Exception as e:
                    msg = str(e)
                    # The node rejects low fees with "required amount of N" (mass-based,
                    # scales with payload size). Parse it and retry with that fee.
                    m = re.search(r"required amount of (\d+)", msg)
                    if m:
                        priority = min(int(m.group(1)) + 200_000, MAX_FEE_GUARD)
                        print(f"⚠️ SDK send fee too low; bumping priority_fee to {priority}")
                        continue  # rebuild immediately with the higher fee
                    print(f"⚠️ SDK send attempt {attempt+1}/4 failed: {msg}")
                    await self._reset_req_rpc()
                    await asyncio.sleep(0.6)
        return "failed_sdk"

    async def get_balance(self, address: str) -> int:
        """Balance via the request client (NOT the subscription client, so a balance
        poll can never disrupt the block stream)."""
        try:
            rpc = await self._ensure_req_rpc()
            r = await rpc.get_balance_by_address({"address": address})
            return int(r["balance"]) if isinstance(r, dict) else int(r)
        except Exception as e:
            print(f"⚠️ SDK balance error: {e}")
            await self._reset_req_rpc()
            return 0

    # ── subscription client (block stream) ──
    async def subscribe(self, on_message: OnMessage):
        self._on_message = on_message
        self._loop = asyncio.get_running_loop()
        await self._connect_sub()
        print("👁️  SDK transport subscribed to block-added")

    async def _connect_sub(self) -> bool:
        async with self._sub_lock:
            if self._sub_rpc is not None and self._sub_rpc.is_connected:
                return True
            if self._sub_rpc is not None:
                try:
                    await self._sub_rpc.disconnect()
                except Exception:
                    pass
            self._sub_rpc = RpcClient(resolver=Resolver(), network_id=NETWORK_ID)
            await self._sub_rpc.connect()
            self.stats["connected"] = bool(self._sub_rpc.is_connected)
            print(f"🔌 SDK transport connected to {NETWORK_ID} via {self._sub_rpc.url}")
            if self._on_message is not None:
                try:
                    self._sub_rpc.add_event_listener("all", self._on_event)
                    await self._sub_rpc.subscribe_block_added()
                except Exception as e:
                    print(f"⚠️ re-subscribe failed: {e}")
            return self.stats["connected"]

    def _on_event(self, event, *_):
        # Sync callback (the SDK does not await async listeners). Parse here, then
        # hand off async delivery onto the event loop thread-safely.
        try:
            if self._closed or not isinstance(event, dict) or event.get("type") != "BlockAdded":
                return
            block = (event.get("data") or {}).get("block")
            if not block:
                return
            self.stats["blocks"] += 1
            for tx in (block.get("transactions") or []):
                self._handle_tx(tx)
        except Exception as e:
            self.stats["errors"] += 1
            print(f"⚠️ SDK event error: {e}")

    def _handle_tx(self, tx):
        phex = tx.get("payload") or ""
        if not phex:
            return
        try:
            pb = bytes.fromhex(phex)
        except ValueError:
            return
        if not pb.startswith(SWARM_PAYLOAD_MAGIC):
            return
        tx_id = (tx.get("verboseData") or {}).get("transactionId", "")
        if not self.mark_seen(tx_id):
            return  # already delivered from an earlier block referencing this tx
        msg = TransactionEncoder.decode_payload(pb, tx_id=tx_id)
        if msg is None:
            return
        # Recipient comes from the PAYLOAD (carrier txs are self-sends now), not the
        # tx output address.
        recipient = getattr(msg, "to_address", "") or None
        self.stats["swarm_msgs"] += 1
        if self._on_message and self._loop and not self._loop.is_closed():
            fut = asyncio.run_coroutine_threadsafe(self._on_message(msg, recipient), self._loop)
            fut.add_done_callback(self._log_delivery_result)

    def _log_delivery_result(self, fut):
        try:
            fut.result()
        except Exception as e:
            self.stats["errors"] += 1
            print(f"⚠️ on-chain delivery error: {e}")

    async def close(self):
        self._closed = True
        self._on_message = None
        self._loop = None
        for client in (self._sub_rpc, self._req_rpc):
            if client is not None:
                try:
                    client.remove_all_event_listeners()
                except Exception:
                    pass
                try:
                    await client.disconnect()
                except Exception:
                    pass
        self._sub_rpc = None
        self._req_rpc = None
        self.stats["connected"] = False


# Shared singleton. A closed instance is replaced so start/stop/restart is clean.
_transport: Optional[SdkTransport] = None


def get_transport() -> SdkTransport:
    global _transport
    if _transport is None or _transport._closed:
        _transport = SdkTransport()
    return _transport
