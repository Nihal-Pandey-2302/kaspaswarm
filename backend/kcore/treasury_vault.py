"""
Agent Treasury Vault — an on-chain spending covenant for KaspaSwarm agents.

An agent's payout wallet is a P2SH UTXO whose redeem script is a KIP-10 covenant
that *governs how the agent may spend*. Kaspa itself enforces the policy:

  • AUTO branch  — the agent signs alone, but the covenant requires the payment to
    be a SINGLE output, to a PINNED beneficiary, whose value is <= `threshold`
    (the per-transaction cap). An autonomous over-cap payment, or a payment to any
    other address, is REJECTED by consensus — not by our code.

  • MANUAL branch — the agent AND a human owner co-sign; any amount, any recipient.
    The "high-risk / unusual spend needs human approval" escape hatch.

Honest scope (PoC, testnet-10 / Toccata):
  - The AUTO branch pins the beneficiary and caps each payment, so an agent that
    only holds the agent key cannot redirect funds or exceed the cap autonomously.
  - It is a *per-transaction* cap, not a rolling/cumulative budget: many under-cap
    payments to the pinned beneficiary are still allowed. A rolling window would
    need covenant state (see IzioDev's threshold_vault_v2) and is future work.
  - AUTO is single-output (no change), so a vault UTXO larger than the cap is only
    spendable via the MANUAL (co-sign) branch — by design: large balances need a human.

Requires the covenant-enabled Kaspa SDK (kaspa>=2.0.0: ScriptBuilder(covenants_enabled),
KIP-10 introspection opcodes).

Redeem script (spent stack shown top-first):
    AUTO   unlock = <agentSig> <OpTrue>
    MANUAL unlock = <ownerSig> <agentSig> <OpFalse>

    OpIf                                       // selector truthy -> AUTO
        OpTxOutputCount OpTrue OpEqualVerify   // exactly 1 output
        OpFalse OpTxOutputAmount <cap> OpLessThanOrEqual OpVerify   // value <= cap
        OpFalse OpTxOutputSpk <beneficiarySpk> OpEqualVerify        // pinned recipient
        <agentPubkey> OpCheckSig               // agent authorises
    OpElse                                     // MANUAL -> agent + owner, any amount
        <agentPubkey> OpCheckSigVerify
        <ownerPubkey> OpCheckSig
    OpEndIf
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from kaspa import (
    Hash,
    Opcodes,
    PrivateKey,
    ScriptBuilder,
    Transaction,
    TransactionInput,
    TransactionOutpoint,
    TransactionOutput,
    UtxoEntryReference,
    address_from_script_public_key,
    calculate_transaction_mass,
    pay_to_script_hash_signature_script,
)

MIN_OUTPUT = 20_000_000          # 0.2 KAS dust floor (matches wallet.py / sdk_transport.py)
FEE_SAFETY = 3                   # over-pay factor; testnet fees are negligible, too-low is rejected
SUBNETWORK_ID = bytes(20)

# Raw opcode bytes for the unlocking-script selector (ScriptBuilder.to_string() is hex).
_OP_TRUE = bytes.fromhex(ScriptBuilder().add_op(Opcodes.OpTrue).to_string())    # push 1  (AUTO)
_OP_FALSE = bytes.fromhex(ScriptBuilder().add_op(Opcodes.OpFalse).to_string())  # push "" (MANUAL)


def network_type_from_id(network_id: str) -> str:
    """'testnet-10' -> 'testnet', 'mainnet' -> 'mainnet'. Address prefixes key off
    the network *type*, so derive it from the id rather than hardcoding (avoids a
    silent testnet-vs-mainnet address mismatch)."""
    return (network_id or "testnet").split("-")[0]


def derive_key(seed: str, label: str) -> PrivateKey:
    """Deterministic secp256k1 key from seed+label (stable vault addresses across
    runs). Retries with a counter on the astronomically rare invalid scalar so an
    arbitrary seed can never crash key derivation."""
    i = 0
    while True:
        material = f"{seed}:{label}" if i == 0 else f"{seed}:{label}:{i}"
        try:
            return PrivateKey(hashlib.sha256(material.encode()).hexdigest())
        except Exception:
            i += 1
            if i > 1000:
                raise


def _spk_bytes(spk) -> bytes:
    """Encode a ScriptPublicKey as OpTxOutputSpk pushes it: 2-byte big-endian
    version || script bytes."""
    return spk.version.to_bytes(2, "big") + bytes(spk)


@dataclass
class Vault:
    """A derived treasury vault: redeem script, P2SH spk, address, and its policy."""
    redeem_script: ScriptBuilder
    covenant_spk: object          # ScriptPublicKey
    address: object               # Address
    agent_xonly: str
    owner_xonly: str
    beneficiary_spk: object       # ScriptPublicKey the AUTO branch pins payments to
    threshold: int                # per-tx auto-spend cap, in sompi

    @property
    def redeem_bytes(self) -> bytes:
        return bytes.fromhex(self.redeem_script.to_string())

    def address_str(self) -> str:
        return self.address.to_string()


def build_redeem_script(agent_xonly_hex: str, owner_xonly_hex: str,
                        beneficiary_spk, threshold_sompi: int) -> ScriptBuilder:
    """Build the treasury-vault covenant redeem script (see module docstring)."""
    agent_pk = bytes.fromhex(agent_xonly_hex)
    owner_pk = bytes.fromhex(owner_xonly_hex)
    beneficiary = _spk_bytes(beneficiary_spk)
    return (
        ScriptBuilder(covenants_enabled=True)
        .add_op(Opcodes.OpIf)
        # --- AUTO: agent alone, single capped payment to the pinned beneficiary ---
        .add_op(Opcodes.OpTxOutputCount)
        .add_op(Opcodes.OpTrue)
        .add_op(Opcodes.OpEqualVerify)
        .add_op(Opcodes.OpFalse)              # output index 0 (empty vector == numeric 0)
        .add_op(Opcodes.OpTxOutputAmount)     # -> output[0].value
        .add_i64(int(threshold_sompi))        # -> cap
        .add_op(Opcodes.OpLessThanOrEqual)    # value <= cap ?
        .add_op(Opcodes.OpVerify)
        .add_op(Opcodes.OpFalse)              # output index 0
        .add_op(Opcodes.OpTxOutputSpk)        # -> output[0].scriptPublicKey
        .add_data(beneficiary)                # -> pinned beneficiary spk
        .add_op(Opcodes.OpEqualVerify)        # require output[0] pays the beneficiary
        .add_data(agent_pk)
        .add_op(Opcodes.OpCheckSig)
        # --- MANUAL: agent + owner co-sign, any amount / recipient ---
        .add_op(Opcodes.OpElse)
        .add_data(agent_pk)
        .add_op(Opcodes.OpCheckSigVerify)     # agent sig (consumed) — must be top of stack
        .add_data(owner_pk)
        .add_op(Opcodes.OpCheckSig)           # owner sig
        .add_op(Opcodes.OpEndIf)
    )


def derive_vault(agent_xonly_hex: str, owner_xonly_hex: str, beneficiary_spk,
                 threshold_sompi: int, network_type: str = "testnet") -> Vault:
    """Derive the full vault (redeem script + P2SH address) from keys, beneficiary, cap."""
    redeem = build_redeem_script(agent_xonly_hex, owner_xonly_hex, beneficiary_spk, threshold_sompi)
    covenant_spk = redeem.create_pay_to_script_hash_script()
    address = address_from_script_public_key(covenant_spk, network_type)
    return Vault(redeem, covenant_spk, address, agent_xonly_hex, owner_xonly_hex,
                 beneficiary_spk, int(threshold_sompi))


def auto_unlock_script(vault: Vault, agent_sig_hex: str) -> bytes:
    """AUTO branch unlock: <agentSig> <OpTrue> <redeem>."""
    prefix = bytes.fromhex(agent_sig_hex) + _OP_TRUE
    return bytes.fromhex(pay_to_script_hash_signature_script(vault.redeem_bytes, prefix))


def manual_unlock_script(vault: Vault, owner_sig_hex: str, agent_sig_hex: str) -> bytes:
    """MANUAL branch unlock: <ownerSig> <agentSig> <OpFalse> <redeem>.

    NOTE (coupled to build_redeem_script MANUAL branch): the agent sig must end up
    on top so OpCheckSigVerify(agent) runs first; hence agentSig is pushed last
    before the selector. Keep this order in sync with the redeem script.
    """
    prefix = bytes.fromhex(owner_sig_hex) + bytes.fromhex(agent_sig_hex) + _OP_FALSE
    return bytes.fromhex(pay_to_script_hash_signature_script(vault.redeem_bytes, prefix))


# --------------------------------------------------------------------------- #
# Live spend plumbing (reusable — shared by covenant_demo and CovenantEscrow)  #
# --------------------------------------------------------------------------- #

def _cov_utxo_ref(vault: Vault, utxo: dict) -> UtxoEntryReference:
    return UtxoEntryReference.from_dict({
        "address": vault.address_str(),
        "outpoint": {"transactionId": utxo["outpoint"]["transactionId"], "index": utxo["outpoint"]["index"]},
        "utxoEntry": {
            "amount": utxo["utxoEntry"]["amount"],
            "scriptPublicKey": {"version": vault.covenant_spk.version, "script": vault.covenant_spk.script},
            "blockDaaScore": 0, "isCoinbase": False, "covenantId": None,
        },
    })


async def _mass_fee(client, network_id: str, tx: Transaction) -> tuple[int, int]:
    mass = calculate_transaction_mass(network_id, tx)
    rates = await client.get_fee_estimate()
    rate = max(float(rates["estimate"]["priorityBucket"]["feerate"]), 1.0)
    return mass, int(mass * rate * FEE_SAFETY) + 2000


async def spend_vault(client, network_id: str, vault: Vault, utxo: dict, to_spk,
                      sign_fn, sig_op_count: int) -> tuple[str, int]:
    """Spend a single vault UTXO to `to_spk`. `sign_fn(tx)->unlock_script_bytes`
    (use auto_unlock_script / manual_unlock_script). Returns (txid, pay_amount).

    Mass is computed on a tx that INCLUDES the real unlock script; the output is
    then re-signed for the fee-adjusted amount (unlock size is constant, so mass
    stays valid). Raises ValueError if the post-fee payout would be dust.
    """
    amount = utxo["utxoEntry"]["amount"]
    outpoint = TransactionOutpoint(Hash(utxo["outpoint"]["transactionId"]), utxo["outpoint"]["index"])
    cov_ref = _cov_utxo_ref(vault, utxo)

    prov = Transaction(0, [TransactionInput(outpoint, b"", 0, sig_op_count, utxo=cov_ref)],
                       [TransactionOutput(amount, to_spk)], 0, SUBNETWORK_ID, 0, b"", 0)
    prov_unlock = sign_fn(prov)
    mass_tx = Transaction(0, [TransactionInput(outpoint, prov_unlock, 0, sig_op_count, utxo=cov_ref)],
                          [TransactionOutput(amount, to_spk)], 0, SUBNETWORK_ID, 0, b"", 0)
    mass, fee = await _mass_fee(client, network_id, mass_tx)

    pay_amount = amount - fee
    if pay_amount < MIN_OUTPUT:
        raise ValueError(f"payout {pay_amount} below dust floor after fee {fee} (utxo {amount})")

    out = TransactionOutput(pay_amount, to_spk)
    final_unsigned = Transaction(0, [TransactionInput(outpoint, b"", 0, sig_op_count, utxo=cov_ref)],
                                 [out], 0, SUBNETWORK_ID, 0, b"", mass)
    unlock = sign_fn(final_unsigned)
    tx = Transaction(0, [TransactionInput(outpoint, unlock, 0, sig_op_count, utxo=cov_ref)],
                     [out], 0, SUBNETWORK_ID, 0, b"", mass)
    res = await client.submit_transaction({"transaction": tx, "allowOrphan": False})
    return res["transactionId"], pay_amount
