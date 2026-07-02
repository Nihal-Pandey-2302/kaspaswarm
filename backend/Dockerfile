# KaspaSwarm backend — FastAPI + agent swarm + Kaspa SDK.
# Build context is the repo root (see docker-compose.yml) so `backend` is a package.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend

# Safe defaults: MOCK mode = no real transactions, no wallet/keys required.
ENV PYTHONUNBUFFERED=1 \
    MOCK_MODE=true \
    KASPA_NETWORK=testnet-10 \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.api.websocket:app", "--host", "0.0.0.0", "--port", "8000"]
