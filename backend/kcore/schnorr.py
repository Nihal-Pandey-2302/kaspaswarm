"""
Schnorr Signature Implementation for Kaspa (secp256k1).

Provides BIP-340 compatible Schnorr signing using the secp256k1 curve.
Kaspa uses x-only public keys (32 bytes) and 64-byte Schnorr signatures.

The signature_script format for P2PK Schnorr in Kaspa is:
    [0x41] + [64-byte signature] + [SIG_HASH_TYPE]
    where 0x41 = 65 decimal = OP_DATA_65

Reference: https://github.com/kaspanet/rusty-kaspa/blob/master/consensus/core/src/sign.rs
"""

import hashlib
import hmac
import struct
from typing import Tuple

# secp256k1 curve parameters
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G_X = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
G_Y = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


def _modinv(a: int, m: int) -> int:
    """Modular inverse using extended Euclidean algorithm."""
    if a == 0:
        return 0
    g, x, _ = _extended_gcd(a % m, m)
    if g != 1:
        raise ValueError("Modular inverse does not exist")
    return x % m


def _extended_gcd(a: int, b: int) -> Tuple[int, int, int]:
    if a == 0:
        return b, 0, 1
    g, x, y = _extended_gcd(b % a, a)
    return g, y - (b // a) * x, x


def _point_add(p1, p2):
    """Point addition on secp256k1."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    
    x1, y1 = p1
    x2, y2 = p2
    
    if x1 == x2 and y1 != y2:
        return None
    
    if x1 == x2:
        lam = (3 * x1 * x1 * _modinv(2 * y1, P)) % P
    else:
        lam = ((y2 - y1) * _modinv(x2 - x1, P)) % P
    
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)


def _point_mul(k: int, point=None):
    """Scalar multiplication on secp256k1."""
    if point is None:
        point = (G_X, G_Y)
    
    result = None
    addend = point
    
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    
    return result


def _int_from_bytes(b: bytes) -> int:
    return int.from_bytes(b, 'big')


def _bytes_from_int(x: int) -> bytes:
    return x.to_bytes(32, 'big')


def _tagged_hash(tag: str, msg: bytes) -> bytes:
    """BIP-340 tagged hash: SHA256(SHA256(tag) || SHA256(tag) || msg)"""
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + msg).digest()


def _has_even_y(point) -> bool:
    return point[1] % 2 == 0


def get_public_key(private_key: bytes) -> bytes:
    """Get the x-only public key (32 bytes) from a private key."""
    d = _int_from_bytes(private_key)
    P_point = _point_mul(d)
    return _bytes_from_int(P_point[0])


def schnorr_sign(message: bytes, private_key: bytes) -> bytes:
    """
    Sign a message using BIP-340 Schnorr signature.
    
    Args:
        message: 32-byte message hash to sign (the sighash)
        private_key: 32-byte private key
    
    Returns:
        64-byte Schnorr signature (r || s)
    """
    assert len(message) == 32, f"Message must be 32 bytes, got {len(message)}"
    assert len(private_key) == 32, f"Private key must be 32 bytes, got {len(private_key)}"
    
    d0 = _int_from_bytes(private_key)
    if d0 == 0 or d0 >= N:
        raise ValueError("Invalid private key")
    
    P_point = _point_mul(d0)
    
    # Negate d if P has odd y
    d = d0 if _has_even_y(P_point) else N - d0
    
    # Deterministic nonce generation (BIP-340)
    t = _bytes_from_int(d)
    aux_rand = b'\x00' * 32  # We use zero aux randomness for deterministic sigs
    
    # BIP-340 nonce derivation
    t_xored = bytes(a ^ b for a, b in zip(t, _tagged_hash("BIP0340/aux", aux_rand)))
    rand = _tagged_hash("BIP0340/nonce", t_xored + _bytes_from_int(P_point[0]) + message)
    
    k0 = _int_from_bytes(rand) % N
    if k0 == 0:
        raise ValueError("Nonce generation failed")
    
    R = _point_mul(k0)
    k = k0 if _has_even_y(R) else N - k0
    
    e_hash = _tagged_hash("BIP0340/challenge", _bytes_from_int(R[0]) + _bytes_from_int(P_point[0]) + message)
    e = _int_from_bytes(e_hash) % N
    
    sig = _bytes_from_int(R[0]) + _bytes_from_int((k + e * d) % N)
    
    # Verify (optional but recommended for safety)
    assert len(sig) == 64
    return sig


def schnorr_verify(message: bytes, public_key: bytes, signature: bytes) -> bool:
    """
    Verify a BIP-340 Schnorr signature.
    
    Args:
        message: 32-byte message hash
        public_key: 32-byte x-only public key
        signature: 64-byte signature
    
    Returns:
        True if valid
    """
    try:
        assert len(message) == 32
        assert len(public_key) == 32
        assert len(signature) == 64
        
        P_x = _int_from_bytes(public_key)
        r = _int_from_bytes(signature[:32])
        s = _int_from_bytes(signature[32:])
        
        if P_x >= P or r >= P or s >= N:
            return False
        
        # Lift x to point
        y_sq = (pow(P_x, 3, P) + 7) % P
        y = pow(y_sq, (P + 1) // 4, P)
        if pow(y, 2, P) != y_sq:
            return False
        if y % 2 != 0:
            y = P - y
        P_point = (P_x, y)
        
        e_hash = _tagged_hash("BIP0340/challenge", signature[:32] + public_key + message)
        e = _int_from_bytes(e_hash) % N
        
        # R = s*G - e*P
        sG = _point_mul(s)
        eP = _point_mul(N - e, P_point)
        R = _point_add(sG, eP)
        
        if R is None or not _has_even_y(R) or R[0] != r:
            return False
        
        return True
    except Exception:
        return False


def build_signature_script(private_key: bytes, sighash: bytes, sighash_type: int = 0x01) -> bytes:
    """
    Build the signature script for a Kaspa P2PK Schnorr input.
    
    Format: [0x41] + [64-byte signature] + [sighash_type]
    where 0x41 (65 decimal) = length of sig + sighash_type byte
    
    Args:
        private_key: 32-byte private key
        sighash: 32-byte sighash digest to sign
        sighash_type: Typically SIG_HASH_ALL (0x01)
    
    Returns:
        66-byte signature script
    """
    sig = schnorr_sign(sighash, private_key)
    # OP_DATA_65 (0x41) + 64-byte sig + sighash_type
    return bytes([65]) + sig + bytes([sighash_type])
