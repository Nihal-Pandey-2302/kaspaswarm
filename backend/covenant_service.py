"""
Covenant service — drives the Agent Treasury Vault proof for the API/UI.

Wraps the live 4-act covenant flow (see backend/covenant_demo.py) in a structured,
awaitable runner that returns machine-readable results the dashboard can render,
and caches the last run so the UI shows it without re-running.

Exposed to the API by backend/api/websocket.py:
    GET  /api/covenant/status  -> vault info + last proof result + run state
    POST /api/covenant/run     -> kick off a proof in the background
"""
from __future__ import annotations

import asyncio
import copy
import os
import time

from dotenv import load_dotenv
from kaspa import Keypair, PrivateKey, Resolver, RpcClient, create_input_signature, pay_to_address_script, Address

from backend.covenant_demo import CAP, FUND_AMOUNTS, KAS, NETWORK_ID, NETWORK_TYPE, fund_vault, link, wait_for_utxos, _take
from backend.kcore.treasury_vault import (
    auto_unlock_script,
    derive_key,
    derive_vault,
    manual_unlock_script,
    spend_vault,
)

load_dotenv()

ADDR_EXPLORER = "https://tn10.kaspa.stream/addresses"

# Module-level run state (single swarm process).
_STATE: dict = {"running": False, "result": None, "error": None, "started_at": None}
_TASK: "asyncio.Task | None" = None   # strong ref so the run isn't GC'd mid-flight


def _publish(result: dict) -> None:
    """Store an isolated (deep-copied) snapshot so a concurrent poll can't observe
    a half-updated acts list."""
    _STATE["result"] = copy.deepcopy(result)


def _build_vault():
    """Derive the vault + keys from env (deterministic, stable across runs)."""
    coord_addr = os.getenv("COORDINATOR_ADDRESS")
    coord_key_hex = os.getenv("COORDINATOR_PRIVATE_KEY")
    if not coord_addr or not coord_key_hex:
        raise RuntimeError("COORDINATOR_ADDRESS / COORDINATOR_PRIVATE_KEY not configured")
    seed = os.getenv("AGENT_MASTER_SEED") or coord_key_hex
    agent_key = derive_key(seed, "vault-agent")
    owner_key = derive_key(seed, "vault-owner")
    agent = Keypair.from_private_key(agent_key)
    owner = Keypair.from_private_key(owner_key)
    beneficiary_spk = pay_to_address_script(Address(coord_addr))
    vault = derive_vault(agent.xonly_public_key, owner.xonly_public_key, beneficiary_spk, CAP, NETWORK_TYPE)
    return vault, agent_key, owner_key, PrivateKey(coord_key_hex), coord_addr, beneficiary_spk


def vault_info() -> dict:
    """Static vault info for the UI (no network calls)."""
    try:
        vault, _, _, _, coord_addr, _ = _build_vault()
        return {
            "configured": True,
            "vault_address": vault.address_str(),
            "vault_explorer": f"{ADDR_EXPLORER}/{vault.address_str()}",
            "cap_kas": CAP / KAS,
            "beneficiary": coord_addr,
            "network": NETWORK_ID,
        }
    except Exception as e:
        return {"configured": False, "reason": str(e), "network": NETWORK_ID}


def get_status() -> dict:
    """Vault info + last proof result + whether a run is in progress."""
    return {**vault_info(), "running": _STATE["running"], "result": _STATE["result"],
            "error": _STATE["error"], "started_at": _STATE["started_at"]}


def _act(n, label, kind, expect, amount_kas):
    return {"n": n, "label": label, "kind": kind, "expect": expect, "amount_kas": amount_kas,
            "outcome": "pending", "txid": None, "explorer": None}


