"""
Kaspa Transaction SigHash Computation.

Implements the BIP-143-like sighash algorithm used by Kaspa,
adapted from rusty-kaspa consensus/core/src/hashing/sighash.rs.

Key differences from Bitcoin:
- Uses Blake2b (keyed with b"TransactionSigningHash") instead of SHA256
- All integers are little-endian
- Includes sig_op_count per input
- Uses Schnorr signatures on secp256k1

Reference:  https://github.com/kaspanet/rusty-kaspa/blob/master/consensus/core/src/hashing/sighash.rs
"""

import struct
from hashlib import blake2b
from typing import List, Optional
from dataclasses import dataclass


# --- Constants ---
SIG_HASH_ALL = 0x01
SIG_HASH_NONE = 0x02
SIG_HASH_SINGLE = 0x04
SIG_HASH_ANY_ONE_CAN_PAY = 0x80
SIG_HASH_MASK = 0x07

# Blake2b key used for TransactionSigningHash in Kaspa
TRANSACTION_SIGNING_HASH_KEY = b"TransactionSigningHash"

# Native subnetwork ID (20 bytes of zeros)
NATIVE_SUBNETWORK_ID = b'\x00' * 20

# Zero hash (32 bytes)
ZERO_HASH = b'\x00' * 32


# --- Data Structures ---
@dataclass
class Outpoint:
    """A reference to a specific UTXO."""
    transaction_id: bytes   # 32 bytes (hash)
    index: int              # u32


@dataclass
class ScriptPublicKey:
    """Represents a script public key with version."""
    version: int            # u16
    script: bytes           # Variable length (e.g., 34 bytes for P2PK)


@dataclass
class UtxoEntry:
    """A UTXO entry with its value and script."""
    amount: int             # u64 (sompi)
    script_public_key: ScriptPublicKey
    block_daa_score: int
    is_coinbase: bool


@dataclass
class TransactionInput:
    """A transaction input consuming a UTXO."""
    previous_outpoint: Outpoint
    signature_script: bytes  # Filled after signing
    sequence: int           # u64
    sig_op_count: int       # u8


@dataclass
class TransactionOutput:
    """A transaction output creating a new UTXO."""
    value: int              # u64 (sompi)
    script_public_key: ScriptPublicKey


@dataclass
class Transaction:
    """A Kaspa transaction."""
    version: int            # u16
    inputs: List[TransactionInput]
    outputs: List[TransactionOutput]
    lock_time: int          # u64
    subnetwork_id: bytes    # 20 bytes
    gas: int                # u64
    payload: bytes          # Variable length


# --- Blake2b Hasher (matches TransactionSigningHash in rusty-kaspa) ---
def new_signing_hasher() -> blake2b:
    """Create a new Blake2b hasher with the TransactionSigningHash domain key."""
    return blake2b(digest_size=32, key=TRANSACTION_SIGNING_HASH_KEY)


def write_u8(hasher: blake2b, val: int):
    hasher.update(struct.pack('<B', val))


def write_u16(hasher: blake2b, val: int):
    hasher.update(struct.pack('<H', val))


def write_u32(hasher: blake2b, val: int):
    hasher.update(struct.pack('<I', val))


def write_u64(hasher: blake2b, val: int):
    hasher.update(struct.pack('<Q', val))


def write_var_bytes(hasher: blake2b, data: bytes):
    """Write length as u64 LE followed by the bytes."""
    write_u64(hasher, len(data))
    hasher.update(data)


# --- Sub-hash computations ---
def hash_previous_outputs(tx: Transaction, hash_type: int) -> bytes:
    """Hash all input outpoints."""
    if hash_type & SIG_HASH_ANY_ONE_CAN_PAY:
        return ZERO_HASH

    h = new_signing_hasher()
    for inp in tx.inputs:
        h.update(inp.previous_outpoint.transaction_id)
        write_u32(h, inp.previous_outpoint.index)
    return h.digest()


def hash_sequences(tx: Transaction, hash_type: int) -> bytes:
    """Hash all input sequences."""
    masked = hash_type & SIG_HASH_MASK
    if masked == SIG_HASH_SINGLE or masked == SIG_HASH_NONE or (hash_type & SIG_HASH_ANY_ONE_CAN_PAY):
        return ZERO_HASH

    h = new_signing_hasher()
    for inp in tx.inputs:
        write_u64(h, inp.sequence)
    return h.digest()


