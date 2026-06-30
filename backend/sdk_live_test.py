"""
SDK live test — prove REAL on-chain coordination via the official Kaspa Python
SDK + Resolver (community node, no node IP) on testnet-10.

Self-contained: imports ONLY the `kaspa` SDK (the local backend/kcore package no longer
shadows it if backend/ is on sys.path, so we avoid importing anything from it).

Run from the project root with a funded coordinator in .env:
    python backend/sdk_live_test.py
Env: COORDINATOR_ADDRESS, COORDINATOR_PRIVATE_KEY, KASPA_NETWORK_ID (default testnet-10).
"""
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

from kaspa import Resolver, RpcClient, PrivateKey, PaymentOutput, create_transactions, Address

NETWORK = os.getenv("KASPA_NETWORK_ID", "testnet-10")
TIMEOUT_S = 40
MAGIC = b"KSWARM1:"


def encode_payload(body: dict) -> bytes:
    return MAGIC + json.dumps(body, separators=(",", ":")).encode("utf-8")


def _extract_block(event):
    e = event
    if isinstance(e, dict):
        data = e.get("data") or e.get("Data") or e
        if isinstance(data, dict):
            return data.get("block") or data.get("Block")
    return getattr(getattr(e, "data", None), "block", None)


async def main():
    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_key = os.getenv("COORDINATOR_PRIVATE_KEY")
    if not (coord_addr and coord_key):
        sys.exit("Set COORDINATOR_ADDRESS and COORDINATOR_PRIVATE_KEY in .env")

    print(f"🔌 Connecting to {NETWORK} via Resolver…")
    rpc = RpcClient(resolver=Resolver(), network_id=NETWORK)
    await rpc.connect()
    print(f"   connected={rpc.is_connected}  url={rpc.url}")

    bal = await rpc.get_balance_by_address({"address": coord_addr})
    print(f"💰 balance: {bal}")

    marker = int(time.time())
    payload = encode_payload({"t": 1, "s": coord_addr, "id": marker % 1_000_000,
                              "d": {"live_test": marker}, "ts": marker})

    seen = {"hit": False, "blocks": 0, "logged": False}

    def on_block(event, *_):
        block = _extract_block(event)
        if block is None:
            if not seen["logged"]:
                seen["logged"] = True
                print(f"   (debug) event shape: type={type(event).__name__} "
                      f"{list(event.keys()) if isinstance(event, dict) else ''}")
            return
        seen["blocks"] += 1
        txs = block.get("transactions") if isinstance(block, dict) else getattr(block, "transactions", [])
        for tx in (txs or []):
            phex = (tx.get("payload") if isinstance(tx, dict) else getattr(tx, "payload", "")) or ""
            try:
                pb = bytes.fromhex(phex)
            except Exception:
                continue
            if pb.startswith(MAGIC):
                body = json.loads(pb[len(MAGIC):].decode("utf-8"))
                if body.get("d", {}).get("live_test") == marker:
                    print(f"👁️  decoded OUR message from a real block: {body['d']}")
                    seen["hit"] = True

    try:
        rpc.add_event_listener("all", on_block)   # 'BlockAdded' events arrive here
        await rpc.subscribe_block_added()
        print("👁️  subscribed to block-added")
    except Exception as e:
        print(f"⚠️ subscribe failed: {e}")

    await asyncio.sleep(2)

    print("📤 building + signing + submitting a real payload tx (0.2 KAS self-send)…")
    utxos_resp = await rpc.get_utxos_by_addresses({"addresses": [coord_addr]})
    entries = utxos_resp["entries"] if isinstance(utxos_resp, dict) else utxos_resp
    print(f"   utxos: {len(entries)}")
    pk = PrivateKey(coord_key)
    # create_transactions (plural) is the change-aware builder: it selects UTXOs,
    # adds a change output, and computes the fee. (The singular create_transaction
    # does NOT add change — using it would burn the balance as fee.)
    built = create_transactions(
        network_id=NETWORK,
        entries=entries,
        change_address=Address(coord_addr),
        outputs=[PaymentOutput(Address(coord_addr), 20_000_000)],
        payload=payload,
        priority_fee=2_000_000,  # 0.02 KAS — covers the payload's compute-mass min fee
    )
    pending = built["transactions"][0]

    # SAFETY: never submit with an absurd fee.
    fee = pending.fee_amount
    print(f"   fee={fee} change={pending.change_amount} payment={pending.payment_amount}")
    if fee is None or fee > 100_000_000:  # > 1 KAS fee = something is wrong
        print("   ❌ ABORT: fee unexpectedly high — not submitting.")
        await rpc.disconnect()
        sys.exit(1)

    pending.sign([pk])
    txid = await pending.submit(rpc)
    print(f"   ✅ submitted txid={txid}")
    print(f"   🔗 https://explorer-tn10.kaspa.org/txs/{txid}")

    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        if seen["hit"]:
            print(f"\n✅ PASS — real on-chain round-trip via Resolver (blocks seen={seen['blocks']})")
            await rpc.disconnect()
            return
        await asyncio.sleep(1)
    print(f"\n❌ FAIL — not seen in a block within {TIMEOUT_S}s (blocks={seen['blocks']})")
    await rpc.disconnect()
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
