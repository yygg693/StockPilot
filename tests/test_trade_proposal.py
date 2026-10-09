"""Tests for backend.app.core.trade_proposal — two-phase confirmation."""
from __future__ import annotations

import time

from backend.app.core.trade_proposal import (
    consume_proposal,
    create_proposal,
    format_proposal_response,
    get_proposal,
)


class TestCreateProposal:
    def test_create_returns_proposal_id(self):
        result = create_proposal(sells=[], buys=[{"code": "sh600519", "amount": 10000}])
        assert "proposal_id" in result
        assert len(result["proposal_id"]) == 12

    def test_create_has_expiry(self):
        result = create_proposal(sells=[], buys=[])
        assert "expires_at" in result
        assert result["expires_at"] > time.time()

    def test_create_preserves_trades(self):
        sells = [{"code": "sh600519", "qty": 100}]
        buys = [{"code": "sh000001", "amount": 50000}]
        result = create_proposal(sells=sells, buys=buys)
        assert result["sells"] == sells
        assert result["buys"] == buys

    def test_create_with_optional_fields(self):
        result = create_proposal(
            sells=[],
            buys=[],
            signals_summary=[{"signal": "buy"}],
            commentary="Test commentary",
        )
        assert result["signals_summary"] == [{"signal": "buy"}]
        assert result["commentary"] == "Test commentary"


class TestGetProposal:
    def test_get_existing_proposal(self):
        result = create_proposal(sells=[], buys=[])
        pid = result["proposal_id"]
        fetched = get_proposal(pid)
        assert fetched is not None
        assert fetched["proposal_id"] == pid

    def test_get_nonexistent_proposal(self):
        assert get_proposal("nonexistent123") is None


class TestConsumeProposal:
    def test_consume_returns_and_removes(self):
        result = create_proposal(sells=[], buys=[{"code": "sh600519"}])
        pid = result["proposal_id"]
        consumed = consume_proposal(pid)
        assert consumed is not None
        assert consumed["proposal_id"] == pid
        # Second consume should return None
        assert consume_proposal(pid) is None

    def test_consume_nonexistent(self):
        assert consume_proposal("nonexistent456") is None


class TestFormatProposalResponse:
    def test_format_response_structure(self):
        proposal = create_proposal(
            sells=[{"code": "sh600519"}],
            buys=[{"code": "sh000001"}, {"code": "sh000002"}],
        )
        formatted = format_proposal_response(proposal)
        assert "data" in formatted
        data = formatted["data"]
        assert data["requires_confirmation"] is True
        assert data["summary"]["total_trades"] == 3
        assert data["summary"]["sells"] == 1
        assert data["summary"]["buys"] == 2
        assert "message" in data
