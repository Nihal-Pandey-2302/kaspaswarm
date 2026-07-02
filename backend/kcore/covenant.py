"""
Escrow / stake-slash layer for trustless agent settlement.

Two interchangeable backends behind one interface:

- InProtocolEscrow  — works TODAY. Models the lock -> release/slash lifecycle in
  the coordinator process and tracks totals for the UI/demo. The economic
  guarantees are enforced by the coordinator (the current trust model).

- CovenantEscrow    — the on-chain version. Locks the reward + the solver's stake
  in a SilverScript-style escrow covenant so settlement is enforced by Kaspa
  itself, not by trusting the coordinator. Still a stub with the integration
  points marked; swapping it in requires NO change to the coordinator.

NOTE: the on-chain covenant building blocks this stub needs are now REAL and
validated — see backend/kcore/treasury_vault.py (KIP-10 redeem script +
P2SH derivation + spend_vault) and backend/covenant_demo.py (a working
governance covenant on testnet-10). CovenantEscrow can be implemented by reusing
treasury_vault.spend_vault with an escrow (settle/timeout/cancel) redeem script.

This is the seam that turns the in-protocol economic model (bidding, reputation,
soft-slash) into trustless, chain-enforced settlement.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class EscrowRecord:
    task_id: int
    coordinator: str
    solver: str
    reward: int
    stake: int
    state: str = "locked"  # locked -> released | slashed | cancelled


class EscrowManager:
    """Interface for task escrow backends."""

    # True if release() itself performs the on-chain payout to the solver (so the
    # coordinator must NOT also send a separate reward tx). False for in-protocol.
    pays_on_release = False

    async def lock(self, task_id: int, coordinator: str, solver: str, reward: int,
                   stake: int, coordinator_priv: str = None) -> EscrowRecord:
        raise NotImplementedError

    async def release(self, task_id: int) -> bool:
        """Verified solution: reward + stake -> solver."""
        raise NotImplementedError

    async def slash(self, task_id: int) -> bool:
        """Failed/timed-out: reward refunded to coordinator, stake slashed."""
        raise NotImplementedError

    async def cancel(self, task_id: int) -> bool:
        """Unwind without reward or slash (e.g. coordinator payout failure)."""
        raise NotImplementedError

    def stats(self) -> Dict:
        raise NotImplementedError


class InProtocolEscrow(EscrowManager):
    """Coordinator-enforced escrow (works now). Tracks lifecycle + totals."""

    def __init__(self):
        self._records: Dict[int, EscrowRecord] = {}
        self._totals = {"locked": 0, "released": 0, "slashed": 0, "cancelled": 0,
                        "kas_locked": 0, "kas_released": 0, "kas_slashed": 0}

    async def lock(self, task_id, coordinator, solver, reward, stake, coordinator_priv=None):
        rec = EscrowRecord(task_id, coordinator, solver, int(reward), int(stake))
        self._records[task_id] = rec
        self._totals["locked"] += 1
        self._totals["kas_locked"] += rec.reward + rec.stake
        print(f"🔒 Escrow locked for task {task_id}: reward={rec.reward} + stake={rec.stake} sompi")
        return rec

    async def release(self, task_id):
        rec = self._records.get(task_id)
        if not rec or rec.state != "locked":
            return False
        rec.state = "released"
        self._totals["released"] += 1
        self._totals["kas_released"] += rec.reward + rec.stake
        print(f"✅ Escrow released for task {task_id}: {rec.reward + rec.stake} sompi -> {rec.solver[:16]}…")
        return True

    async def slash(self, task_id):
        rec = self._records.get(task_id)
        if not rec or rec.state != "locked":
            return False
        rec.state = "slashed"
        self._totals["slashed"] += 1
        self._totals["kas_slashed"] += rec.stake
        print(f"⚔️ Escrow slashed for task {task_id}: stake={rec.stake} sompi forfeited by {rec.solver[:16]}…")
        return True

    async def cancel(self, task_id):
        rec = self._records.get(task_id)
        if not rec or rec.state != "locked":
            return False
        rec.state = "cancelled"
        self._totals["cancelled"] += 1
        print(f"↩️ Escrow cancelled for task {task_id} (no reward/slash — stake returned)")
        return True

    def stats(self):
        return dict(self._totals)


class CovenantEscrow(EscrowManager):
    """REAL on-chain escrow via a per-task KIP-10 covenant (testnet-10).

    Enabled with COVENANT_ESCROW=true. At lock() the coordinator funds a covenant
    UTXO with the reward; release() spends it to the solver (settle branch);
    slash()/cancel() refund it to the coordinator (refund branch). The covenant
    (backend/kcore/escrow_covenant.py) lets the locked reward reach ONLY the
    pinned solver or the coordinator — enforced by Kaspa consensus.

    Opt-in because per-task on-chain settlement adds a funding + confirmation tx
    per task; the default InProtocolEscrow keeps the live swarm fast.
    """

    pays_on_release = True

    def __init__(self, network_id: str = None):
        import os
        from backend.kcore.treasury_vault import network_type_from_id
        self.network_id = network_id or os.getenv("KASPA_NETWORK_ID", "testnet-10")
        self.network_type = network_type_from_id(self.network_id)
        self._client = None
        self._records: Dict[int, dict] = {}
        self._totals = {"locked": 0, "released": 0, "slashed": 0, "cancelled": 0,
                        "kas_locked": 0, "kas_released": 0, "kas_slashed": 0}

    async def _rpc(self):
        if self._client is None:
            from kaspa import Resolver, RpcClient
            self._client = RpcClient(resolver=Resolver(), network_id=self.network_id)
            await self._client.connect()
        return self._client

    async def _wait_utxo(self, address_str: str, tries: int = 40):
        client = await self._rpc()
        import asyncio
        for _ in range(tries):
            entries = (await client.get_utxos_by_addresses({"addresses": [address_str]})).get("entries", [])
            if entries:
                return max(entries, key=lambda u: u["utxoEntry"]["amount"])
            await asyncio.sleep(2)
        raise TimeoutError(f"escrow covenant UTXO never appeared at {address_str}")

    async def lock(self, task_id, coordinator, solver, reward, stake, coordinator_priv=None):
        from kaspa import Keypair, PrivateKey
        from backend.kcore.escrow_covenant import derive_escrow
        from backend.kcore.sdk_transport import get_transport
        if not coordinator_priv:
            raise RuntimeError("CovenantEscrow.lock requires the coordinator private key")
        kp = Keypair.from_private_key(PrivateKey(coordinator_priv))
        vault = derive_escrow(kp.xonly_public_key, solver, coordinator, self.network_type)
        txid = await get_transport().send(coordinator_priv, coordinator, vault.address_str(), int(reward), b"")
        if isinstance(txid, str) and txid.startswith("failed"):
            raise RuntimeError(f"escrow lock funding failed: {txid}")
        rec = EscrowRecord(task_id, coordinator, solver, int(reward), int(stake))
        self._records[task_id] = {"rec": rec, "vault": vault, "coord_priv": coordinator_priv, "fund_txid": txid}
        self._totals["locked"] += 1
        self._totals["kas_locked"] += int(reward)
        print(f"🔒 Covenant escrow locked for task {task_id}: {reward} sompi -> {vault.address_str()[:20]}… (fund {txid[:12]}…)")
        return rec

    async def _spend(self, task_id, to_spk, unlock_builder):
        from kaspa import PrivateKey, create_input_signature
        from backend.kcore.treasury_vault import spend_vault
        info = self._records.get(task_id)
        if not info or info["rec"].state != "locked":
            return None
        client = await self._rpc()
        vault = info["vault"]
        coord_key = PrivateKey(info["coord_priv"])
        utxo = await self._wait_utxo(vault.address_str())

        def sign_fn(tx):
            return unlock_builder(vault, create_input_signature(tx, 0, coord_key))

        txid, _pay = await spend_vault(client, self.network_id, vault, utxo, to_spk, sign_fn, 1)
        return txid

    async def release(self, task_id):
        from backend.kcore.escrow_covenant import settle_unlock_script
        info = self._records.get(task_id)
        if not info or info["rec"].state != "locked":
            return False
        try:
            txid = await self._spend(task_id, info["vault"].solver_spk, settle_unlock_script)
        except Exception as e:
            print(f"⚠️ Covenant escrow release failed for task {task_id}: {e}")
            return False
        if not txid:
            return False
        info["rec"].state = "released"
        self._totals["released"] += 1
        self._totals["kas_released"] += info["rec"].reward
        print(f"✅ Covenant escrow settled to solver for task {task_id}: {txid[:16]}…")
        return True

    async def _refund(self, task_id, kind):
        from backend.kcore.escrow_covenant import refund_unlock_script
        info = self._records.get(task_id)
        if not info or info["rec"].state != "locked":
            return False
        try:
            txid = await self._spend(task_id, info["vault"].coordinator_spk, refund_unlock_script)
        except Exception as e:
            print(f"⚠️ Covenant escrow refund ({kind}) failed for task {task_id}: {e}")
            return False
        if not txid:
            return False
        info["rec"].state = kind
        self._totals[kind if kind in self._totals else "cancelled"] += 1
        print(f"↩️ Covenant escrow refunded to coordinator ({kind}) for task {task_id}: {txid[:16]}…")
        return True

    async def slash(self, task_id):
        return await self._refund(task_id, "slashed")

    async def cancel(self, task_id):
        return await self._refund(task_id, "cancelled")

    def stats(self):
        return {**self._totals, "backend": "covenant", "network": self.network_id}
