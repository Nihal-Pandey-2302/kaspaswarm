"""
KaspaSwarm MCP server — lets any external AI agent (Claude Desktop, Cursor, etc.)
HIRE the on-chain swarm: post a task, the swarm's LLM agents bid/solve it and
settle on Kaspa, and the caller retrieves the result.

This makes KaspaSwarm interoperable with the de-facto agent-tooling standard (MCP):
an agent hiring agents, with settlement on a fast L1.

Run (talks to a running KaspaSwarm backend over HTTP):
    python backend/mcp_server.py        # stdio transport

Claude Desktop / Cursor config (mcpServers):
    {
      "kaspaswarm": {
        "command": "/path/backend/venv/bin/python",
        "args": ["/path/backend/mcp_server.py"],
        "env": { "SWARM_API": "http://localhost:8000" }
      }
    }
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

API = os.getenv("SWARM_API", "http://localhost:8000")
SOMPI = 100_000_000

mcp = FastMCP("kaspaswarm")


@mcp.tool()
async def post_ai_task(prompt: str, reward_kas: float = 0.5) -> dict:
    """Hire the KaspaSwarm to perform an AI task. A solver agent bids, an LLM does
    the work, a verifier agent checks it, and the reward settles on Kaspa.

    Args:
        prompt: the task for the agent (e.g. "summarize this", "write a function…").
        reward_kas: reward offered, in KAS (default 0.5).
    Returns: {status, task_id} — pass task_id to get_task_result.
    """
    reward = int(reward_kas * SOMPI)
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{API}/api/control/create-task",
                         params={"reward": reward, "task_type": "ai_task", "prompt": prompt, "source": "mcp"})
        return r.json()


@mcp.tool()
async def get_task_result(task_id: int) -> dict:
    """Get the status and result of a previously posted task."""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{API}/stats")
        for t in (r.json().get("task_history") or []):
            if t.get("task_id") == task_id:
                return {
                    "task_id": task_id,
                    "status": t.get("status"),
                    "answer": t.get("solution"),
                    "solver": t.get("assigned_to"),
                    "reward_sompi": t.get("reward"),
                    "winning_bid_sompi": t.get("bid_amount"),
                }
    return {"task_id": task_id, "status": "not_found"}


@mcp.tool()
async def swarm_status() -> dict:
    """Live summary of the KaspaSwarm: mode, agent counts, task throughput, and
    on-chain (ChainWatcher) stats."""
    async with httpx.AsyncClient(timeout=20) as c:
        d = (await c.get(f"{API}/stats")).json()
        return {
            "mode": d.get("mode"),
            "total_agents": d.get("total_agents"),
            "active_tasks": d.get("active_tasks"),
            "completed_tasks": d.get("completed_tasks"),
            "on_chain": d.get("chain"),
            "escrow": d.get("escrow"),
        }


if __name__ == "__main__":
    mcp.run()
