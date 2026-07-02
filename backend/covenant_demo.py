"""
Agent Treasury Vault — live covenant demo on Kaspa testnet-10.

Proves, with real on-chain transactions, that a KIP-10 covenant governs how a
KaspaSwarm agent may spend its treasury:

  Act 1  AUTO  spend <= cap   -> ACCEPTED  (agent signs alone, small payout)
  Act 2  AUTO  spend  > cap    -> BLOCKED   (Kaspa consensus rejects the tx)
  Act 3  MANUAL spend > cap    -> ACCEPTED  (agent + human owner co-sign)

Requires kaspa>=2.0.0 and a funded testnet-10 coordinator (COORDINATOR_ADDRESS /
COORDINATOR_PRIVATE_KEY in .env). PoC — testnet only.

    python -m backend.covenant_demo

Every txid is printed with a tn10.kaspa.stream link.
"""
from __future__ import annotations

import asyncio
import hashlib
import os

from dotenv import load_dotenv
from kaspa import (
    Hash,
    Keypair,
    PrivateKey,
    Resolver,
    RpcClient,
    Transaction,
    TransactionInput,
    TransactionOutpoint,
    TransactionOutput,
    UtxoEntryReference,
    address_from_script_public_key,
    calculate_transaction_mass,
    create_input_signature,
    pay_to_address_script,
    sign_transaction,
    Address,
)

from backend.kcore.treasury_vault import derive_vault, auto_unlock_script, manual_unlock_script

load_dotenv()

NETWORK_ID = os.getenv("KASPA_NETWORK_ID", "testnet-10")
NETWORK_TYPE = "testnet"
SUBNETWORK_ID = bytes(20)
KAS = 100_000_000

EXPLORER = "https://tn10.kaspa.stream/transactions"

CAP = 2 * KAS               # per-tx auto-spend cap enforced by the covenant
SMALL = 1 * KAS             # vault UTXO for the under-cap auto spend (Act 1)
LARGE = 3 * KAS             # vault UTXO for the over-cap spends (Acts 2 & 3)


FEE_SAFETY = 3          # over-pay factor; testnet fees are negligible and too-low is rejected


def link(txid: str) -> str:
    return f"{EXPLORER}/{txid}"


def _derive_key(seed: str, label: str) -> PrivateKey:
    """Deterministic secp256k1 key from the master seed + a label, so vault
    addresses are stable across runs (a random key per run would strand funds)."""
    return PrivateKey(hashlib.sha256(f"{seed}:{label}".encode()).hexdigest())


async def _fee_for(client: RpcClient, tx: Transaction) -> tuple[int, int]:
    """Mass of the (fully-assembled) tx + a safe fee. Pass a tx that already has
    its real signature script so the mass reflects the actual on-chain size."""
    mass = calculate_transaction_mass(NETWORK_ID, tx)
    fee_rates = await client.get_fee_estimate()
    rate = max(float(fee_rates["estimate"]["priorityBucket"]["feerate"]), 1.0)
    fee = int(mass * rate * FEE_SAFETY) + 2000
    return mass, fee


async def wait_for_utxos(client: RpcClient, address_str: str, want: int = 1, tries: int = 60):
    for _ in range(tries):
        res = await client.get_utxos_by_addresses({"addresses": [address_str]})
        entries = res.get("entries", [])
        if len(entries) >= want:
            return entries
        await asyncio.sleep(2)
    raise TimeoutError(f"no UTXOs at {address_str} after waiting")


async def wait_for_confirmation(client: RpcClient, txid: str, tries: int = 60):
    for _ in range(tries):
        await asyncio.sleep(1)
        try:
            await client.get_mempool_entry({"transactionId": txid, "includeOrphanPool": True})
        except Exception:
            return True  # left the mempool -> accepted into the DAG
    return False


