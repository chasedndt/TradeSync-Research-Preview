"""Server errors answer with a trace id, never with the exception's own text (finding L4).

Nineteen handlers answered HTTP 500 with ``detail=str(e)``: a database error, an
httpx error naming an internal address, whatever the exception said. The handler
installed here replaces such a detail with a generic message and a trace id, and
logs the exception's type under the same id, so the operator can find the
failure without the caller learning anything from it.

It acts on an HTTP 500 whose detail is exactly the text of the exception being
handled when it was raised (``HTTPException.__context__``). A composed detail,
and every 4xx detail (the validation messages callers rely on), passes
unchanged. A route that reports an error inside its response body instead quotes
``reference(exc, where)``, which logs the same way.

The trace id is the request's own (``TraceIdMiddleware`` in ``app.main``, which
also returns it as ``X-Trace-Id``) when that is a plain token; otherwise a new one.
"""

from __future__ import annotations

import logging
import re
import uuid

from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("state-api")

GENERIC_DETAIL = "Internal error. The state-api log records its type under this trace id."
_PLAIN_TRACE = re.compile(r"[A-Za-z0-9._-]{1,64}")


def trace_id_for(request: Request | None) -> str:
    """The request's trace id when it is a plain token, otherwise a new one."""
    candidate = getattr(request.state, "trace_id", None) if request is not None else None
    return candidate if isinstance(candidate, str) and _PLAIN_TRACE.fullmatch(candidate) else uuid.uuid4().hex


def reference(exc: BaseException, where: str, trace_id: str | None = None) -> str:
    """Log an exception's type, never its text, and return the id to quote in its place."""
    trace_id = trace_id or uuid.uuid4().hex
    logger.error(f"{where} failed: {type(exc).__name__}", extra={"trace_id": trace_id})
    return trace_id


def raw_exception(exc: StarletteHTTPException) -> BaseException | None:
    """The exception whose text an HTTP 500 detail repeats verbatim, or None."""
    context = exc.__cause__ or exc.__context__
    if exc.status_code == 500 and context is not None and exc.detail == str(context):
        return context
    return None


async def sanitising_http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    context = raw_exception(exc)
    if context is None:
        return await http_exception_handler(request, exc)
    trace_id = reference(context, f"{request.method} {request.url.path}", trace_id_for(request))
    return JSONResponse({"detail": GENERIC_DETAIL, "trace_id": trace_id}, status_code=500, headers=exc.headers)


def install(app) -> None:
    """Answer every HTTPException through the sanitising handler."""
    app.add_exception_handler(StarletteHTTPException, sanitising_http_exception_handler)
