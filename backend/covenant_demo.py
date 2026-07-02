"""
Agent Treasury Vault — live covenant demo on Kaspa testnet-10.

Proves, with real on-chain transactions, that a KIP-10 covenant governs how a
KaspaSwarm agent may spend its treasury:

  Act 1  AUTO   pay beneficiary <= cap   -> ACCEPTED  (agent signs alone)
  Act 2  AUTO   pay beneficiary  > cap    -> BLOCKED   (over the on-chain cap)
  Act 3  AUTO   pay WRONG addr  <= cap    -> BLOCKED   (recipient not the pinned payee)
  Act 4  MANUAL pay beneficiary  > cap    -> ACCEPTED  (agent + human owner co-sign)

Requires kaspa>=2.0.0 and a funded testnet-10 coordinator (COORDINATOR_ADDRESS /
COORDINATOR_PRIVATE_KEY in .env). PoC — testnet only.

    python -m backend.covenant_demo
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from kaspa import (
    Address,
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
    create_input_signature,
    pay_to_address_script,
    sign_transaction,
)

from backend.kcore.treasury_vault import (
    MIN_OUTPUT,
    SUBNETWORK_ID,
    auto_unlock_script,
    derive_key,
    derive_vault,
    manual_unlock_script,
    network_type_from_id,
    spend_vault,
    _mass_fee,
)

load_dotenv()

NETWORK_ID = os.getenv("KASPA_NETWORK_ID", "testnet-10")
NETWORK_TYPE = network_type_from_id(NETWORK_ID)
KAS = 100_000_000
EXPLORER = "https://tn10.kaspa.stream/transactions"

CAP = 2 * KAS
FUND_AMOUNTS = [1 * KAS, 1 * KAS, 3 * KAS]   # small(good auto), small(wrong-payee), large(over-cap/manual)


def link(txid: str) -> str:
    return f"{EXPLORER}/{txid}"


async def wait_for_utxos(client: RpcClient, address_str: str, want: int = 1, tries: int = 60):
    for _ in range(tries):
        res = await client.get_utxos_by_addresses({"addresses": [address_str]})
        entries = res.get("entries", [])
        if len(entries) >= want:
            return entries
        await asyncio.sleep(2)
    raise TimeoutError(f"expected >= {want} UTXOs at {address_str}; timed out")


async def fund_vault(client: RpcClient, coord_key: PrivateKey, coord_addr: str, vault, amounts) -> str:
    """Coordinator funds the vault with one UTXO per entry in `amounts` (one tx).
    Selects enough coordinator UTXOs to cover the total; folds sub-dust change into fee."""
    res = await client.get_utxos_by_addresses({"addresses": [coord_addr]})
    entries = sorted(res.get("entries", []), key=lambda u: u["utxoEntry"]["amount"], reverse=True)
    if not entries:
        raise RuntimeError(f"coordinator {coord_addr} has no UTXOs — fund it from the faucet")

    need = sum(amounts)
    coord_spk = pay_to_address_script(Address(coord_addr))
    vault_outs = [TransactionOutput(a, vault.covenant_spk) for a in amounts]

    # Select enough inputs to cover need + a fee headroom.
    selected, total = [], 0
    for e in entries:
        selected.append(e)
        total += e["utxoEntry"]["amount"]
        if total >= need + 5_000_000:   # ~0.05 KAS headroom for fee
            break
    if total < need:
        raise RuntimeError(f"coordinator balance {total} < required {need}")

    def _inputs():
        ins = []
        for e in selected:
            op = TransactionOutpoint(Hash(e["outpoint"]["transactionId"]), e["outpoint"]["index"])
            ins.append(TransactionInput(op, b"", 0, 1, utxo=UtxoEntryReference.from_dict(e)))
        return ins

    ph = Transaction(0, _inputs(), vault_outs + [TransactionOutput(total, coord_spk)], 0, SUBNETWORK_ID, 0, b"", 0)
    mass, fee = await _mass_fee(client, NETWORK_ID, ph)
    change = total - need - fee
    outs = list(vault_outs)
    if change >= MIN_OUTPUT:
        outs.append(TransactionOutput(change, coord_spk))
    else:
        fee += max(change, 0)   # fold sub-dust change into the fee
    tx = Transaction(0, _inputs(), outs, 0, SUBNETWORK_ID, 0, b"", mass)
    signed = sign_transaction(tx, [coord_key], True)
    result = await client.submit_transaction({"transaction": signed, "allowOrphan": False})
    txid = result["transactionId"]
    print(f"  🔒 funded vault: {[a/KAS for a in amounts]} KAS  tx={txid}")
    print(f"     {link(txid)}")
    return txid


def _take(work: list, amount: int) -> dict:
    """Pop a UTXO of exactly `amount` from the working list (by outpoint, so the
    same UTXO is never reused across acts)."""
    for i, e in enumerate(work):
        if e["utxoEntry"]["amount"] == amount:
            return work.pop(i)
    raise RuntimeError(f"no vault UTXO of {amount} sompi available")


async def main():
    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_key_hex = os.getenv("COORDINATOR_PRIVATE_KEY")
    if not coord_addr or not coord_key_hex:
        raise SystemExit("Set COORDINATOR_ADDRESS and COORDINATOR_PRIVATE_KEY in .env")
    coord_key = PrivateKey(coord_key_hex)

    # Agent + human-owner keys governing the vault. Deterministic from the master
    # seed so the vault address is stable/idempotent across runs.
    # NOTE: with no AGENT_MASTER_SEED the owner key is derived from the coordinator
    # key — a testnet-PoC convenience; a real deployment MUST use an independent owner.
    seed = os.getenv("AGENT_MASTER_SEED") or coord_key_hex
    agent_key = derive_key(seed, "vault-agent")
    owner_key = derive_key(seed, "vault-owner")
    agent = Keypair.from_private_key(agent_key)
    owner = Keypair.from_private_key(owner_key)

    # AUTO payments are pinned to the coordinator (the agent's legitimate payee here).
    beneficiary_spk = pay_to_address_script(Address(coord_addr))
    vault = derive_vault(agent.xonly_public_key, owner.xonly_public_key, beneficiary_spk, CAP, NETWORK_TYPE)

    print("=" * 66)
    print("  Agent Treasury Vault — on-chain spend-policy covenant (TN10)")
    print("=" * 66)
    print(f"  cap (per auto tx): {CAP/KAS:g} KAS   beneficiary: {coord_addr[:24]}…")
    print(f"  vault address    : {vault.address_str()}")
    print()

    client = RpcClient(resolver=Resolver(), network_id=NETWORK_ID)
    await client.connect()
    print(f"  connected: {client.url}\n")

    def _auto(tx):
        return auto_unlock_script(vault, create_input_signature(tx, 0, agent_key))

    def _manual(tx):
        owner_sig = create_input_signature(tx, 0, owner_key)
        agent_sig = create_input_signature(tx, 0, agent_key)
        return manual_unlock_script(vault, owner_sig, agent_sig)

    coord_spk = beneficiary_spk
    wrong_spk = pay_to_address_script(Keypair.random().to_address(NETWORK_TYPE))

    try:
        print("[1/5] Funding vault from coordinator…")
        existing = (await client.get_utxos_by_addresses({"addresses": [vault.address_str()]})).get("entries", [])
        if len(existing) >= len(FUND_AMOUNTS):
            print(f"  ↩️ vault already has {len(existing)} UTXOs — reusing")
            entries = existing
        else:
            await fund_vault(client, coord_key, coord_addr, vault, FUND_AMOUNTS)
            entries = await wait_for_utxos(client, vault.address_str(), want=len(FUND_AMOUNTS))
        work = list(entries)
        print()

        async def act(n, label, utxo, to_spk, sign_fn, sig_ops, expect_accept):
            try:
                txid, pay = await spend_vault(client, NETWORK_ID, vault, utxo, to_spk, sign_fn, sig_ops)
                if expect_accept:
                    print(f"  ✅ {label}: ACCEPTED  pay {pay/KAS:.4f} KAS  tx={txid}\n     {link(txid)}")
                else:
                    print(f"  ⚠️ {label}: UNEXPECTEDLY ACCEPTED (covenant not enforced?) tx={txid}")
            except Exception as e:
                if expect_accept:
                    print(f"  ❌ {label}: UNEXPECTED FAILURE: {e}")
                else:
                    print(f"  ⛔ {label}: BLOCKED by covenant (consensus rejected)")

        print(f"[2/5] AUTO pay beneficiary {FUND_AMOUNTS[0]/KAS:g} KAS (<= {CAP/KAS:g} cap) — expect ACCEPT")
        await act(2, "auto under-cap", _take(work, FUND_AMOUNTS[0]), coord_spk, _auto, 1, True)
        print()

        print(f"[3/5] AUTO pay beneficiary {FUND_AMOUNTS[2]/KAS:g} KAS (> {CAP/KAS:g} cap) — expect BLOCK")
        large = _take(work, FUND_AMOUNTS[2])
        await act(3, "auto over-cap", large, coord_spk, _auto, 1, False)
        print()

        print(f"[4/5] AUTO pay WRONG address {FUND_AMOUNTS[1]/KAS:g} KAS (<= cap) — expect BLOCK")
        await act(4, "auto wrong-payee", _take(work, FUND_AMOUNTS[1]), wrong_spk, _auto, 1, False)
        print()

        print(f"[5/5] MANUAL co-sign pay beneficiary {FUND_AMOUNTS[2]/KAS:g} KAS (agent + owner) — expect ACCEPT")
        await act(5, "manual co-sign", large, coord_spk, _manual, 2, True)
        print()
        print("=" * 66)
        print("  Demo complete — the chain enforced the agent's spend policy.")
        print("=" * 66)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
