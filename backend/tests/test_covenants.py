"""Offline tests for the covenant scripts (no network).

Covers the two win-critical guarantees that must never silently regress:
  - the treasury vault derives a stable, valid P2SH address and assembles unlock
    scripts for both branches;
  - each escrow task derives a UNIQUE covenant address (task_id binding) so
    concurrent tasks can't collide on one UTXO.
"""
from kaspa import Keypair, pay_to_address_script

from backend.kcore.treasury_vault import (
    auto_unlock_script,
    build_redeem_script,
    derive_key,
    derive_vault,
    manual_unlock_script,
    network_type_from_id,
)
from backend.kcore.escrow_covenant import derive_escrow


def _kp():
    return Keypair.random()


def _addr():
    return _kp().to_address("testnet").to_string()


def test_network_type_from_id():
    assert network_type_from_id("testnet-10") == "testnet"
    assert network_type_from_id("testnet-12") == "testnet"
    assert network_type_from_id("mainnet") == "mainnet"
    assert network_type_from_id("") == "testnet"


def test_derive_key_deterministic_and_valid():
    # Compare via the derived x-only pubkey (a valid key always yields one).
    a1 = Keypair.from_private_key(derive_key("seed-x", "vault-agent")).xonly_public_key
    a2 = Keypair.from_private_key(derive_key("seed-x", "vault-agent")).xonly_public_key
    b = Keypair.from_private_key(derive_key("seed-x", "vault-owner")).xonly_public_key
    # deterministic for same (seed,label); different labels -> different keys
    assert a1 == a2
    assert a1 != b


def test_treasury_vault_address_stable_and_valid():
    agent, owner = _kp(), _kp()
    ben = pay_to_address_script(_kp().to_address("testnet"))
    v1 = derive_vault(agent.xonly_public_key, owner.xonly_public_key, ben, 200_000_000, "testnet")
    v2 = derive_vault(agent.xonly_public_key, owner.xonly_public_key, ben, 200_000_000, "testnet")
    assert v1.address_str() == v2.address_str()          # deterministic
    assert v1.address_str().startswith("kaspatest:p")    # P2SH testnet prefix
    assert len(v1.redeem_bytes) > 0


def test_treasury_cap_changes_address():
    agent, owner = _kp(), _kp()
    ben = pay_to_address_script(_kp().to_address("testnet"))
    lo = derive_vault(agent.xonly_public_key, owner.xonly_public_key, ben, 100_000_000, "testnet")
    hi = derive_vault(agent.xonly_public_key, owner.xonly_public_key, ben, 900_000_000, "testnet")
    # a different policy (cap) must be a different covenant
    assert lo.address_str() != hi.address_str()


def test_treasury_unlock_scripts_assemble():
    agent, owner = _kp(), _kp()
    ben = pay_to_address_script(_kp().to_address("testnet"))
    v = derive_vault(agent.xonly_public_key, owner.xonly_public_key, ben, 200_000_000, "testnet")
    sig = "41" + "11" * 65
    auto = auto_unlock_script(v, sig)
    manual = manual_unlock_script(v, "41" + "22" * 65, sig)
    assert isinstance(auto, bytes) and len(auto) > len(v.redeem_bytes)
    # manual carries two sigs, so its unlock is larger than the single-sig auto
    assert len(manual) > len(auto)


def test_escrow_address_unique_per_task():
    """The core fix: task_id is bound into the escrow covenant so two tasks for the
    same (coordinator, solver) pair derive DIFFERENT covenant addresses."""
    coord_kp = _kp()
    coord_addr = coord_kp.to_address("testnet").to_string()
    solver_addr = _addr()
    v1 = derive_escrow(coord_kp.xonly_public_key, solver_addr, coord_addr, "testnet", task_id=1)
    v2 = derive_escrow(coord_kp.xonly_public_key, solver_addr, coord_addr, "testnet", task_id=2)
    same = derive_escrow(coord_kp.xonly_public_key, solver_addr, coord_addr, "testnet", task_id=1)
    assert v1.address_str() != v2.address_str()   # unique per task
    assert v1.address_str() == same.address_str() # but stable for the same task


def test_rolling_vault_artifact_derives_address():
    """The stateful rolling-allowance covenant (compiled by silverc) is a real
    Kaspa script that derives a fundable P2SH address — validated from the committed
    artifact so CI doesn't need the Rust compiler installed."""
    import json
    import os
    from kaspa import ScriptBuilder, address_from_script_public_key

    artifact = os.path.join(os.path.dirname(__file__), "..", "covenants", "rolling_vault.json")
    d = json.load(open(artifact))
    assert d["contract_name"] == "AgentAllowance"
    assert len(d["script"]) > 0
    assert {f["name"] for f in d["abi"]} == {"draw", "reclaim"}
    spk = ScriptBuilder.from_script(bytes(d["script"]), covenants_enabled=True).create_pay_to_script_hash_script()
    addr = address_from_script_public_key(spk, "testnet")
    assert addr.to_string().startswith("kaspatest:p")


def test_escrow_pins_solver_and_coordinator():
    coord_kp = _kp()
    coord_addr = coord_kp.to_address("testnet").to_string()
    solver_addr = _addr()
    v = derive_escrow(coord_kp.xonly_public_key, solver_addr, coord_addr, "testnet", task_id=7)
    # the escrow records the two spk targets it will pin on-chain
    assert v.solver_spk is not None and v.coordinator_spk is not None
    assert v.address_str().startswith("kaspatest:p")
