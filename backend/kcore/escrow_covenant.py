"""
Per-task escrow covenant — on-chain settlement for a single task's reward.

At assignment the coordinator LOCKS the reward into a P2SH covenant. That covenant,
enforced by Kaspa consensus, allows the funds to move in exactly two ways:

  • SETTLE  — a single output to the PINNED solver address (coordinator authorises
              once the solution is verified) → the solver is paid.
  • REFUND  — a single output back to the coordinator (on timeout / failed / cancel).

The coordinator is the settlement authority (it is also the verifier in this
system), but the covenant guarantees the locked reward can reach ONLY the rightful
solver or return to the coordinator — it can never be redirected elsewhere, and
the recipient/output-count are enforced by the chain.

Reuses the treasury-vault spend plumbing. PoC — testnet-10.

Redeem script (spent stack top-first):
    SETTLE unlock = <coordSig> <OpTrue>
    REFUND unlock = <coordSig> <OpFalse>

    OpIf                                            // SETTLE -> solver
        OpTxOutputCount OpTrue OpEqualVerify
        OpFalse OpTxOutputSpk <solverSpk> OpEqualVerify
        <coordinatorPubkey> OpCheckSig
    OpElse                                          // REFUND -> coordinator
        OpTxOutputCount OpTrue OpEqualVerify
        OpFalse OpTxOutputSpk <coordinatorSpk> OpEqualVerify
        <coordinatorPubkey> OpCheckSig
    OpEndIf
"""
from __future__ import annotations

from dataclasses import dataclass

from kaspa import Opcodes, ScriptBuilder, address_from_script_public_key, pay_to_address_script, pay_to_script_hash_signature_script, Address

from backend.kcore.treasury_vault import _OP_FALSE, _OP_TRUE, _spk_bytes


@dataclass
class EscrowVault:
    """A per-task escrow covenant (spend_vault-compatible)."""
    redeem_script: ScriptBuilder
    covenant_spk: object
    address: object
    solver_spk: object
    coordinator_spk: object

    @property
    def redeem_bytes(self) -> bytes:
        return bytes.fromhex(self.redeem_script.to_string())

    def address_str(self) -> str:
        return self.address.to_string()


def build_escrow_redeem_script(coordinator_xonly_hex: str, solver_spk, coordinator_spk,
                               task_id: int = 0) -> ScriptBuilder:
    coord_pk = bytes.fromhex(coordinator_xonly_hex)
    solver_b = _spk_bytes(solver_spk)
    coord_b = _spk_bytes(coordinator_spk)
    return (
        ScriptBuilder(covenants_enabled=True)
        # Bind task_id into the script (pushed then dropped — a no-op at runtime)
        # so each task derives a UNIQUE P2SH address. Without this, two tasks for
        # the same (coordinator, solver) pair would share one covenant UTXO and
        # settle/refund could grab the wrong task's funds.
        .add_i64(int(task_id))
        .add_op(Opcodes.OpDrop)
        .add_op(Opcodes.OpIf)
        # SETTLE -> pay the pinned solver
        .add_op(Opcodes.OpTxOutputCount)
        .add_op(Opcodes.OpTrue)
        .add_op(Opcodes.OpEqualVerify)
        .add_op(Opcodes.OpFalse)
        .add_op(Opcodes.OpTxOutputSpk)
        .add_data(solver_b)
        .add_op(Opcodes.OpEqualVerify)
        .add_data(coord_pk)
        .add_op(Opcodes.OpCheckSig)
        # REFUND -> back to the coordinator
        .add_op(Opcodes.OpElse)
        .add_op(Opcodes.OpTxOutputCount)
        .add_op(Opcodes.OpTrue)
        .add_op(Opcodes.OpEqualVerify)
        .add_op(Opcodes.OpFalse)
        .add_op(Opcodes.OpTxOutputSpk)
        .add_data(coord_b)
        .add_op(Opcodes.OpEqualVerify)
        .add_data(coord_pk)
        .add_op(Opcodes.OpCheckSig)
        .add_op(Opcodes.OpEndIf)
    )


def derive_escrow(coordinator_xonly_hex: str, solver_addr: str, coordinator_addr: str,
                  network_type: str = "testnet", task_id: int = 0) -> EscrowVault:
    solver_spk = pay_to_address_script(Address(solver_addr))
    coordinator_spk = pay_to_address_script(Address(coordinator_addr))
    redeem = build_escrow_redeem_script(coordinator_xonly_hex, solver_spk, coordinator_spk, task_id)
    covenant_spk = redeem.create_pay_to_script_hash_script()
    address = address_from_script_public_key(covenant_spk, network_type)
    return EscrowVault(redeem, covenant_spk, address, solver_spk, coordinator_spk)


def settle_unlock_script(vault: EscrowVault, coordinator_sig_hex: str) -> bytes:
    """SETTLE branch: <coordSig> <OpTrue> <redeem> — pays the solver."""
    prefix = bytes.fromhex(coordinator_sig_hex) + _OP_TRUE
    return bytes.fromhex(pay_to_script_hash_signature_script(vault.redeem_bytes, prefix))


def refund_unlock_script(vault: EscrowVault, coordinator_sig_hex: str) -> bytes:
    """REFUND branch: <coordSig> <OpFalse> <redeem> — returns to the coordinator."""
    prefix = bytes.fromhex(coordinator_sig_hex) + _OP_FALSE
    return bytes.fromhex(pay_to_script_hash_signature_script(vault.redeem_bytes, prefix))
