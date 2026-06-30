"""
Kaspa wRPC Client — WebSocket JSON-RPC for direct Kaspa node communication.

Simple send/receive pattern — no background tasks, no hanging.
"""

import asyncio
import json
from typing import Dict, List, Optional

try:
    import websockets
except ImportError:
    websockets = None


class KaspaRpcClient:
    """WebSocket JSON-RPC client for Kaspa nodes."""

    def __init__(self, ws_url: str = "ws://127.0.0.1:18210"):
        self.ws_url = ws_url
        self._ws = None
        self._request_id = 0

    async def connect(self) -> bool:
        """Connect to the Kaspa node via WebSocket."""
        if websockets is None:
            print("⚠️ websockets not installed")
            return False
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(self.ws_url, ping_interval=None, close_timeout=3),
                timeout=5,
            )
            print(f"✅ Connected to {self.ws_url}")
            return True
        except Exception as e:
            print(f"❌ Connect failed: {e}")
            self._ws = None
            return False

    async def _rpc_call(self, method: str, params: Optional[Dict] = None, timeout: float = 10.0) -> Dict:
        """Send JSON-RPC request and wait for matching response."""
        if self._ws is None:
            raise ConnectionError("Not connected")

        self._request_id += 1
        rid = self._request_id
        msg = json.dumps({"id": rid, "method": method, "params": params or {}})
        await self._ws.send(msg)

        # Read responses until we get the one matching our request id
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"RPC '{method}' timed out")
            raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            data = json.loads(raw)
            if data.get("id") == rid:
                if "error" in data and data["error"]:
                    raise Exception(f"RPC error: {data['error']}")
                return data.get("params", data.get("result", {}))

    # ── High-level API ──────────────────────────────────────

    async def get_server_info(self) -> Dict:
        return await self._rpc_call("getServerInfo")

    async def get_utxos_by_addresses(self, addresses: List[str]) -> List[Dict]:
        r = await self._rpc_call("getUtxosByAddresses", {"addresses": addresses})
        return r.get("entries", [])

    async def submit_transaction(self, transaction: Dict, allow_orphan: bool = False) -> str:
        r = await self._rpc_call("submitTransaction", {
            "transaction": transaction, "allowOrphan": allow_orphan
        })
        return r.get("transactionId", "")

    async def get_balance_by_address(self, address: str) -> int:
        r = await self._rpc_call("getBalanceByAddress", {"address": address})
        return int(r.get("balance", 0))

    async def close(self):
        if self._ws:
            await self._ws.close()
            self._ws = None