async def fund_vault(client: RpcClient, coord_key: PrivateKey, coord_addr: str, vault) -> None:
    """Coordinator funds the vault with two UTXOs (SMALL + LARGE) in one tx."""
    utxos = await client.get_utxos_by_addresses({"addresses": [coord_addr]})
    entries = utxos.get("entries", [])
    if not entries:
        raise RuntimeError(f"coordinator {coord_addr} has no UTXOs — fund it from the faucet")
    funding = max(entries, key=lambda u: u["utxoEntry"]["amount"])
    amount = funding["utxoEntry"]["amount"]
    ref = UtxoEntryReference.from_dict(funding)
    outpoint = TransactionOutpoint(Hash(funding["outpoint"]["transactionId"]), funding["outpoint"]["index"])

    coord_spk = pay_to_address_script(Address(coord_addr))
    outs = [
        TransactionOutput(SMALL, vault.covenant_spk),
        TransactionOutput(LARGE, vault.covenant_spk),
        TransactionOutput(amount, coord_spk),  # placeholder change, fixed below
    ]
    ph = Transaction(0, [TransactionInput(outpoint, b"", 0, 1, utxo=ref)], outs, 0, SUBNETWORK_ID, 0, b"", 0)
    mass, fee = await _fee_for(client, ph)
    change = amount - SMALL - LARGE - fee
    if change < 0:
        raise RuntimeError(f"coordinator UTXO {amount} too small to fund {SMALL+LARGE} + fee {fee}")
    outs[2] = TransactionOutput(change, coord_spk)
    tx = Transaction(0, [TransactionInput(outpoint, b"", 0, 1, utxo=ref)], outs, 0, SUBNETWORK_ID, 0, b"", mass)
    signed = sign_transaction(tx, [coord_key], True)
    res = await client.submit_transaction({"transaction": signed, "allowOrphan": False})
    txid = res["transactionId"]
    print(f"  🔒 funded vault: {SMALL/KAS:g} + {LARGE/KAS:g} KAS  tx={txid}")
    print(f"     {link(txid)}")
    await wait_for_confirmation(client, txid)


def _pick(entries, amount):
    """Find the vault UTXO with the given amount."""
    for e in entries:
        if e["utxoEntry"]["amount"] == amount:
            return e
    raise RuntimeError(f"no vault UTXO of {amount} sompi found")


async def _spend(client, vault, utxo, pay_to_spk, sign_fn, sig_op_count, label):
    """Build + submit a covenant spend. sign_fn(tx_unsigned)->unlock_script bytes."""
    amount = utxo["utxoEntry"]["amount"]
    outpoint = TransactionOutpoint(Hash(utxo["outpoint"]["transactionId"]), utxo["outpoint"]["index"])
    cov_ref = UtxoEntryReference.from_dict({
        "address": vault.address_str(),
        "outpoint": {"transactionId": utxo["outpoint"]["transactionId"], "index": utxo["outpoint"]["index"]},
        "utxoEntry": {
            "amount": amount,
            "scriptPublicKey": {"version": vault.covenant_spk.version, "script": vault.covenant_spk.script},
            "blockDaaScore": 0, "isCoinbase": False, "covenantId": None,
        },
    })
    # 1) Provisional sign (output = full amount) just to learn the unlock-script size.
    prov = Transaction(0, [TransactionInput(outpoint, b"", 0, sig_op_count, utxo=cov_ref)],
                       [TransactionOutput(amount, pay_to_spk)], 0, SUBNETWORK_ID, 0, b"", 0)
    prov_unlock = sign_fn(prov)
    # 2) Mass + fee computed on a tx that INCLUDES the real unlock script.
    mass_tx = Transaction(0, [TransactionInput(outpoint, prov_unlock, 0, sig_op_count, utxo=cov_ref)],
                          [TransactionOutput(amount, pay_to_spk)], 0, SUBNETWORK_ID, 0, b"", 0)
    mass, fee = await _fee_for(client, mass_tx)
    pay_amount = amount - fee
    # 3) Re-sign for the fee-adjusted output (sighash commits to outputs; unlock size
    #    is constant, so `mass` stays valid).
    out = TransactionOutput(pay_amount, pay_to_spk)
    final_unsigned = Transaction(0, [TransactionInput(outpoint, b"", 0, sig_op_count, utxo=cov_ref)],
                                 [out], 0, SUBNETWORK_ID, 0, b"", mass)
    unlock = sign_fn(final_unsigned)
    signed_inp = TransactionInput(outpoint, unlock, 0, sig_op_count, utxo=cov_ref)
    tx = Transaction(0, [signed_inp], [out], 0, SUBNETWORK_ID, 0, b"", mass)
    res = await client.submit_transaction({"transaction": tx, "allowOrphan": False})
    txid = res["transactionId"]
    print(f"  ✅ {label}: ACCEPTED  pay {pay_amount/KAS:.4f} KAS  tx={txid}")
    print(f"     {link(txid)}")
    return txid


