"""FastAPI application entry point for the recruitment platform API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from ml_project.api.routers.auth import router as auth_router
from ml_project.api.routers.evaluations import router as evaluations_router
from ml_project.api.routers.jobs_candidates import router as jobs_candidates_router
from ml_project.api.routers.matching import router as matching_router
from ml_project.api.routers.shortlists import router as shortlists_router
from ml_project.api.routers.workspaces import router as workspaces_router
from ml_project.config import get_cors_origins, get_environment, get_jwt_settings

_production = get_environment() == "production"
app = FastAPI(
    title="AI Recruitment Sourcing API",
    version="0.1.0",
    description="Backend API foundation for the recruitment sourcing platform.",
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
    openapi_url=None if _production else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_cors_origins()),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth_router)
app.include_router(evaluations_router)
app.include_router(jobs_candidates_router)
app.include_router(matching_router)
app.include_router(shortlists_router)
app.include_router(workspaces_router)


_SAFE_VALIDATION_MESSAGES = {
    "datetime_parsing": "Input should be a valid datetime.",
    "extra_forbidden": "Extra inputs are not permitted.",
    "int_parsing": "Input should be a valid integer.",
    "int_type": "Input should be a valid integer.",
    "json_invalid": "Request body must be valid JSON.",
    "literal_error": "Input is not an allowed value.",
    "missing": "Field required.",
    "string_too_long": "String is too long.",
    "string_too_short": "String is too short.",
    "string_type": "Input should be a valid string.",
    "too_long": "String is too long.",
    "too_short": "String is too short.",
    "uuid_parsing": "Input should be a valid UUID.",
    "value_error": "Invalid value.",
}


def _safe_validation_details(error: RequestValidationError) -> list[dict[str, object]]:
    """Build public validation details without echoing raw input, context, or messages."""
    details = []
    for item in error.errors():
        location = item.get("loc", ())
        field_path = [str(part) for part in location if isinstance(part, (str, int))]
        error_type = item.get("type")
        if not isinstance(error_type, str):
            error_type = "value_error"
        message = _SAFE_VALIDATION_MESSAGES.get(error_type, "Invalid value.")
        if field_path and field_path[-1] == "email" and error_type == "value_error":
            message = "Enter a valid email address."
        details.append({"loc": field_path, "type": error_type, "msg": message})
    return details


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    """Return useful validation locations and types without exposing submitted values."""
    return JSONResponse(
        status_code=422,
        content={"detail": _safe_validation_details(error)},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
    """Keep database details out of API responses."""
    return JSONResponse(
        status_code=500,
        content={"detail": "The database operation could not be completed."},
    )



@app.on_event("startup")
def validate_production_jwt_configuration() -> None:
    if get_environment() == "production":
        get_jwt_settings()


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report API process health without querying or exposing internal services."""
    return {"status": "ok"}
