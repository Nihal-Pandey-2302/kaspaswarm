"""
Kaspa CashAddr encoding/decoding utility.

Kaspa uses Bitcoin Cash-style CashAddr encoding (NOT BIP-350 Bech32m).
Ported from bech32cashaddr JS library used by kaspalib (CoinSpace).

Key differences from BIP-350:
- 40-bit polymod generators (vs 32-bit)
- 8-character checksum (vs 6)
- Native ':' separator (vs '1')
"""

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

# CashAddr polymod generators (40-bit, from bech32cashaddr)
POLYMOD_GENERATORS = [
    0x98f2bc8e61,
    0x79b76d99e2,
    0xf33e5fb3c4,
    0xae2eabe2a8,
    0x1e4f43e470,
]

# Address version bytes
ADDRESS_VERSION = {
    "pk": 0,           # Schnorr P2PK (32-byte X-only pubkey)
    "pk-ecdsa": 1,     # ECDSA P2PK (33-byte compressed pubkey)
    "sh": 8,           # Script Hash (32 bytes)
}

ADDRESS_PAYLOAD_LENGTH = {
    "pk": 32,
    "pk-ecdsa": 33,
    "sh": 32,
}

ADDRESS_PREFIXES = {
    "mainnet": "kaspa",
    "testnet": "kaspatest",
    "simnet": "kaspasim",
    "devnet": "kaspadev",
}


def cashaddr_polymod(pre):
    """CashAddr polymod (40-bit generators)."""
    b = pre >> 35
    chk = (pre & 0x07ffffffff) << 5
    for i in range(5):
        if ((b >> i) & 1) == 1:
            chk ^= POLYMOD_GENERATORS[i]
    return chk


def cashaddr_checksum(prefix, words):
    """Compute 8-character CashAddr checksum."""
    chk = 1
    for c in prefix:
        chk = cashaddr_polymod(chk) ^ (ord(c) & 0x1f)
    chk = cashaddr_polymod(chk)
    for v in words:
        chk = cashaddr_polymod(chk) ^ v
    for _ in range(8):
        chk = cashaddr_polymod(chk)
    chk ^= 1

    result = []
    for i in range(8):
        result.append((chk >> (5 * (7 - i))) & 31)
    return result


def convertbits(data, frombits, tobits, pad=True):
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if isinstance(value, int):
            v = value
        else:
            v = value
        acc = (acc << frombits) | v
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    return ret


def encode_address(prefix, addr_type, payload):
    """
    Encode a Kaspa address using CashAddr.
    
    Args:
        prefix: Network prefix (e.g. 'kaspatest')
        addr_type: 'pk' (Schnorr), 'pk-ecdsa', or 'sh'
        payload: Raw bytes (public key or script hash)
    
    Returns:
        Kaspa address string (e.g. 'kaspatest:qq...')
    """
    version = ADDRESS_VERSION[addr_type]
    expected_len = ADDRESS_PAYLOAD_LENGTH[addr_type]
    if len(payload) != expected_len:
        raise ValueError(f"Payload length {len(payload)} != expected {expected_len} for {addr_type}")
    
    raw = bytes([version]) + payload
    words = convertbits(raw, 8, 5)
    check = cashaddr_checksum(prefix, words)
    combined = words + check
    addr_str = ''.join([CHARSET[d] for d in combined])
    return f"{prefix}:{addr_str}"


def decode_address(address):
    """
    Decode a Kaspa CashAddr address.
    
    Returns:
        dict with 'prefix', 'type', 'payload' keys
    """
    address = address.lower()
    pos = address.rfind(':')
    if pos == -1:
        raise ValueError("Missing ':' separator")
    
    prefix = address[:pos]
    payload_str = address[pos + 1:]
    
    if len(payload_str) < 8:
        raise ValueError("Address too short")
    
    # Decode all characters
    all_words = []
    for c in payload_str:
        val = CHARSET.find(c)
        if val == -1:
            raise ValueError(f"Invalid character: {c}")
        all_words.append(val)
    
    # Split data and checksum
    words = all_words[:-8]
    checksum_str = payload_str[-8:]
    
    # Verify checksum
    expected_check = cashaddr_checksum(prefix, words)
    expected_str = ''.join([CHARSET[d] for d in expected_check])
    if checksum_str != expected_str:
        raise ValueError(f"Invalid checksum: expected {expected_str}, got {checksum_str}")
    
    # Convert 5-bit words to 8-bit bytes
    data_bytes = []
    acc = 0
    bits = 0
    for v in words:
        acc = (acc << 5) | v
        bits += 5
        while bits >= 8:
            bits -= 8
            data_bytes.append((acc >> bits) & 0xff)
    
    version = data_bytes[0]
    payload = bytes(data_bytes[1:])
    
    # Determine type from version
    type_name = None
    for name, ver in ADDRESS_VERSION.items():
        if ver == version:
            type_name = name
            break
    
    if type_name is None:
        raise ValueError(f"Unknown version: {version}")
    
    return {
        "prefix": prefix,
        "type": type_name,
        "payload": payload,
    }
