# Deployment Guide 🚀

KaspaSwarm consists of two distinct components that need to be deployed separately:

1.  **Frontend**: A React application (deployed to Vercel/Netlify)
2.  **Backend**: A Python agent swarm (deployed to Render/Railway/VPS)

> **ℹ️ Note on Kaspa connectivity**
> The default `sdk` transport connects to `testnet-10` through the **community-node
> Resolver** — you do **not** need to run your own `kaspad` node. The backend can run
> on any persistent host (Render/Railway/VPS); only a funded coordinator address is
> required. Running your own node is optional and only needed for the legacy
> `handrolled` transport (`KASPA_TRANSPORT=handrolled` + `KASPA_WS_URL`).

---

## 🏗️ Architecture Overview

| Component      | Type               | Recommended Host           | Why?                                                               |
| -------------- | ------------------ | -------------------------- | ------------------------------------------------------------------ |
| **Frontend**   | Static Site / SPA  | **Vercel** / Netlify       | Free, fast global CDN, connects to backend via WebSocket           |
| **Backend**    | Persistent Process | **Render** / Railway / VPS | Needs to run 24/7 (Long-running process), NOT serverless           |
| **Kaspa Node** | Blockchain Node    | **Optional**               | Not needed with the default SDK+Resolver transport; only for `handrolled`. |

---

## 1. Backend Deployment (The Brain) 🧠

The backend runs the agent swarm. It **cannot** be deployed on Vercel Serverless functions because it needs to maintain a persistent WebSocket server and continuous agent loops.

### Option A: Render / Railway (Easiest Cloud) — Recommended

The default SDK+Resolver transport means **no Kaspa node is required** — cloud hosting is now the simplest path.

1.  Push your code to GitHub.
2.  Create a **New Web Service** on Render/Railway.
3.  Connect your repository.
4.  **Settings**:
    - **Root Directory**: `backend`
    - **Runtime**: Python 3
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `gunicorn -k uvicorn.workers.UvicornWorker main:app` (or `python -m main`)
5.  **Environment Variables**:
    - `MOCK_MODE`: `false` (for live) or `true` (for demo)
    - `KASPA_NETWORK`: `testnet-10`
    - `KASPA_TRANSPORT`: `sdk` (default; connects via Resolver — no node needed)
    - `COORDINATOR_ADDRESS` / `COORDINATOR_PRIVATE_KEY`: a funded testnet keypair
    - `AGENT_MASTER_SEED`: any stable secret (derives fundable agent addresses)
    - `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`: *(optional)* for real AI tasks
    - `PORT`: `8000`

> ⚠️ Set secrets in the host's env var UI — never commit real keys. Rotate them after the event.

### Option B: VPS with your own node (legacy `handrolled` transport) 🛡️

_Only needed if you specifically want to run against your own `kaspad` instead of the Resolver._

1.  Rent a VPS (Ubuntu 22.04) from Hetzner/DigitalOcean.
2.  Install `kaspad` (see [Running a Node](https://github.com/kaspanet/rusty-kaspa)).
    ```bash
    ./kaspad --testnet --netsuffix=10 --rpclisten-json=default --utxoindex
    ```
    Then set `KASPA_TRANSPORT=handrolled` and `KASPA_WS_URL=ws://127.0.0.1:18210`.
3.  Clone the repo and run the swarm:

    ```bash
    git clone https://github.com/Nihal-Pandey-2302/kaspaswarm.git
    cd kaspaswarm/backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

    # Run in background (e.g., using tmux or systemd)
    python -m main
    ```

---

## 2. Frontend Deployment (The Interface) 🎨

The frontend can be deployed for free on Vercel.

1.  Push your code to GitHub.
2.  Go to [Vercel](https://vercel.com) and **Add New Project**.
3.  Import `kaspaswarm`.
4.  **Settings**:
    - **Framework Preset**: Vite
    - **Root Directory**: `frontend`
    - **Build Command**: `npm run build`
    - **Output Directory**: `dist`
5.  **Environment Variables**:
    - `VITE_API_URL`: `wss://your-backend-url.onrender.com/ws` (The URL of your deployed backend)
    - _Note: If testing locally, this defaults to `ws://localhost:8000/ws`_

---

## 🔗 Connecting Them

1.  **Deploy Backend first**. Get its comprehensive URL (e.g., `https://kaspaswarm-api.onrender.com`).
2.  **Deploy Frontend**, setting the `VITE_API_URL` environment variable to your backend's WebSocket URL (replace `https://` with `wss://`).
    - Example: `VITE_API_URL=wss://kaspaswarm-api.onrender.com/ws`

## ✅ Verification

Open your Vercel URL. You should see the 3D swarm visualization.

- If it says "Connecting...", check the Browser Console (F12).
- Ensure `VITE_API_URL` is set correctly without trailing slashes.
- Ensure the Backend is running and not crashing.
