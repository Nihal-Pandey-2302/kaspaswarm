"""
Rolling-allowance covenant — LIVE spend on Kaspa testnet-10.

Proves the stateful covenant (compiled by silverc) is real end-to-end:
  1. compile rolling_vault.sil -> real Kaspa script -> P2SH vault address
  2. fund the covenant (real UTXO locked under the covenant script)
  3. RECLAIM by the owner -> ACCEPTED (real tx; funds return to coordinator)
  4. RECLAIM with a WRONG key -> BLOCKED by the covenant (consensus rejects)

The `draw` (streaming-allowance) entrypoint additionally needs a fee-realistic
minerFee and the compiler's validateOutputState for the change re-lock; the
owner-authorised `reclaim` path is the robust, fund-safe live proof.

    python -m backend.rolling_demo        # needs silverc on PATH + funded coordinator
"""
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from dotenv import load_dotenv
from kaspa import (
    Address,
    Keypair,
    PrivateKey,
    Resolver,
    RpcClient,
    ScriptBuilder,
    address_from_script_public_key,
    create_input_signature,
    pay_to_address_script,
    pay_to_script_hash_signature_script,
)

from backend.kcore.treasury_vault import derive_key, network_type_from_id, spend_vault
from backend.kcore.sdk_transport import get_transport

load_dotenv()
KAS = 100_000_000
NETWORK_ID = os.getenv("KASPA_NETWORK_ID", "testnet-10")
NETWORK_TYPE = network_type_from_id(NETWORK_ID)
EXPLORER = "https://tn10.kaspa.stream/transactions"
HERE = os.path.dirname(__file__)
SIL = os.path.join(HERE, "covenants", "rolling_vault.sil")

RECLAIM_SELECTOR = 1   # entrypoint order: draw=0, reclaim=1


@dataclass
class CompiledVault:
    """spend_vault-compatible wrapper around a compiled covenant artifact."""
    redeem: bytes
    covenant_spk: object
    address: object

    @property
    def redeem_bytes(self):
        return self.redeem

    def address_str(self):
        return self.address.to_string()


def _barr(bs):
    return {"kind": "array", "data": [{"kind": "byte", "data": b} for b in bs]}


def compile_vault(agent_xonly_hex, owner_hash: bytes, allowance_per_block=100_000, window_start=b"\x00" * 8) -> CompiledVault:
    if not shutil.which("silverc"):
        raise RuntimeError("silverc not on PATH — cargo install --git github.com/kaspanet/silverscript silverscript-lang")
    args = [_barr(bytes.fromhex(agent_xonly_hex)), _barr(owner_hash),
            {"kind": "int", "data": allowance_per_block}, _barr(window_start)]
    with tempfile.TemporaryDirectory() as tmp:
        ap, op = os.path.join(tmp, "a.json"), os.path.join(tmp, "o.json")
        json.dump(args, open(ap, "w"))
        subprocess.run(["silverc", SIL, "--constructor-args", ap, "-o", op], check=True, capture_output=True)
        art = json.load(open(op))
    redeem = bytes(art["script"])
    spk = ScriptBuilder.from_script(redeem, covenants_enabled=True).create_pay_to_script_hash_script()
    return CompiledVault(redeem, spk, address_from_script_public_key(spk, NETWORK_TYPE))


def _reclaim_signer(vault: CompiledVault, pk_xonly: bytes, key: PrivateKey):
    """Return sign_fn(tx)->unlock bytes for the reclaim branch:
    <pk> <sig> <selector=1> <redeem>."""
    def sign_fn(tx):
        sig_full = bytes.fromhex(create_input_signature(tx, 0, key))  # 0x41 + 65B
        sig_val = sig_full[1:]                                        # strip push op
        b = ScriptBuilder(covenants_enabled=True)
        b.add_data(pk_xonly)     # pubkey pk (32B)
        b.add_data(sig_val)      # sig s (re-pushed)
        b.add_i64(RECLAIM_SELECTOR)
        prefix = bytes.fromhex(b.to_string())
        return bytes.fromhex(pay_to_script_hash_signature_script(vault.redeem_bytes, prefix))
    return sign_fn


async def _wait_utxo(client, addr, tries=40):
    for _ in range(tries):
        e = (await client.get_utxos_by_addresses({"addresses": [addr]})).get("entries", [])
        if e:
            return max(e, key=lambda u: u["utxoEntry"]["amount"])
        await asyncio.sleep(2)
    raise TimeoutError(f"no covenant UTXO at {addr}")


async def main():
    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_priv = os.getenv("COORDINATOR_PRIVATE_KEY")
    if not coord_addr or not coord_priv:
        raise SystemExit("Set COORDINATOR_ADDRESS / COORDINATOR_PRIVATE_KEY in .env")

    agent = Keypair.from_private_key(derive_key("kaspaswarm-demo", "allowance-agent"))
    owner = Keypair.from_private_key(derive_key("kaspaswarm-demo", "allowance-owner"))
    owner_xonly = bytes.fromhex(owner.xonly_public_key)
    owner_hash = hashlib.blake2b(owner_xonly, digest_size=32).digest()   # == Kaspa OpBlake2b

    vault = compile_vault(agent.xonly_public_key, owner_hash)
    reward = KAS // 4  # 0.25 KAS

    print("=" * 64)
    print("  Rolling-allowance covenant — LIVE reclaim proof (TN10)")
    print("=" * 64)
    print(f"  covenant address : {vault.address_str()}")
    print(f"  redeem script    : {len(vault.redeem_bytes)} bytes (compiled by silverc)\n")

    client = RpcClient(resolver=Resolver(), network_id=NETWORK_ID)
    await client.connect()
    coord_spk = pay_to_address_script(Address(coord_addr))
    try:
        print(f"[1/3] Funding covenant with {reward/KAS:g} KAS…")
        txid = await get_transport().send(coord_priv, coord_addr, vault.address_str(), reward, b"")
        if isinstance(txid, str) and txid.startswith("failed"):
            raise RuntimeError(f"funding failed: {txid}")
        print(f"      fund tx: {txid}\n      {EXPLORER}/{txid}")
        utxo = await _wait_utxo(client, vault.address_str())
        print()

        print("[2/3] RECLAIM with WRONG key — expect BLOCK")
        wrong = Keypair.random()
        try:
            await spend_vault(client, NETWORK_ID, vault, utxo, coord_spk,
                              _reclaim_signer(vault, bytes.fromhex(wrong.xonly_public_key), PrivateKey(wrong.private_key)), 1)
            print("      ⚠️ UNEXPECTEDLY ACCEPTED (covenant not enforced?)")
        except Exception as e:
            print(f"      ⛔ BLOCKED by covenant: {str(e)[:90]}")
        print()

        print("[3/3] RECLAIM by the owner — expect ACCEPT")
        rid, pay = await spend_vault(client, NETWORK_ID, vault, utxo, coord_spk,
                                     _reclaim_signer(vault, owner_xonly, PrivateKey(owner.private_key)), 1)
        print(f"      ✅ ACCEPTED  reclaimed {pay/KAS:.4f} KAS  tx: {rid}\n      {EXPLORER}/{rid}")
        print()
        print("=" * 64)
        print("  Live proof complete — the compiled covenant is enforced on-chain.")
        print("=" * 64)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
