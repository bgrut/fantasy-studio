"""
Top-level entry: render a scene from an English prompt.

This is the script your product / users / CI calls. Wraps the orchestrator
CLI with sane defaults and ensures the backend root is on sys.path.

Examples:
    python scripts/render_from_prompt.py "a red metallic cube on a checkered floor at sunset"
    python scripts/render_from_prompt.py --model llama3.1:8b "low-poly castle on a hill"
    python scripts/render_from_prompt.py --dry-run "test prompt"
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.orchestrator.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
