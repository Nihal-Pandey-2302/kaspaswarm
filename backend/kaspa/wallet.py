"""
Kaspa Wallet — Real on-chain transaction support for the agent swarm.

Manages:
- Key generation (secp256k1)
- UTXO fetching via wRPC
- Transaction construction (inputs, outputs, change)
- Schnorr signing
- Transaction broadcasting

When MOCK_MODE=true, uses simulated transactions.
When MOCK_MODE=false, constructs and broadcasts real Kaspa transactions.
"""

import asyncio
from typing import Optional, Dict, List
import httpx
from dataclasses import dataclass
import secrets
import hashlib
import ecdsa
import time
import os
import sys
import struct

# Add backend directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from bech32_util import encode_address, decode_address

from kaspa.sighash import (
    Transaction, TransactionInput, TransactionOutput,
    Outpoint, ScriptPublicKey, UtxoEntry,
    calc_schnorr_signature_hash, make_p2pk_script,
    SIG_HASH_ALL, NATIVE_SUBNETWORK_ID
)
from kaspa.schnorr import build_signature_script, get_public_key
from kaspa.wrpc_client import KaspaRpcClient


# Minimum fee per transaction in sompi (0.0001 KAS per UTXO typically)
MIN_FEE_PER_INPUT = 10_000  # 0.0001 KAS
DEFAULT_FEE = 10_000        # Base fee for simple tx


@dataclass
class KaspaAddress:
    """Represents a Kaspa wallet address with credentials."""
    address: str
    private_key: str        # hex
    public_key: str         # hex (x-only 32 bytes)
    balance: int = 0        # in sompi


