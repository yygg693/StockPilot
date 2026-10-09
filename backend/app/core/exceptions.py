"""Unified business exception hierarchy + FastAPI handler."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception."""
    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "Internal server error", detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppException):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, message: str = "Resource not found", detail: str | None = None):
        super().__init__(message, detail)


class ValidationError(AppException):
    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, message: str = "Validation failed", detail: str | None = None):
        super().__init__(message, detail)


class InsufficientPositionError(AppException):
    status_code = 400
    code = "INSUFFICIENT_POSITION"

    def __init__(self, message: str = "Insufficient position", detail: str | None = None):
        super().__init__(message, detail)


class InsufficientCashError(AppException):
    status_code = 400
    code = "INSUFFICIENT_CASH"

    def __init__(self, message: str = "Insufficient cash balance", detail: str | None = None):
        super().__init__(message, detail)


class PositionNotFoundError(AppException):
    status_code = 404
    code = "POSITION_NOT_FOUND"

    def __init__(self, message: str = "No position found", detail: str | None = None):
        super().__init__(message, detail)


class AIServiceError(AppException):
    status_code = 502
    code = "AI_SERVICE_ERROR"

    def __init__(self, message: str = "AI service unavailable", detail: str | None = None):
        super().__init__(message, detail)


class DataSourceError(AppException):
    status_code = 502
    code = "DATA_SOURCE_ERROR"

    def __init__(self, message: str = "Data source unavailable", detail: str | None = None):
        super().__init__(message, detail)


class AuthError(AppException):
    status_code = 401
    code = "AUTH_ERROR"

    def __init__(self, message: str = "Authentication required", detail: str | None = None):
        super().__init__(message, detail)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "message": exc.message,
            **({"detail": exc.detail} if exc.detail else {}),
        },
    )
