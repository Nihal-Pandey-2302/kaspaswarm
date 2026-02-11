# Deployment Guide 🚀

KaspaSwarm consists of two distinct components that need to be deployed separately:

1.  **Frontend**: A React application (deployed to Vercel/Netlify)
2.  **Backend**: A Python agent swarm (deployed to Render/Railway/VPS)

> **⚠️ Critical Note on Kaspa Network**
> Since `testnet-10` public infrastructure is currently unstable, you must ensure your backend has access to a working Kaspa node (`kaspad`). The easiest way is to run the backend on a VPS (like DigitalOcean or Hetzner) where you can also run your own `kaspad` node.

---

## 🏗️ Architecture Overview

| Component      | Type               | Recommended Host           | Why?                                                               |
| -------------- | ------------------ | -------------------------- | ------------------------------------------------------------------ |
| **Frontend**   | Static Site / SPA  | **Vercel** / Netlify       | Free, fast global CDN, connects to backend via WebSocket           |
| **Backend**    | Persistent Process | **Render** / Railway / VPS | Needs to run 24/7 (Long-running process), NOT serverless           |
| **Kaspa Node** | Blockchain Node    | **Self-Hosted VPS**        | Needs high bandwidth/storage. Public testnet nodes are unreliable. |

---

## 1. Backend Deployment (The Brain) 🧠

The backend runs the agent swarm. It **cannot** be deployed on Vercel Serverless functions because it needs to maintain a persistent WebSocket server and continuous agent loops.

### Option A: Render / Railway (Easiest Cloud)

_Note: Public Testnet-10 nodes must be accessible for this to work._

1.  Push your code to GitHub.
2.  Create a **New Web Service** on Render/Railway.
3.  Connect your repository.
4.  **Settings**:
    - **Root Directory**: `backend`
    - **Runtime**: Python 3
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `gunicorn -k uvicorn.workers.UvicornWorker main:app` (or `python -m main`)
5.  **Environment Variables**:
    - `KASPA_WS_URL`: `wss://your-node-url` (or public node if available)
    - `MOCK_MODE`: `false` (for live) or `true` (for demo)
    - `PORT`: `8000`

### Option B: VPS (Recommended for Stability) 🛡️

_Best option currently to run your own `kaspad` node alongside the swarm._

1.  Rent a VPS (Ubuntu 22.04) from Hetzner/DigitalOcean.
2.  Install `kaspad` (see [Running a Node](https://github.com/kaspanet/rusty-kaspa)).
    ```bash
    ./kaspad --testnet --netsuffix=10 --rpclisten-json=default --utxoindex
    ```
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
