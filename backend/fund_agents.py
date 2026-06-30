"""
Fund (or inspect) the swarm's agent addresses for LIVE mode.

In live mode the coordinator uses your funded env address, and every other agent
derives a STABLE address from AGENT_MASTER_SEED + agent_id (see wallet.create_address).
This script computes those addresses and sends each solver some test KAS from the
coordinator so they can broadcast their own on-chain bids/solutions.

Usage (run from the project root, with .env populated):
    python backend/fund_agents.py check          # list addresses + balances, send nothing
    python backend/fund_agents.py fund [KAS]     # send KAS (default 25) to each solver

Required env: COORDINATOR_ADDRESS, COORDINATOR_PRIVATE_KEY, AGENT_MASTER_SEED,
              NUM_SOLVERS (optional, default 8), KASPA_WS_URL (optional).
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from backend.kcore.wallet import KaspaWallet, KaspaAddress  # noqa: E402
from backend.kcore.schnorr import get_public_key  # noqa: E402
from backend.bech32_util import encode_address  # noqa: E402

SOMPI = 100_000_000


def solver_addresses(master_seed: str, num_solvers: int):
    out = []
    for i in range(num_solvers):
        agent_id = f"solver_{i}"
        priv = KaspaWallet.derive_private_key(master_seed, agent_id)
        pub = get_public_key(bytes.fromhex(priv))
        addr = encode_address("kaspatest", "pk", pub)
        out.append((agent_id, addr, priv))
    return out


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    amount_kas = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0

    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_key = os.getenv("COORDINATOR_PRIVATE_KEY")
    seed = os.getenv("AGENT_MASTER_SEED")
    num_solvers = int(os.getenv("NUM_SOLVERS", "8"))

    if not (coord_addr and coord_key):
        sys.exit("Set COORDINATOR_ADDRESS and COORDINATOR_PRIVATE_KEY in .env")
    if not seed:
        sys.exit("Set AGENT_MASTER_SEED in .env (any stable secret string)")

    wallet = KaspaWallet(mock_mode=False)
    solvers = solver_addresses(seed, num_solvers)

    coord_bal = await wallet.get_balance(coord_addr)
    print(f"\nCoordinator {coord_addr}\n  balance: {coord_bal/SOMPI:.4f} KAS\n")
    print(f"{num_solvers} solver addresses:")
    for agent_id, addr, _ in solvers:
        bal = await wallet.get_balance(addr)
        print(f"  {agent_id:<10} {addr}  ({bal/SOMPI:.4f} KAS)")

    if mode != "fund":
        print("\n(check mode — nothing sent. Run 'fund [KAS]' to distribute.)")
        return

    coord = KaspaAddress(
        address=coord_addr, private_key=coord_key,
        public_key=get_public_key(bytes.fromhex(coord_key)).hex(), balance=coord_bal,
    )
    amount = int(amount_kas * SOMPI)
    print(f"\nSending {amount_kas} KAS to each of {num_solvers} solvers...\n")

    for agent_id, addr, _ in solvers:
        # Wait until the coordinator has a spendable UTXO (the previous send's
        # change must mature before the next send).
        tx_id = None
        for attempt in range(20):
            tx_id = await wallet.send_transaction(from_addr=coord, to_addr=addr, amount=amount)
            if isinstance(tx_id, str) and not tx_id.startswith("failed"):
                break
            print(f"  {agent_id}: waiting for spendable UTXO ({tx_id}, retry {attempt+1})...")
            await asyncio.sleep(3)
        if isinstance(tx_id, str) and not tx_id.startswith("failed"):
            print(f"  ✅ {agent_id} <- {amount_kas} KAS   tx={tx_id}")
        else:
            print(f"  ❌ {agent_id} FAILED: {tx_id}")
        await asyncio.sleep(3)  # let the change UTXO settle before the next send

    print("\nDone. Re-run 'check' to confirm balances.")


if __name__ == "__main__":
    asyncio.run(main())
