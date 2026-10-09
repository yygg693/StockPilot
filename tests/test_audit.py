"""Tests for backend.app.core.audit — audit logging."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.core.audit import extract_request_info, get_audit_logs, log_audit


class TestExtractRequestInfo:
    def test_with_forwarded_for(self):
        request = MagicMock()
        request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8", "user-agent": "TestAgent"}
        request.client = MagicMock(host="127.0.0.1")
        info = extract_request_info(request)
        assert info["ip_address"] == "1.2.3.4"
        assert info["user_agent"] == "TestAgent"

    def test_without_forwarded_for(self):
        request = MagicMock()
        request.headers = {"user-agent": "Mozilla"}
        request.client = MagicMock(host="192.168.1.1")
        info = extract_request_info(request)
        assert info["ip_address"] == "192.168.1.1"
        assert info["user_agent"] == "Mozilla"

    def test_no_client(self):
        request = MagicMock()
        request.headers = {}
        request.client = None
        info = extract_request_info(request)
        assert info["ip_address"] == "unknown"
        assert info["user_agent"] == ""


class TestLogAudit:
    @pytest.mark.asyncio
    async def test_log_audit_calls_db(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("backend.app.core.audit.get_db", return_value=mock_db):
            await log_audit(
                action="trade.buy",
                target="sh600519",
                detail={"amount": 50000},
                user_id="user1",
            )

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_audit_never_raises(self):
        """Audit logging must never break business operations."""
        with patch("backend.app.core.audit.get_db", side_effect=Exception("DB down")):
            # Should not raise
            await log_audit(action="test", target="x")


class TestGetAuditLogs:
    @pytest.mark.asyncio
    async def test_get_logs_without_filter(self):
        mock_cursor = AsyncMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {"id": 1, "action": "test", "detail": "{}"}.get(key, "")
        mock_cursor.fetchall = AsyncMock(return_value=[])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_cursor)

        with patch("backend.app.core.audit.get_db", return_value=mock_db):
            logs = await get_audit_logs(limit=10, offset=0)

        assert isinstance(logs, list)
        mock_db.execute.assert_called_once()
