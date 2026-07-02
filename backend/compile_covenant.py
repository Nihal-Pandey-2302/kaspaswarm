"""
Compile the stateful rolling-allowance covenant (backend/covenants/rolling_vault.sil)
with the SilverScript compiler and derive its on-chain P2SH address.

This proves the full pipeline for the ADVANCED (stateful) covenant:
    SilverScript source  --silverc-->  real Kaspa script  -->  fundable P2SH address

Usage:
    # needs `silverc` on PATH (cargo install --git github.com/kaspanet/silverscript)
    python -m backend.compile_covenant

If `silverc` is not installed, it falls back to the committed artifact
(backend/covenants/rolling_vault.json) so the address can still be derived.

Params are derived deterministically from a fixed demo seed so the artifact and
address are stable/reproducible. PoC — testnet-10 only.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

from kaspa import Keypair, ScriptBuilder, address_from_script_public_key

from backend.kcore.treasury_vault import derive_key, network_type_from_id

HERE = os.path.dirname(__file__)
SIL = os.path.join(HERE, "covenants", "rolling_vault.sil")
ARTIFACT = os.path.join(HERE, "covenants", "rolling_vault.json")
NETWORK_TYPE = network_type_from_id(os.getenv("KASPA_NETWORK_ID", "testnet-10"))

# Deterministic demo parameters (stable artifact + address).
AGENT = Keypair.from_private_key(derive_key("kaspaswarm-demo", "allowance-agent"))
OWNER = Keypair.from_private_key(derive_key("kaspaswarm-demo", "allowance-owner"))
ALLOWANCE_PER_BLOCK = 100_000        # sompi accrued per block
WINDOW_START = bytes(8)              # 8-byte state slot (advanced on each draw)


def _barr(bs: bytes) -> dict:
    return {"kind": "array", "data": [{"kind": "byte", "data": b} for b in bs]}


def constructor_args() -> list:
    owner_hash = hashlib.blake2b(bytes.fromhex(OWNER.xonly_public_key), digest_size=32).digest()
    return [
        _barr(bytes.fromhex(AGENT.xonly_public_key)),  # pubkey agent
        _barr(owner_hash),                             # byte[32] owner (blake2b of pubkey)
        {"kind": "int", "data": ALLOWANCE_PER_BLOCK},  # allowancePerBlock
        _barr(WINDOW_START),                           # byte[8] windowStart (state)
    ]


def compile_artifact() -> dict:
    """Compile rolling_vault.sil with silverc if available, else load the committed
    artifact. Returns the compiled JSON artifact."""
    if shutil.which("silverc"):
        with tempfile.TemporaryDirectory() as tmp:
            args_path = os.path.join(tmp, "args.json")
            out_path = os.path.join(tmp, "rolling_vault.json")
            with open(args_path, "w") as f:
                json.dump(constructor_args(), f)
            subprocess.run(["silverc", SIL, "--constructor-args", args_path, "-o", out_path], check=True)
            artifact = json.load(open(out_path))
        with open(ARTIFACT, "w") as f:      # refresh the committed artifact
            json.dump(artifact, f, indent=2)
        return artifact
    print("⚠️ silverc not on PATH — using committed artifact")
    return json.load(open(ARTIFACT))


def covenant_address(artifact: dict) -> str:
    script = bytes(artifact["script"])
    spk = ScriptBuilder.from_script(script, covenants_enabled=True).create_pay_to_script_hash_script()
    return address_from_script_public_key(spk, NETWORK_TYPE).to_string()


if __name__ == "__main__":
    art = compile_artifact()
    print(f"contract       : {art.get('contract_name')} (compiler {art.get('compiler_version')})")
    print(f"script bytes   : {len(art.get('script', []))}")
    print(f"entrypoints    : {[f['name'] for f in art.get('abi', [])]}")
    print(f"covenant addr  : {covenant_address(art)}")
