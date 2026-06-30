"""
ChainWatcher — the *read* side of the Kaspa coordination bus.

Subscribes to Kaspa block notifications over wRPC (notifyBlockAdded), scans every
transaction's payload for KaspaSwarm coordination messages, decodes them, and
hands each decoded SwarmMessage (plus the on-chain recipient address) to a
callback. This is what turns Kaspa from a decorative anchor into the actual
medium agents coordinate through: a message is only delivered once it has been
observed inside a real block.

Runs on its own dedicated WebSocket connection so it never interferes with the
wallet's strict request/response RPC client. Auto-reconnects with backoff;
the subscription is re-established on every reconnect.

Wire shapes confirmed against rusty-kaspa rpc.proto:
  BlockAddedNotification -> { "params": { "block": RpcBlock } }
  RpcBlock.transactions[] -> RpcTransaction { payload (hex), verboseData.transactionId,
                                              outputs[].verboseData.scriptPublicKeyAddress }
"""

import asyncio
import json
from collections import deque
from typing import Awaitable, Callable, Optional, Set

from backend.kcore.transaction import (
    TransactionEncoder,
    SwarmMessage,
    SWARM_PAYLOAD_MAGIC,
)

try:
    import websockets
except ImportError:
    websockets = None


# Callback: (decoded message, on-chain recipient address or None) -> awaitable
OnMessage = Callable[[SwarmMessage, Optional[str]], Awaitable[None]]


class ChainWatcher:
    def __init__(self, ws_url: str, on_message: OnMessage):
        self.ws_url = ws_url
        self.on_message = on_message
        self._ws = None
        self._task: Optional[asyncio.Task] = None
        self.running = False
        # Bounded dedup by transactionId: a set for O(1) lookup + a deque for
        # oldest-first eviction (a wholesale clear would re-admit recent tx ids).
        self._seen_tx: Set[str] = set()
        # Large window so a tx id can't be evicted before its ~8s fallback timer
        # fires (which would reintroduce a double-delivery).
        self._seen_order: deque = deque(maxlen=50000)
        self.stats = {"blocks": 0, "swarm_msgs": 0, "errors": 0, "connected": False}

    def mark_seen(self, tx_id: str) -> bool:
        """Record a tx id as handled. Returns False if it was already seen
        (so callers can dedup the in-memory fallback against on-chain delivery)."""
        if not tx_id:
            return True
        if tx_id in self._seen_tx:
            return False
        if len(self._seen_order) >= (self._seen_order.maxlen or 5000):
            self._seen_tx.discard(self._seen_order[0])  # oldest will be evicted
        self._seen_order.append(tx_id)
        self._seen_tx.add(tx_id)
        return True

    async def start(self) -> bool:
        if websockets is None:
            print("⚠️ websockets not installed — ChainWatcher disabled")
            return False
        self.running = True
        self._task = asyncio.create_task(self._run())
        return True

    async def stop(self):
        self.running = False
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task is not None:
            self._task.cancel()

    async def _run(self):
        backoff = 1.0
        while self.running:
            try:
                async with websockets.connect(
                    self.ws_url, ping_interval=None, close_timeout=3
                ) as ws:
                    self._ws = ws
                    self.stats["connected"] = True
                    await ws.send(json.dumps(
                        {"id": 1, "method": "notifyBlockAdded", "params": {}}
                    ))
                    print(f"👁️  ChainWatcher subscribed to blocks at {self.ws_url}")
                    backoff = 1.0
                    async for raw in ws:
                        if not self.running:
                            break
                        await self._handle_raw(raw)
            except Exception as e:
                if not self.running:
                    break
                self.stats["errors"] += 1
                print(f"⚠️ ChainWatcher connection lost ({e}); reconnecting in {backoff:.0f}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)
            finally:
                self.stats["connected"] = False
                self._ws = None

    async def _handle_raw(self, raw):
        try:
            data = json.loads(raw)
        except Exception:
            return
        # Notifications carry params.block; the subscription ack (id-matched) won't.
        params = data.get("params") or {}
        block = params.get("block")
        if not block:
            return
        self.stats["blocks"] += 1
        for tx in (block.get("transactions") or []):
            try:
                await self._handle_tx(tx)
            except Exception as e:
                self.stats["errors"] += 1
                print(f"⚠️ ChainWatcher tx error: {e}")

    async def _handle_tx(self, tx):
        payload_hex = tx.get("payload") or ""
        if not payload_hex:
            return
        try:
            payload = bytes.fromhex(payload_hex)
        except ValueError:
            return
        if not payload.startswith(SWARM_PAYLOAD_MAGIC):
            return

        tx_id = (tx.get("verboseData") or {}).get("transactionId", "")
        if tx_id and not self.mark_seen(tx_id):
            return  # already handled (seen in an earlier block view or by the fallback)

        msg = TransactionEncoder.decode_payload(payload, tx_id=tx_id)
        if msg is None:
            return

        # Recipient comes from the payload (carrier txs are self-sends now).
        recipient = getattr(msg, "to_address", "") or None
        self.stats["swarm_msgs"] += 1
        await self.on_message(msg, recipient)
