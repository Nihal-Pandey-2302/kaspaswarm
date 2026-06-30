"""
Escrow / stake-slash layer for trustless agent settlement.

Two interchangeable backends behind one interface:

- InProtocolEscrow  — works TODAY. Models the lock -> release/slash lifecycle in
  the coordinator process and tracks totals for the UI/demo. The economic
  guarantees are enforced by the coordinator (the current trust model).

- CovenantEscrow    — the on-chain version. Locks the reward + the solver's stake
  in the SilverScript `AgentEscrow` covenant (see backend/covenants/agent_escrow.sil)
  so settlement is enforced by Kaspa itself, not by trusting the coordinator.
  Requires Testnet-12 (covenants/KIP-10) + the silverscript compiler, so it is a
  stub with the integration points marked. Swapping it in requires NO change to
  the coordinator — both backends share the same interface.

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

    def lock(self, task_id: int, coordinator: str, solver: str, reward: int, stake: int) -> EscrowRecord:
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

    def lock(self, task_id, coordinator, solver, reward, stake):
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
    """On-chain escrow via the SilverScript AgentEscrow covenant (Testnet-12).

    NOT YET ACTIVE — requires:
      1. Compiling backend/covenants/agent_escrow.sil with the silverscript compiler.
      2. A TN12 node + funded TN12 addresses for coordinator and solvers.
      3. Wallet support for building/spending P2SH-style covenant outputs
         (the current wallet does P2PK only).

    The method bodies below mark exactly where each on-chain step plugs in. Until
    then, SwarmOrchestrator uses InProtocolEscrow.
    """

    def __init__(self, wallet, compiled_covenant=None):
        self.wallet = wallet
        self.covenant = compiled_covenant  # output of the silverscript compiler
        self._records: Dict[int, EscrowRecord] = {}

    def lock(self, task_id, coordinator, solver, reward, stake):
        # TODO(TN12): build a tx whose output pays (reward+stake) to the covenant
        # scriptPublicKey instantiated with (coordinator, solver, verifier,
        # reward, stake, deadline). Broadcast and record the covenant UTXO.
        raise NotImplementedError("CovenantEscrow requires TN12 + compiled covenant")

    async def release(self, task_id):
        # TODO(TN12): spend the covenant UTXO via settle(verifierSig) -> solver.
        raise NotImplementedError

    async def slash(self, task_id):
        # TODO(TN12): spend via timeoutSlash(coordinatorSig) -> coordinator.
        raise NotImplementedError

    async def cancel(self, task_id):
        # TODO(TN12): spend via cancel(coordinatorSig, solverSig) -> unwind.
        raise NotImplementedError

    def stats(self):
        return {"backend": "covenant", "active": False}
