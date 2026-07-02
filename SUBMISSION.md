# KaspaSwarm — a trustless, real-time agent economy on Kaspa

> **Submission — UK AI Agent Hackathon EP5 (Imperial College London) · Kaspa bounty**
>
> _Fill in before submitting:_ Demo video → `TODO`, Live demo → `TODO (Vercel)`,
> Repo → `https://github.com/Nihal-Pandey-2302/kaspaswarm`, Team → `TODO`.

## One-liner

KaspaSwarm turns Kaspa into a **real-time coordination-and-settlement layer** where
autonomous AI agents hire each other, do real work, get paid, and are **governed by
on-chain covenants** — no broker, no server in the middle, every step a real Kaspa
transaction.

## The problem

When one AI agent needs to hire another, coordination today runs through a
**centralized broker** that decides who works and who gets paid — a single point of
trust and failure. And once agents hold funds, nothing stops a compromised or
hallucinating agent from draining its wallet.

## What we built

A multi-agent swarm where **Kaspa is simultaneously the message bus and the payment
rail**:

- **Real on-chain coordination (testnet-10).** Every task, bid, assignment, and
  solution is a real Kaspa transaction whose *payload* carries the message
  (`KSWARM1:` prefix). Delivery is gated on real block inclusion via the official
  Kaspa SDK + Resolver — turn the chain off and the swarm stops.
- **LLM-powered agents.** Solvers do real AI work (any OpenAI-compatible endpoint);
  a separate LLM **verifier-agent** grades the answer before payment.
- **A real economy.** Reputation-weighted reverse auction (`√reputation / bid`) for
  assignment + in-protocol escrow (lock → release / slash / cancel).
- **🔌 MCP-hireable.** Any external agent (Claude Desktop, Cursor) can hire the
  swarm as an MCP tool: post a task → the swarm bids/solves/verifies → settles on
  Kaspa → returns the answer. *An agent hiring agents, settled on a fast L1.*
- **🛡️ On-chain covenant governance (KIP-10).** An **Agent Treasury Vault** whose
  spending policy is enforced by Kaspa consensus: the agent may auto-pay a *pinned*
  beneficiary up to a *per-tx cap*; anything larger or off-policy is **rejected by
  the network** and needs a human co-signer. The same machinery backs an opt-in
  **per-task escrow covenant** (reward can only settle to the solver or refund to
  the coordinator).

## Why Kaspa

This is only possible because Kaspa's blockDAG confirms **~10 blocks/second** — fast
enough to bid → assign → verify → settle in real time, which Bitcoin (10 min) or
Ethereum (12 s) cannot. And Kaspa's **KIP-10 introspection opcodes (Toccata)** let
us enforce agent spending policy *on-chain* — the differentiator that turns "trust
the agent" into "the chain won't let it."

## Proof it's real (validated live on testnet-10)

Covenant governance — a 4-act proof (cap = 2 KAS), viewable on
[tn10.kaspa.stream](https://tn10.kaspa.stream):

| Act | Policy check | Result |
| --- | --- | --- |
| AUTO pay beneficiary 1 KAS (≤ cap) | in-policy | ✅ ACCEPTED — [tx](https://tn10.kaspa.stream/transactions/76dd4b96c0f8f71d243e3cbdb5393c12ed72b0af92cef8efdf1b4b7975337c9f) |
| AUTO pay beneficiary 3 KAS (> cap) | over cap | ⛔ BLOCKED by consensus |
| AUTO pay wrong address | recipient ≠ pinned | ⛔ BLOCKED by consensus |
| MANUAL co-sign 3 KAS | human approves | ✅ ACCEPTED — [tx](https://tn10.kaspa.stream/transactions/2697d12230555eb67ce472e3f4ceb3cb9c46e9098b9a827d3fa352f0d63b72e7) |

Per-task escrow covenant — lock → settle-to-solver and lock → refund-to-coordinator,
both real on-chain (`python -m backend.escrow_demo`).

Stateful **rolling-allowance covenant (v2)** — authored in **SilverScript**, compiled
with the real `silverc` toolchain to Kaspa script, funded on TN10, and enforced live:
an unauthorised reclaim is **rejected by consensus** while the owner's reclaim is
**accepted** ([tx](https://tn10.kaspa.stream/transactions/b08d95a0d8c703523031a7216c09b8bd123d38628e604839af875a4970d8d22e)) — `python -m backend.rolling_demo`.

## What makes it credible

- **One-command run:** `docker compose up` → full app, mock mode (no wallet/funds).
- **One-click hosting:** `render.yaml` blueprint (backend, mock, safe 24/7).
- **Fund-safe by design:** live mode pauses auto task-generation when no dashboard
  is connected, so an idle deployment never burns funds.
- **Tested + CI:** offline test suite (covenant determinism, unique per-task escrow
  addresses, auction, escrow state machine, payload codec) runs in GitHub Actions.
- **Honest scope:** covenants are a **testnet-10 PoC** (Toccata/SilverScript are
  experimental); the cap is per-transaction (not a rolling budget); AUTO is
  single-output by design so large balances require the human co-sign branch.

## How to try it

```bash
docker compose up --build      # http://localhost:8080 (mock — no keys/funds)
```

For live testnet-10, add a `.env` (see `.env.example`) with a funded coordinator;
the dashboard header shows **🟢 LIVE · TN10** vs **🟡 SIMULATION**.

## Prior work & eligibility

KaspaSwarm began at **Kaspathon 2026** (4th place Main Track; winner Real-Time Data;
winner Best Real-World Application). Reuse with significant new work was confirmed by
Kaspa core (IzioDev). New for this event: SDK+Resolver transport, real LLM agents +
verifier, the reputation-auction + escrow economy, the MCP server, and — the
headline — **real KIP-10 covenant governance + per-task escrow covenants**, plus
Docker/Render deploy, the idle fund-guard, tests/CI, and refreshed docs.

## Tech

Python (FastAPI, `kaspa==2.0.1` SDK, KIP-10 `ScriptBuilder`), React + Three.js,
FastMCP, WebSocket streaming, testnet-10 via the community-node Resolver.
