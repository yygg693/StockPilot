"""Risk management module — delegated to core/risk.py (unified engine).

This module is kept for backward compatibility. The canonical implementation
lives in backend.app.core.risk.
"""
from __future__ import annotations

# Re-export unified risk types and singleton
from backend.app.core.risk import (
    RiskCheckResult,
    RiskLimits,
    RiskManager,
    configure_risk,
    get_risk_manager,
)

__all__ = [
    "RiskLimits",
    "RiskCheckResult",
    "RiskManager",
    "get_risk_manager",
    "configure_risk",
]
