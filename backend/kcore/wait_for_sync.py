"""Wait for kaspad to sync, then test balance and a real transaction."""
import asyncio, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))  # project root

# Credentials come from the environment (.env), never hardcoded. See .env.example.
from backend.kcore.wrpc_client import KaspaRpcClient

ADDR = os.environ.get('COORDINATOR_ADDRESS')
if not ADDR:
    sys.exit("COORDINATOR_ADDRESS not set — add it to your .env (see .env.example)")

async def wait_for_sync():
    c = KaspaRpcClient('ws://127.0.0.1:18210')
    if not await c.connect():
        print("Cannot connect"); return False
    
    print("Waiting for node to sync...")
    while True:
        info = await c.get_server_info()
        synced = info.get("isSynced", False)
        daa = info.get("virtualDaaScore", 0)
        print(f"  isSynced={synced}  DAA={daa}", end="\r")
        if synced:
            print(f"\n✅ Node synced! DAA={daa}")
            break
        await asyncio.sleep(5)
    
    # Check balance
    bal = await c.get_balance_by_address(ADDR)
    print(f"💰 Balance: {bal} sompi ({bal/1e8:.2f} KAS)")
    
    utxos = await c.get_utxos_by_addresses([ADDR])
    print(f"📦 UTXOs: {len(utxos)}")
    for u in utxos[:5]:
        e = u.get("utxoEntry", {})
        print(f"   {int(e.get('amount',0))/1e8:.2f} KAS  daa={e.get('blockDaaScore')}")
    
    await c.close()
    return bal > 0

if __name__ == "__main__":
    asyncio.run(wait_for_sync())
