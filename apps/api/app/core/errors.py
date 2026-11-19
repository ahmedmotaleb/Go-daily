"""Domain errors and their HTTP representation.

Every error response has the same shape so clients can rely on it:

    {"error": {"code": "not_found", "message": "...", "details": {...}}}

`message` is Arabic (primary UI language); `code` is stable and
machine-readable.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import monitoring
from app.core.logging import security_headers

logger = logging.getLogger(__name__)


class DomainError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    default_message: str = "طلب غير صالح"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code:
            self.code = code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    default_message = "العنصر غير موجود"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    default_message = "يتعارض الطلب مع بيانات موجودة"


class ValidationFailed(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"
    default_message = "البيانات المدخلة غير صحيحة"


class AuthenticationError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"
    default_message = "يجب تسجيل الدخول"


class PermissionDenied(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    default_message = "ليس لديك صلاحية لتنفيذ هذا الإجراء"


class TooManyRequests(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_requests"
    default_message = "محاولات كثيرة، حاول مرة أخرى لاحقًا"


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"error": body}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "loc": [str(p) for p in err.get("loc", ())],
                "msg": arabic_message(err),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=jsonable_encoder(
                _error_body("validation_error", "البيانات المدخلة غير صحيحة", {"fields": fields})
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 401: "not_authenticated"}.get(
            exc.status_code, "http_error"
        )
        message = exc.detail if isinstance(exc.detail, str) else "خطأ في الطلب"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals to clients; details go to the logs only.
        rid = request.scope.get("godaily.request_id")
        logger.exception("unhandled_error", extra={"path": request.url.path, "request_id": rid})
        monitoring.capture_exception(exc, component="api", path=request.url.path, request_id=rid)
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", "حدث خطأ غير متوقع"),
        )
        if rid:
            # Lets support find the log line from what the user sees.
            response.headers["X-Request-ID"] = rid
        security_headers(response)
        return response


# Pydantic's built-in messages are English; the admin shows them next to fields.
_ARABIC: dict[str, str] = {
    "missing": "هذا الحقل مطلوب",
    "greater_than": "يجب أن تكون القيمة أكبر من {gt}",
    "greater_than_equal": "يجب ألا تقل القيمة عن {ge}",
    "less_than": "يجب أن تكون القيمة أقل من {lt}",
    "less_than_equal": "يجب ألا تزيد القيمة عن {le}",
    "decimal_max_places": "عدد الخانات العشرية أكثر من {decimal_places}",
    "decimal_max_digits": "الرقم أطول من المسموح",
    "decimal_parsing": "أدخل رقمًا صحيحًا",
    "int_parsing": "أدخل رقمًا صحيحًا",
    "int_from_float": "أدخل رقمًا صحيحًا بدون كسور",
    "float_parsing": "أدخل رقمًا",
    "string_too_short": "النص أقصر من المطلوب",
    "string_too_long": "النص أطول من {max_length} حرف",
    "string_pattern_mismatch": "الصيغة غير صحيحة",
    "date_parsing": "تاريخ غير صحيح",
    "date_from_datetime_parsing": "تاريخ غير صحيح",
    "datetime_parsing": "تاريخ ووقت غير صحيحين",
    "timezone_aware": "الوقت يجب أن يتضمن المنطقة الزمنية",
    "uuid_parsing": "معرّف غير صحيح",
    "enum": "اختر قيمة من القائمة",
    "literal_error": "اختر قيمة من القائمة",
    "bool_parsing": "قيمة غير صحيحة",
}


def arabic_message(err: Any) -> str:
    """The Arabic message for a Pydantic error; our own messages are kept as written."""
    template = _ARABIC.get(str(err.get("type")))
    if template is None:
        return str(err.get("msg", ""))
    try:
        return template.format(**(err.get("ctx") or {}))
    except (KeyError, IndexError, ValueError):
        return template.split("{")[0].strip()


def field_error(field: str, message: str, *, code: str = "validation_error") -> ValidationFailed:
    """A 422 tied to one input field (shown next to it in the admin web)."""
    return ValidationFailed(
        message, code=code, details={"fields": [{"loc": [field], "msg": message, "type": code}]}
    )
