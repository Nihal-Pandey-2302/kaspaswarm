"""
CovenantEscrow live validation on testnet-10.

Proves the per-task escrow covenant end to end:
  1. lock  -> coordinator funds a covenant UTXO with the reward
  2. release -> settle branch pays the pinned SOLVER (real tx)
  3. lock + cancel -> refund branch returns funds to the COORDINATOR (real tx)

    python -m backend.escrow_demo
"""
import asyncio
import os

from dotenv import load_dotenv
from kaspa import Keypair

from backend.kcore.covenant import CovenantEscrow

load_dotenv()
KAS = 100_000_000
EXPLORER = "https://tn10.kaspa.stream/transactions"


async def main():
    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_priv = os.getenv("COORDINATOR_PRIVATE_KEY")
    if not coord_addr or not coord_priv:
        raise SystemExit("Set COORDINATOR_ADDRESS / COORDINATOR_PRIVATE_KEY in .env")

    solver = Keypair.random().to_address("testnet").to_string()
    reward = KAS // 2  # 0.5 KAS

    esc = CovenantEscrow("testnet-10")
    print("=" * 62)
    print("  CovenantEscrow — live per-task escrow covenant (TN10)")
    print("=" * 62)
    print(f"  coordinator: {coord_addr[:26]}…")
    print(f"  solver     : {solver[:26]}…")
    print(f"  reward     : {reward/KAS:g} KAS\n")

    # ---- Task A: lock -> release (settle to solver) ----
    print("[A] lock reward into covenant, then RELEASE to solver…")
    await esc.lock(101, coord_addr, solver, reward, reward // 2, coord_priv)
    ok = await esc.release(101)
    print(f"    release ok: {ok}\n")

    # ---- Task B: lock -> cancel (refund to coordinator) ----
    print("[B] lock reward into covenant, then CANCEL (refund to coordinator)…")
    await esc.lock(102, coord_addr, solver, reward, reward // 2, coord_priv)
    ok2 = await esc.cancel(102)
    print(f"    refund ok: {ok2}\n")

    print("  escrow stats:", esc.stats())
    print("=" * 62)
    if esc._client:
        await esc._client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
