"""
Main entry point for KaspaSwarm backend.

Run with: python main.py (from backend directory)
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env', override=True)

# Import and run the API server
if __name__ == "__main__":
    from backend.api.websocket import app
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    # Render and other providers use "PORT", our config uses "API_PORT"
    port_env = os.getenv("PORT") or os.getenv("API_PORT")
    port = int(port_env) if port_env else 8000
    
    print("=" * 60)
    print("🐝 KaspaSwarm - Decentralized AI Agent Coordination")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

