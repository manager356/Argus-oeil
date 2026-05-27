import os
import sys
from pathlib import Path

# Stub env vars before `loeil.config` is imported by any test module.
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("STAFF_CHANNEL_ID", "111111111111111111")

# Make the project root importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
