"""
Agent Treasury Vault — an on-chain spending covenant for KaspaSwarm agents.

An agent's payout wallet is a P2SH UTXO whose redeem script is a KIP-10 covenant
that *governs how the agent may spend*. Kaspa itself enforces the policy:

  • AUTO branch  — the agent signs alone, but the covenant requires the payment
    to be a single output whose value is <= `threshold` (the per-transaction cap).
    An autonomous over-cap spend is REJECTED by consensus, not by our code.

  • MANUAL branch — the agent AND a human owner co-sign; any amount is allowed.
    This is the "high-risk spend needs human approval" escape hatch.

This turns "trust the agent not to drain its wallet" into "the chain won't let it."
It is the on-chain enforcement layer beneath KaspaSwarm's in-protocol escrow.

Requires the covenant-enabled Kaspa SDK (kaspa>=2.0.0: ScriptBuilder(covenants_enabled),
KIP-10 introspection opcodes). Runs on testnet-10 (Toccata). PoC — testnet only.

Redeem script (spent stack shown top-first):
    AUTO   unlock = <agentSig> <OpTrue>
    MANUAL unlock = <ownerSig> <agentSig> <OpFalse>

    OpIf                          // selector truthy -> AUTO
        OpTxOutputCount OpTrue OpEqualVerify   // exactly 1 output
        OpFalse OpTxOutputAmount               // output[0].value
        <threshold> OpLessThanOrEqual OpVerify // require value <= cap
        <agentPubkey> OpCheckSig               // agent authorises
    OpElse                        // MANUAL -> agent + owner, any amount
        <agentPubkey> OpCheckSigVerify
        <ownerPubkey> OpCheckSig
    OpEndIf
"""
from __future__ import annotations

from dataclasses import dataclass

from kaspa import (
    Opcodes,
    ScriptBuilder,
    address_from_script_public_key,
    pay_to_script_hash_signature_script,
)

# Raw opcode bytes for the unlocking-script selector (built once, no magic numbers).
# ScriptBuilder.to_string() returns hex; convert to raw bytes.
_OP_TRUE = bytes.fromhex(ScriptBuilder().add_op(Opcodes.OpTrue).to_string())    # push 1  (AUTO)
_OP_FALSE = bytes.fromhex(ScriptBuilder().add_op(Opcodes.OpFalse).to_string())  # push "" (MANUAL)


@dataclass
class Vault:
    """A derived treasury vault: its redeem script, P2SH spk, and address."""
    redeem_script: ScriptBuilder
    covenant_spk: object          # ScriptPublicKey
    address: object               # Address
    agent_xonly: str              # hex x-only pubkey (32 bytes)
    owner_xonly: str
    threshold: int                # per-tx auto-spend cap, in sompi

    @property
    def redeem_bytes(self) -> bytes:
        return bytes.fromhex(self.redeem_script.to_string())

    def address_str(self) -> str:
        return self.address.to_string()


def build_redeem_script(agent_xonly_hex: str, owner_xonly_hex: str, threshold_sompi: int) -> ScriptBuilder:
    """Build the treasury-vault covenant redeem script (see module docstring)."""
    agent_pk = bytes.fromhex(agent_xonly_hex)
    owner_pk = bytes.fromhex(owner_xonly_hex)
    return (
        ScriptBuilder(covenants_enabled=True)
        .add_op(Opcodes.OpIf)
        # --- AUTO: agent alone, capped single-output payment ---
        .add_op(Opcodes.OpTxOutputCount)
        .add_op(Opcodes.OpTrue)
        .add_op(Opcodes.OpEqualVerify)
        .add_op(Opcodes.OpFalse)              # output index 0
        .add_op(Opcodes.OpTxOutputAmount)     # -> output[0].value
        .add_i64(int(threshold_sompi))        # -> cap
        .add_op(Opcodes.OpLessThanOrEqual)    # value <= cap ?
        .add_op(Opcodes.OpVerify)
        .add_data(agent_pk)
        .add_op(Opcodes.OpCheckSig)
        # --- MANUAL: agent + owner co-sign, any amount ---
        .add_op(Opcodes.OpElse)
        .add_data(agent_pk)
        .add_op(Opcodes.OpCheckSigVerify)
        .add_data(owner_pk)
        .add_op(Opcodes.OpCheckSig)
        .add_op(Opcodes.OpEndIf)
    )


def derive_vault(agent_xonly_hex: str, owner_xonly_hex: str, threshold_sompi: int,
                 network: str = "testnet") -> Vault:
    """Derive the full vault (redeem script + P2SH address) from the two keys + cap."""
    redeem = build_redeem_script(agent_xonly_hex, owner_xonly_hex, threshold_sompi)
    covenant_spk = redeem.create_pay_to_script_hash_script()
    address = address_from_script_public_key(covenant_spk, network)
    return Vault(redeem, covenant_spk, address, agent_xonly_hex, owner_xonly_hex, int(threshold_sompi))


def auto_unlock_script(vault: Vault, agent_sig_hex: str) -> bytes:
    """Unlocking script for the AUTO branch: <agentSig> <OpTrue> <redeem>."""
    prefix = bytes.fromhex(agent_sig_hex) + _OP_TRUE
    return bytes.fromhex(pay_to_script_hash_signature_script(vault.redeem_bytes, prefix))


def manual_unlock_script(vault: Vault, owner_sig_hex: str, agent_sig_hex: str) -> bytes:
    """Unlocking script for the MANUAL branch: <ownerSig> <agentSig> <OpFalse> <redeem>."""
    prefix = bytes.fromhex(owner_sig_hex) + bytes.fromhex(agent_sig_hex) + _OP_FALSE
    return bytes.fromhex(pay_to_script_hash_signature_script(vault.redeem_bytes, prefix))
