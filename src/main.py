from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.routes import products, skus, invoices, categories, moderation
from src.schemas.errors import ErrorCode, ErrorResponse

app = FastAPI(
    title="NeoMarket B2B Seller Cabinet",
    description="API для управления товарами, SKU и накладными продавцов",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _status_to_code(status_code: int) -> str:
    mapping = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        500: ErrorCode.INTERNAL_ERROR,
    }
    return mapping.get(status_code, ErrorCode.INTERNAL_ERROR)


def _flat_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the single flat error body used by the whole service."""
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return body


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize every HTTPException to the flat ErrorResponse contract."""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        code = str(detail["code"])
        message = str(detail["message"])
        extra = detail.get("details")
        if extra is None and "field" in detail:
            extra = {"field": detail["field"]}
        body = _flat_error(code, message, extra if isinstance(extra, dict) else None)
    elif isinstance(detail, dict):
        message = str(detail.get("message") or detail)
        body = _flat_error(_status_to_code(exc.status_code), message, detail)
    else:
        body = _flat_error(_status_to_code(exc.status_code), str(detail))
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map Pydantic/FastAPI validation errors to the same flat error shape."""
    errors = exc.errors()
    # Prefer the first field-level error for a clear message
    if errors:
        first = errors[0]
        loc = first.get("loc") or ()
        # skip "body" prefix from FastAPI
        field_parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
        field = ".".join(field_parts) if field_parts else None
        msg = first.get("msg") or "Validation error"
        if field:
            message = f"Validation error on field '{field}': {msg}"
        else:
            message = f"Validation error: {msg}"
        details: dict[str, Any] = {"errors": errors}
        if field:
            details["field"] = field
    else:
        message = "Request validation failed"
        details = {"errors": []}

    body = _flat_error(ErrorCode.VALIDATION_ERROR, message, details)
    return JSONResponse(status_code=422, content=body)


app.include_router(products.router, prefix="/api/v1", tags=["Products"])
app.include_router(skus.router, prefix="/api/v1", tags=["SKUs"])
app.include_router(invoices.router, prefix="/api/v1", tags=["Invoices"])
app.include_router(categories.router, prefix="/api/v1", tags=["Categories"])
app.include_router(moderation.router, prefix="/api/v1", tags=["Moderation"])
app.include_router(moderation.approve_router, prefix="/api/v1", tags=["Moderation"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "b2b-seller-cabinet"}
