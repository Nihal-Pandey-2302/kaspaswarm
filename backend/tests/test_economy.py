"""Offline tests for the economy: reputation-weighted auction + escrow lifecycle."""
import asyncio

from backend.kcore.covenant import InProtocolEscrow
from backend.swarm.task_types import Task, TaskType


def _task():
    return Task(1, "t", TaskType.PRIME_FINDING, {"target": 100}, 100_000_000, 0.0, "coord")


def test_auction_lower_bid_wins_at_equal_reputation():
    t = _task()
    t.add_bid("cheap", 40_000_000, reputation=100.0)
    t.add_bid("pricey", 90_000_000, reputation=100.0)
    assert t.get_best_bid()["agent"] == "cheap"


def test_auction_reputation_breaks_close_bids():
    t = _task()
    # near-identical price, but one agent has far higher reputation -> it wins
    t.add_bid("newbie", 50_000_000, reputation=1.0)
    t.add_bid("trusted", 52_000_000, reputation=400.0)
    assert t.get_best_bid()["agent"] == "trusted"


def test_add_bid_keeps_one_bid_per_agent():
    t = _task()
    t.add_bid("a", 80_000_000, reputation=100.0)
    t.add_bid("a", 40_000_000, reputation=100.0)  # same agent re-bids lower
    agents = [b["agent"] for b in t.bids]
    assert agents.count("a") == 1


def test_escrow_lifecycle_release():
    esc = InProtocolEscrow()

    async def run():
        await esc.lock(1, "coord", "solver", 100, 50)
        assert await esc.release(1) is True
        # releasing again is a no-op (idempotent) — can't double-pay
        assert await esc.release(1) is False
        # can't slash an already-released escrow
        assert await esc.slash(1) is False

    asyncio.run(run())
    s = esc.stats()
    assert s["locked"] == 1 and s["released"] == 1 and s["slashed"] == 0
    assert s["kas_released"] == 150  # reward + stake


def test_escrow_lifecycle_slash():
    esc = InProtocolEscrow()

    async def run():
        await esc.lock(2, "coord", "solver", 200, 100)
        assert await esc.slash(2) is True
        assert await esc.release(2) is False  # can't pay after slash

    asyncio.run(run())
    s = esc.stats()
    assert s["slashed"] == 1 and s["kas_slashed"] == 100  # only the stake is slashed


def test_escrow_cancel_returns_stake_no_slash():
    esc = InProtocolEscrow()

    async def run():
        await esc.lock(3, "coord", "solver", 200, 100)
        assert await esc.cancel(3) is True

    asyncio.run(run())
    s = esc.stats()
    assert s["cancelled"] == 1 and s["slashed"] == 0


def test_release_unknown_task_is_false():
    esc = InProtocolEscrow()
    assert asyncio.run(esc.release(999)) is False
