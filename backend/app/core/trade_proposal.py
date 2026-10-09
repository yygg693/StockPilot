"""Trade proposal store - two-phase confirmation for AI auto-trading.

Phase 1: AI generates proposals (no execution)
Phase 2: User confirms proposals, then trades execute

Proposals are ephemeral (in-memory with TTL). They expire after 5 minutes
to prevent stale signals from being executed.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from backend.app.core.logging import get_logger

logger = get_logger("trade.proposal")

_PROPOSAL_TTL = 300  # 5 minutes
_proposals: dict[str, dict] = {}


@dataclass
class TradeProposal:
    proposal_id: str
    created_at: float
    expires_at: float
    sells: list[dict] = field(default_factory=list)
    buys: list[dict] = field(default_factory=list)
    signals_summary: list[dict] = field(default_factory=list)
    commentary: str = ""


def create_proposal(
    sells: list[dict],
    buys: list[dict],
    signals_summary: list[dict] | None = None,
    commentary: str = "",
) -> dict:
    """Create a trade proposal and return it for user confirmation.

    Returns a dict with proposal_id, expires_at, and the proposed trades.
    """
    proposal_id = uuid.uuid4().hex[:12]
    now = time.time()
    expires_at = now + _PROPOSAL_TTL

    proposal = {
        "proposal_id": proposal_id,
        "created_at": now,
        "expires_at": expires_at,
        "sells": sells,
        "buys": buys,
        "signals_summary": signals_summary or [],
        "commentary": commentary,
    }
    _proposals[proposal_id] = proposal

    # Prune expired proposals
    _prune_expired()

    logger.info("proposal.created", proposal_id=proposal_id, sells=len(sells), buys=len(buys))
    return proposal


def get_proposal(proposal_id: str) -> dict | None:
    """Get a proposal by ID. Returns None if not found or expired."""
    _prune_expired()
    p = _proposals.get(proposal_id)
    if not p:
        return None
    if time.time() > p["expires_at"]:
        del _proposals[proposal_id]
        return None
    return p


def consume_proposal(proposal_id: str) -> dict | None:
    """Get and remove a proposal (one-time use). Returns None if not found/expired."""
    p = get_proposal(proposal_id)
    if p:
        del _proposals[proposal_id]
        logger.info("proposal.consumed", proposal_id=proposal_id)
    return p


def _prune_expired() -> None:
    """Remove expired proposals."""
    now = time.time()
    expired = [pid for pid, p in _proposals.items() if now > p["expires_at"]]
    for pid in expired:
        del _proposals[pid]
    if expired:
        logger.info("proposal.pruned", count=len(expired))


def format_proposal_response(proposal: dict) -> dict:
    """Format proposal for API response (user review)."""
    total = len(proposal["sells"]) + len(proposal["buys"])
    return {
        "data": {
            "proposal_id": proposal["proposal_id"],
            "expires_at": int(proposal["expires_at"]),
            "requires_confirmation": True,
            "summary": {
                "total_trades": total,
                "sells": len(proposal["sells"]),
                "buys": len(proposal["buys"]),
            },
            "proposed_sells": proposal["sells"],
            "proposed_buys": proposal["buys"],
            "signals": proposal.get("signals_summary", []),
            "commentary": proposal.get("commentary", ""),
            "message": f"AI 生成 {total} 笔交易提案，请确认后执行（5分钟内有效）",
        }
    }
