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
    
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", os.getenv("API_PORT", 8000)))

    
    print("=" * 60)
    print("🐝 KaspaSwarm - Decentralized AI Agent Coordination")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

