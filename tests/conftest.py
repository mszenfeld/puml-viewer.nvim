"""Test configuration for puml-viewer server tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path so we can import server.server
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