def hash_sig_op_counts(tx: Transaction, hash_type: int) -> bytes:
    """Hash all input sig_op_counts."""
    if hash_type & SIG_HASH_ANY_ONE_CAN_PAY:
        return ZERO_HASH

    h = new_signing_hasher()
    for inp in tx.inputs:
        write_u8(h, inp.sig_op_count)
    return h.digest()


def hash_output(hasher: blake2b, output: TransactionOutput):
    """Hash a single output into the hasher."""
    write_u64(hasher, output.value)
    hash_script_public_key(hasher, output.script_public_key)


def hash_script_public_key(hasher: blake2b, spk: ScriptPublicKey):
    """Hash a script public key into the hasher."""
    write_u16(hasher, spk.version)
    write_var_bytes(hasher, spk.script)


def hash_outputs(tx: Transaction, hash_type: int, input_index: int) -> bytes:
    """Hash transaction outputs based on sighash type."""
    masked = hash_type & SIG_HASH_MASK
    if masked == SIG_HASH_NONE:
        return ZERO_HASH

    if masked == SIG_HASH_SINGLE:
        if input_index >= len(tx.outputs):
            return ZERO_HASH
        h = new_signing_hasher()
        hash_output(h, tx.outputs[input_index])
        return h.digest()

    # SIG_HASH_ALL — hash all outputs
    h = new_signing_hasher()
    for out in tx.outputs:
        hash_output(h, out)
    return h.digest()


def hash_payload(tx: Transaction) -> bytes:
    """Hash the transaction payload."""
    if tx.subnetwork_id == NATIVE_SUBNETWORK_ID and len(tx.payload) == 0:
        return ZERO_HASH

    h = new_signing_hasher()
    write_var_bytes(h, tx.payload)
    return h.digest()


# --- Main SigHash Computation ---
def calc_schnorr_signature_hash(
    tx: Transaction,
    input_index: int,
    hash_type: int,
    utxo_entry: UtxoEntry
) -> bytes:
    """
    Compute the Schnorr signature hash for a specific input.

    This is the hash that gets signed with the private key.

    Args:
        tx: The transaction being signed
        input_index: Index of the input being signed
        hash_type: SIG_HASH_ALL (0x01) for standard transactions
        utxo_entry: The UTXO being spent by this input

    Returns:
        32-byte hash to be signed
    """
    inp = tx.inputs[input_index]

    h = new_signing_hasher()

    # 1. Transaction version (u16 LE)
    write_u16(h, tx.version)

    # 2. Hash of all previous outpoints
    h.update(hash_previous_outputs(tx, hash_type))

    # 3. Hash of all sequences
    h.update(hash_sequences(tx, hash_type))

    # 4. Hash of all sig_op_counts
    h.update(hash_sig_op_counts(tx, hash_type))

    # 5. This input's outpoint (tx_id + index)
    h.update(inp.previous_outpoint.transaction_id)
    write_u32(h, inp.previous_outpoint.index)

    # 6. The UTXO's script public key being spent
    hash_script_public_key(h, utxo_entry.script_public_key)

    # 7. The UTXO's value (u64 LE)
    write_u64(h, utxo_entry.amount)

    # 8. This input's sequence (u64 LE)
    write_u64(h, inp.sequence)

    # 9. This input's sig_op_count (u8)
    write_u8(h, inp.sig_op_count)

    # 10. Hash of outputs
    h.update(hash_outputs(tx, hash_type, input_index))

    # 11. Lock time (u64 LE)
    write_u64(h, tx.lock_time)

    # 12. Subnetwork ID (20 bytes)
    h.update(tx.subnetwork_id)

    # 13. Gas (u64 LE)
    write_u64(h, tx.gas)

    # 14. Payload hash
    h.update(hash_payload(tx))

    # 15. SigHash type (u8)
    write_u8(h, hash_type)

    return h.digest()


# --- Helper: Build P2PK ScriptPublicKey from public key ---
def make_p2pk_script(public_key_bytes: bytes) -> ScriptPublicKey:
    """
    Create a P2PK (Pay-to-Public-Key) ScriptPublicKey for Schnorr.

    Script format: OP_DATA_32 <32-byte-pubkey> OP_CHECKSIG
    Hex:           20 <pubkey> ac
    """
    assert len(public_key_bytes) == 32, f"Expected 32-byte x-only pubkey, got {len(public_key_bytes)}"
    script = bytes([0x20]) + public_key_bytes + bytes([0xac])
    return ScriptPublicKey(version=0, script=script)
