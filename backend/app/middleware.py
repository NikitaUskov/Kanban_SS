"""Request ID, timing and safe request logging middleware."""

import logging
import time
from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("kanban.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID and record safe technical request metadata."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        try:
            request_id = str(UUID(supplied)) if supplied else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        status = 500
        error_type = "-"
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            error_type = getattr(request.state, "error_type", error_type)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%s error_type=%s",
                request_id,
                request.method,
                request.url.path,
                status,
                duration_ms,
                error_type,
            )
            if "response" in locals():
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Server-Time"] = (
                    __import__("datetime")
                    .datetime.now(__import__("datetime").UTC)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
