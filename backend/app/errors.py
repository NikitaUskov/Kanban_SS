"""Consistent application errors and FastAPI exception handlers."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("kanban.errors")


class AppError(Exception):
    """A safe API error with an application code and optional details."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _payload(request: Request, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "requestId": _request_id(request),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that never expose stack traces or secrets."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request.state.error_type = exc.code
        headers = None
        if exc.status_code == 429 and "retryAfterSeconds" in exc.details:
            headers = {"Retry-After": str(exc.details["retryAfterSeconds"])}
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request.state.error_type = "VALIDATION_ERROR"
        safe_errors = [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_payload(
                request,
                "VALIDATION_ERROR",
                "Проверьте заполнение полей",
                {"fields": safe_errors},
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request.state.error_type = f"HTTP_{exc.status_code}"
        message = exc.detail if isinstance(exc.detail, str) else "Ошибка HTTP-запроса"
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, f"HTTP_{exc.status_code}", message),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request.state.error_type = type(exc).__name__
        logger.exception(
            "Unhandled error request_id=%s method=%s path=%s error_type=%s",
            _request_id(request),
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=_payload(
                request,
                "INTERNAL_ERROR",
                "Внутренняя ошибка сервера. Повторите запрос позже",
            ),
        )