async def run_proof() -> dict:
    """Run the full 4-act covenant proof live on TN10. Returns a structured result.

    Everything (setup + I/O) runs inside one try/finally so `running` is ALWAYS
    reset — a failure in _build_vault()/connect() can never brick the feature.
    """
    if _STATE["running"]:
        return {"status": "already_running"}
    _STATE.update(running=True, error=None, started_at=time.time(), result=None)
    client = None
    result: "dict | None" = None
    try:
        vault, agent_key, owner_key, coord_key, coord_addr, beneficiary_spk = _build_vault()
        coord_spk = beneficiary_spk
        wrong_spk = pay_to_address_script(Keypair.random().to_address(NETWORK_TYPE))

        result = {
            "vault_address": vault.address_str(),
            "vault_explorer": f"{ADDR_EXPLORER}/{vault.address_str()}",
            "cap_kas": CAP / KAS,
            "beneficiary": coord_addr,
            "network": NETWORK_ID,
            "funding_txid": None,
            "funding_explorer": None,
            "acts": [
                _act(1, f"AUTO pay beneficiary {FUND_AMOUNTS[0]/KAS:g} KAS (≤ cap)", "auto", "accept", FUND_AMOUNTS[0] / KAS),
                _act(2, f"AUTO pay beneficiary {FUND_AMOUNTS[2]/KAS:g} KAS (> cap)", "auto", "block", FUND_AMOUNTS[2] / KAS),
                _act(3, f"AUTO pay WRONG address {FUND_AMOUNTS[1]/KAS:g} KAS", "auto", "block", FUND_AMOUNTS[1] / KAS),
                _act(4, f"MANUAL co-sign {FUND_AMOUNTS[2]/KAS:g} KAS (agent + owner)", "manual", "accept", FUND_AMOUNTS[2] / KAS),
            ],
            "status": "running",
            "ran_at": time.time(),
        }
        _publish(result)

        client = RpcClient(resolver=Resolver(), network_id=NETWORK_ID)
        await client.connect()

        def _auto(tx):
            return auto_unlock_script(vault, create_input_signature(tx, 0, agent_key))

        def _manual(tx):
            owner_sig = create_input_signature(tx, 0, owner_key)
            agent_sig = create_input_signature(tx, 0, agent_key)
            return manual_unlock_script(vault, owner_sig, agent_sig)

        async def do_act(act, utxo, to_spk, sign_fn, sig_ops):
            try:
                txid, _pay = await spend_vault(client, NETWORK_ID, vault, utxo, to_spk, sign_fn, sig_ops)
                act["txid"] = txid
                act["explorer"] = link(txid)
                act["outcome"] = "accepted" if act["expect"] == "accept" else "unexpected_accept"
            except Exception as e:
                act["outcome"] = "blocked" if act["expect"] == "block" else "unexpected_fail"
                act["error"] = str(e)[:200]

        existing = (await client.get_utxos_by_addresses({"addresses": [vault.address_str()]})).get("entries", [])
        if len(existing) >= len(FUND_AMOUNTS):
            entries = existing
        else:
            txid = await fund_vault(client, coord_key, coord_addr, vault, FUND_AMOUNTS)
            result["funding_txid"] = txid
            result["funding_explorer"] = link(txid)
            _publish(result)
            entries = await wait_for_utxos(client, vault.address_str(), want=len(FUND_AMOUNTS))

        work = list(entries)
        large = _take(work, FUND_AMOUNTS[2])
        await do_act(result["acts"][0], _take(work, FUND_AMOUNTS[0]), coord_spk, _auto, 1)
        _publish(result)
        await do_act(result["acts"][1], large, coord_spk, _auto, 1)
        _publish(result)
        await do_act(result["acts"][2], _take(work, FUND_AMOUNTS[1]), wrong_spk, _auto, 1)
        _publish(result)
        await do_act(result["acts"][3], large, coord_spk, _manual, 2)
        result["status"] = "complete"
        return result
    except Exception as e:
        _STATE["error"] = str(e)
        if result is None:
            result = {"network": NETWORK_ID, "acts": []}
        result["status"] = "error"
        result["error"] = str(e)
        return result
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        _STATE["running"] = False
        if result is not None:
            _publish(result)


def _on_run_done(task: "asyncio.Task") -> None:
    _STATE["running"] = False   # belt-and-suspenders
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        _STATE["error"] = str(exc)
        print(f"⚠️ covenant proof run failed: {exc!r}")


def run_proof_background() -> dict:
    """Kick off a proof run; returns immediately. Keeps a strong task reference so
    the run can't be garbage-collected, and logs any escaped exception."""
    global _TASK
    if _STATE["running"] or (_TASK is not None and not _TASK.done()):
        return {"status": "already_running"}
    _TASK = asyncio.create_task(run_proof())
    _TASK.add_done_callback(_on_run_done)
    return {"status": "started"}