class KaspaWallet:
    """
    Manages Kaspa wallet operations for agents.
    
    In live mode:
    - Connects to testnet-10 via wRPC WebSocket
    - Fetches real UTXOs
    - Constructs, signs, and broadcasts transactions
    
    In mock mode:
    - Returns simulated transaction hashes
    """
    
    def __init__(self, rpc_url: str = "https://api.kaspa.org/testnet", mock_mode: bool = False):
        self.rpc_url = rpc_url
        self.mock_mode = mock_mode
        self.client = httpx.AsyncClient(timeout=30.0)
        self._address_counter = 0
        
        # wRPC client for real transactions
        self._rpc: Optional[KaspaRpcClient] = None
        self._rpc_connected = False
        
        # wRPC endpoint — default to local kaspad node (run with --rpclisten-json=default)
        self._ws_url = os.getenv("KASPA_WS_URL", "ws://127.0.0.1:18210")

    async def _ensure_rpc(self) -> bool:
        """Ensure wRPC connection is established."""
        if self.mock_mode:
            return True
        
        if self._rpc_connected and self._rpc:
            return True
        
        self._rpc = KaspaRpcClient(ws_url=self._ws_url)
        connected = await self._rpc.connect()
        self._rpc_connected = connected
        
        if connected:
            try:
                info = await self._rpc.get_server_info()
                print(f"🌐 Kaspa node: {info.get('serverVersion', 'unknown')}")
            except Exception:
                pass
        
        return connected

    async def create_address(self) -> KaspaAddress:
        """Generate new Kaspa address (SECP256k1) or load from Env."""
        # Check for injected credentials (for Coordinator)
        env_addr = os.getenv("COORDINATOR_ADDRESS")
        env_key = os.getenv("COORDINATOR_PRIVATE_KEY")
        
        if env_addr and env_key and not self.mock_mode:
            if self._address_counter == 0: 
                self._address_counter += 1
                # Derive public key from private key
                pk_bytes = bytes.fromhex(env_key)
                pub_key = get_public_key(pk_bytes)
                return KaspaAddress(
                    address=env_addr,
                    private_key=env_key,
                    public_key=pub_key.hex(),
                    balance=0
                )

        if self.mock_mode:
            self._address_counter += 1
            address_hash = hashlib.sha256(f"agent_{self._address_counter}".encode()).hexdigest()[:40]
            return KaspaAddress(
                address=f"kaspatest:qq{address_hash}",
                private_key=secrets.token_hex(32),
                public_key="mock_pubkey",
                balance=10_000_000
            )
        
        # 1. Generate Private Key (SECP256k1)
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        private_key_hex = sk.to_string().hex()
        
        # 2. Extract X-only public key (32 bytes) for Schnorr P2PK
        x_only_pub_key = vk.to_string()[:32]
        
        # 3. Encode using CashAddr (Kaspa's native format)
        address = encode_address("kaspatest", "pk", x_only_pub_key)
        
        self._address_counter += 1
        return KaspaAddress(
            address=address,
            private_key=private_key_hex,
            public_key=x_only_pub_key.hex(),
            balance=0
        )

    async def get_balance(self, address: str) -> int:
        """Get balance in sompi."""
        if self.mock_mode:
            return 10_000_000
        
        # Try wRPC first
        if await self._ensure_rpc():
            try:
                balance = await self._rpc.get_balance_by_address(address)
                return balance
            except Exception as e:
                pass
        
        # Fallback to REST API
        try:
            response = await self.client.post(
                f"{self.rpc_url}/messages", 
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalanceByAddress",
                    "params": {"address": address}
                }
            )
            data = response.json()
            return int(data.get("result", {}).get("balance", 0))
        except Exception as e:
            return 0

    async def get_utxos(self, address: str) -> List[Dict]:
        """Fetch UTXOs for an address via wRPC or REST API."""
        # Try wRPC first
        try:
            if await self._ensure_rpc():
                utxos = await self._rpc.get_utxos_by_addresses([address])
                if utxos:
                    return utxos
        except Exception:
            pass
        
        # Fallback: REST API
        rest_urls = [
            "https://api-tn10.kaspa.org",
            self.rpc_url
        ]
        for base_url in rest_urls:
            try:
                resp = await self.client.get(f"{base_url}/addresses/{address}/utxos", timeout=10.0)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
        
        raise ConnectionError("Cannot fetch UTXOs — all endpoints unreachable")

    def _select_utxos(self, utxos: List[Dict], amount: int, fee: int) -> tuple:
        """
        Select UTXOs to cover the amount + fee.
        Returns (selected_utxos, total_input, change_amount).
        """
        total_needed = amount + fee
        selected = []
        total_input = 0
        
        # Sort by amount descending (use larger UTXOs first to minimize inputs)
        sorted_utxos = sorted(utxos, key=lambda u: int(u.get("utxoEntry", {}).get("amount", "0")), reverse=True)
        
        for utxo in sorted_utxos:
            entry = utxo.get("utxoEntry", {})
            utxo_amount = int(entry.get("amount", "0"))
            if utxo_amount == 0:
                continue
            
            selected.append(utxo)
            total_input += utxo_amount
            
            # Adjust fee based on number of inputs
            fee = DEFAULT_FEE + (len(selected) - 1) * MIN_FEE_PER_INPUT
            total_needed = amount + fee
            
            if total_input >= total_needed:
                change = total_input - total_needed
                return selected, total_input, change, fee
        
        raise ValueError(
            f"Insufficient balance: have {total_input} sompi, "
            f"need {total_needed} sompi (amount={amount} + fee={fee})"
        )

    def _build_transaction(
        self,
        selected_utxos: List[Dict],
        to_address: str,
        amount: int,
        change_address: str,
        change_amount: int,
    ) -> tuple:
        """
        Build a Transaction object from UTXOs and desired outputs.
        Returns (Transaction, list of UtxoEntry for signing).
        """
        inputs = []
        utxo_entries = []
        
        for utxo in selected_utxos:
            outpoint = utxo.get("outpoint", {})
            entry = utxo.get("utxoEntry", {})
            spk = entry.get("scriptPublicKey", {})
            
            tx_id_hex = outpoint.get("transactionId", "")
            tx_id_bytes = bytes.fromhex(tx_id_hex)
            index = int(outpoint.get("index", 0))
            
            inputs.append(TransactionInput(
                previous_outpoint=Outpoint(
                    transaction_id=tx_id_bytes,
                    index=index
                ),
                signature_script=b'',  # Filled after signing
                sequence=0,
                sig_op_count=1  # Always 1 for P2PK Schnorr
            ))
            
            utxo_entries.append(UtxoEntry(
                amount=int(entry.get("amount", "0")),
                script_public_key=ScriptPublicKey(
                    version=int(spk.get("version", 0)),
                    script=bytes.fromhex(spk.get("scriptPublicKey", ""))
                ),
                block_daa_score=int(entry.get("blockDaaScore", "0")),
                is_coinbase=entry.get("isCoinbase", False)
            ))
        
        # Build outputs
        outputs = []
        
        # Output 1: Payment to recipient
        decoded_to = decode_address(to_address)
        to_pubkey = decoded_to['payload']
        if isinstance(to_pubkey, str):
            to_pubkey = bytes.fromhex(to_pubkey)
        to_script = make_p2pk_script(to_pubkey)
        outputs.append(TransactionOutput(
            value=amount,
            script_public_key=to_script
        ))
        
        # Output 2: Change back to sender (if any)
        if change_amount > 0:
            decoded_change = decode_address(change_address)
            change_pubkey = decoded_change['payload']
            if isinstance(change_pubkey, str):
                change_pubkey = bytes.fromhex(change_pubkey)
            change_script = make_p2pk_script(change_pubkey)
            outputs.append(TransactionOutput(
                value=change_amount,
                script_public_key=change_script
            ))
        
        tx = Transaction(
            version=0,
            inputs=inputs,
            outputs=outputs,
            lock_time=0,
            subnetwork_id=NATIVE_SUBNETWORK_ID,
            gas=0,
            payload=b''
        )
        
        return tx, utxo_entries

    def _sign_transaction(self, tx: Transaction, utxo_entries: List[UtxoEntry], private_key_hex: str) -> Transaction:
        """Sign all inputs of a transaction with the private key."""
        private_key = bytes.fromhex(private_key_hex)
        
        for i in range(len(tx.inputs)):
            # Compute sighash for this input
            sighash = calc_schnorr_signature_hash(
                tx=tx,
                input_index=i,
                hash_type=SIG_HASH_ALL,
                utxo_entry=utxo_entries[i]
            )
            
            # Sign and build signature script
            sig_script = build_signature_script(
                private_key=private_key,
                sighash=sighash,
                sighash_type=SIG_HASH_ALL
            )
            
            tx.inputs[i].signature_script = sig_script
        
        return tx

    def _tx_to_json(self, tx: Transaction) -> Dict:
        """Serialize a Transaction to JSON for submission via wRPC."""
        inputs = []
        for inp in tx.inputs:
            inputs.append({
                "previousOutpoint": {
                    "transactionId": inp.previous_outpoint.transaction_id.hex(),
                    "index": inp.previous_outpoint.index
                },
                "signatureScript": inp.signature_script.hex(),
                "sequence": inp.sequence,
                "sigOpCount": inp.sig_op_count
            })
        
        outputs = []
        for out in tx.outputs:
            outputs.append({
                "amount": out.value,
                "scriptPublicKey": {
                    "version": out.script_public_key.version,
                    "scriptPublicKey": out.script_public_key.script.hex()
                }
            })
        
        return {
            "version": tx.version,
            "inputs": inputs,
            "outputs": outputs,
            "lockTime": tx.lock_time,
            "subnetworkId": tx.subnetwork_id.hex(),
            "gas": tx.gas,
            "payload": tx.payload.hex() if tx.payload else ""
        }

    async def send_transaction(self, from_addr: KaspaAddress, to_addr: str, amount: int) -> str:
        """
        Send a real Kaspa transaction.
        
        Flow:
        1. Fetch UTXOs for sender
        2. Select UTXOs covering amount + fee
        3. Build transaction with payment + change outputs
        4. Compute sighash for each input  
        5. Sign each input with Schnorr
        6. Broadcast via wRPC
        
        Args:
            from_addr: Sender's KaspaAddress (with private key)
            to_addr: Recipient's address string
            amount: Amount in sompi
        
        Returns:
            Transaction ID (hash) or "failed"
        """
        if self.mock_mode:
            await asyncio.sleep(0.5)
            return f"tx_{secrets.token_hex(8)}"
            
        try:
            print(f"📤 Building tx: {amount} sompi from {from_addr.address[:20]}... → {to_addr[:20]}...")
            
            # 1. Fetch UTXOs
            utxos = await self.get_utxos(from_addr.address)
            if not utxos:
                print(f"❌ No UTXOs found for {from_addr.address}")
                return "failed_no_utxos"
            
            print(f"   Found {len(utxos)} UTXOs")
            
            # 2. Select UTXOs
            selected, total_input, change, fee = self._select_utxos(utxos, amount, DEFAULT_FEE)
            print(f"   Selected {len(selected)} UTXOs, total={total_input}, fee={fee}, change={change}")
            
            # 3. Build transaction
            tx, utxo_entries = self._build_transaction(
                selected_utxos=selected,
                to_address=to_addr,
                amount=amount,
                change_address=from_addr.address,
                change_amount=change
            )
            
            # 4. Sign all inputs
            tx = self._sign_transaction(tx, utxo_entries, from_addr.private_key)
            print(f"   ✅ Signed {len(tx.inputs)} inputs")
            
            # 5. Serialize to JSON
            tx_json = self._tx_to_json(tx)
            
            # 6. Broadcast — try wRPC first, then REST API
            tx_id = None
            
            # Try wRPC
            try:
                if await self._ensure_rpc():
                    tx_id = await self._rpc.submit_transaction(tx_json)
            except Exception as e:
                print(f"   ⚠️ wRPC broadcast failed: {e}")
            
            # Fallback: REST API
            if not tx_id:
                rest_urls = [
                    "https://api-tn10.kaspa.org",
                    self.rpc_url
                ]
                rest_payload = {
                    "transaction": tx_json,
                    "allowOrphan": False
                }
                for base_url in rest_urls:
                    try:
                        resp = await self.client.post(
                            f"{base_url}/transactions",
                            json=rest_payload,
                            timeout=15.0
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            tx_id = data.get("transactionId", "")
                            break
                    except Exception:
                        continue
            
            if not tx_id:
                print("❌ All broadcast methods failed (testnet-10 infrastructure may be down)")
                return "failed_broadcast"
            
            print(f"   🎉 Broadcast success! TX: {tx_id}")
            
            # Update sender balance
            from_addr.balance = max(0, from_addr.balance - amount - fee)
            
            return tx_id
            
        except ValueError as e:
            print(f"❌ Tx Failed (insufficient funds): {e}")
            return "failed_insufficient_funds"
        except ConnectionError as e:
            print(f"❌ Tx Failed (connection): {e}")
            return "failed_connection"
        except Exception as e:
            print(f"❌ Tx Failed: {e}")
            import traceback
            traceback.print_exc()
            return "failed"

    async def close(self):
        """Close all connections."""
        await self.client.aclose()
        if self._rpc:
            await self._rpc.close()
