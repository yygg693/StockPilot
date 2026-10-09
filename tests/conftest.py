"""Pytest fixtures for StockPilot test suite."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("PYTHONPATH", str(PROJECT_ROOT))