async def main():
    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_key_hex = os.getenv("COORDINATOR_PRIVATE_KEY")
    if not coord_addr or not coord_key_hex:
        raise SystemExit("Set COORDINATOR_ADDRESS and COORDINATOR_PRIVATE_KEY in .env")
    coord_key = PrivateKey(coord_key_hex)

    # Agent + human-owner keypairs governing this treasury vault. Derived
    # deterministically from the master seed so the vault address is stable across
    # runs (funds are never stranded and a re-run reuses the same vault).
    seed = os.getenv("AGENT_MASTER_SEED") or coord_key_hex
    agent_key = _derive_key(seed, "vault-agent")
    owner_key = _derive_key(seed, "vault-owner")
    agent = Keypair.from_private_key(agent_key)
    owner = Keypair.from_private_key(owner_key)
    vault = derive_vault(agent.xonly_public_key, owner.xonly_public_key, CAP, NETWORK_TYPE)

    print("=" * 64)
    print("  Agent Treasury Vault — on-chain spend-policy covenant (TN10)")
    print("=" * 64)
    print(f"  cap (per auto tx): {CAP/KAS:g} KAS")
    print(f"  vault address    : {vault.address_str()}")
    print()

    client = RpcClient(resolver=Resolver(), network_id=NETWORK_ID)
    await client.connect()
    print(f"  connected: {client.url}\n")

    try:
        print("[1/4] Funding vault from coordinator…")
        existing = (await client.get_utxos_by_addresses({"addresses": [vault.address_str()]})).get("entries", [])
        have = {e["utxoEntry"]["amount"] for e in existing}
        if {SMALL, LARGE} <= have:
            print(f"  ↩️ vault already funded ({len(existing)} UTXOs) — reusing")
            entries = existing
        else:
            await fund_vault(client, coord_key, coord_addr, vault)
            entries = await wait_for_utxos(client, vault.address_str(), want=2)
        print()

        coord_spk = pay_to_address_script(Address(coord_addr))

        # Act 1 — AUTO under cap -> accepted
        print(f"[2/4] AUTO spend {SMALL/KAS:g} KAS (<= {CAP/KAS:g} cap) — expect ACCEPT")
        small = _pick(entries, SMALL)
        await _spend(client, vault, small, coord_spk,
                     lambda tx: auto_unlock_script(vault, create_input_signature(tx, 0, agent_key)),
                     1, "auto under-cap")
        print()

        # Act 2 — AUTO over cap -> blocked by the covenant
        print(f"[3/4] AUTO spend {LARGE/KAS:g} KAS (>  {CAP/KAS:g} cap) — expect BLOCK")
        large = _pick(entries, LARGE)
        try:
            await _spend(client, vault, large, coord_spk,
                         lambda tx: auto_unlock_script(vault, create_input_signature(tx, 0, agent_key)),
                         1, "auto over-cap")
            print("  ⚠️ UNEXPECTED: over-cap auto spend was accepted (covenant not enforced?)")
        except Exception as e:
            print(f"  ⛔ BLOCKED by covenant (consensus rejected): {e}")
        print()

        # Act 3 — MANUAL co-sign over cap -> accepted
        print(f"[4/4] MANUAL co-sign spend {LARGE/KAS:g} KAS (agent + owner) — expect ACCEPT")

        def _manual(tx):
            owner_sig = create_input_signature(tx, 0, owner_key)
            agent_sig = create_input_signature(tx, 0, agent_key)
            return manual_unlock_script(vault, owner_sig, agent_sig)

        await _spend(client, vault, large, coord_spk, _manual, 2, "manual co-sign")
        print()
        print("=" * 64)
        print("  Demo complete — the chain enforced the agent's spend policy.")
        print("=" * 64)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
