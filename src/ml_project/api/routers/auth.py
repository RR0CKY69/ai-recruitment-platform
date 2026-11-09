
"""Login and current-user endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ml_project.api.dependencies import get_api_session, get_current_user
from ml_project.api.workspace_slugs import generate_workspace_slug
from ml_project.api.rate_limit import InMemoryLoginRateLimiter, client_rate_limit_key
from ml_project.api.schemas import (
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from ml_project.config import (
    get_cors_origins,
    get_jwt_settings,
    get_login_rate_limit_settings,
    get_refresh_token_settings,
)
from ml_project.models import RefreshSession, User, Workspace, WorkspaceMember
from ml_project.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_dummy_password,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["authentication"])
login_rate_limiter = InMemoryLoginRateLimiter()


def _normalize_samesite(value: str) -> Literal["lax", "strict", "none"]:
    """Validate and normalize the SameSite cookie setting."""
    normalized = value.strip().lower()

    if normalized not in {"lax", "strict", "none"}:
        raise ValueError(f"Invalid SameSite cookie setting: {value}")

    return cast(Literal["lax", "strict", "none"], normalized)


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_refresh_token_settings()
    max_age = int(timedelta(days=settings.token_days).total_seconds())

    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=_normalize_samesite(settings.cookie_samesite),
        max_age=max_age,
        expires=max_age,
        path=settings.cookie_path,
        domain=settings.cookie_domain,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_refresh_token_settings()

    response.set_cookie(
        key=settings.cookie_name,
        value="",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=_normalize_samesite(settings.cookie_samesite),
        max_age=0,
        expires=0,
        path=settings.cookie_path,
        domain=settings.cookie_domain,
    )


def _validate_origin(request: Request) -> None:
    try:
        origins = set(get_cors_origins())
    except Exception:  # noqa: BLE001 - intentional broad catch for config errors
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request not allowed.",
        ) from None

    origin = request.headers.get("origin")

    if origin and origin in origins:
        return

    # If no Origin header (same-site requests), allow;
    # if Origin is present and not allowed, reject.
    if origin and origin not in origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request not allowed.",
        )


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    response: Response,
    credentials: LoginRequest,
    session: Annotated[Session, Depends(get_api_session)],
) -> TokenResponse:
    """Authenticate a user and issue a short-lived access token."""
    _validate_origin(request)

    try:
        rate_limit_settings = get_login_rate_limit_settings()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        ) from None

    client_key = client_rate_limit_key(
        request,
        rate_limit_settings.trusted_proxy_networks,
    )

    retry_after = login_rate_limiter.check_rate_limit(
        client_key,
        rate_limit_settings.attempts,
        rate_limit_settings.window_seconds,
    )

    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = session.scalar(
        select(User).where(func.lower(User.email) == credentials.email)
    )

    password = credentials.password.get_secret_value()

    if user is None:
        login_rate_limiter.record_failure(
            client_key,
            rate_limit_settings.attempts,
            rate_limit_settings.window_seconds,
        )
        verify_dummy_password(password)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(password, user.password_hash):
        login_rate_limiter.record_failure(
            client_key,
            rate_limit_settings.attempts,
            rate_limit_settings.window_seconds,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication is not permitted.",
        )

    try:
        settings = get_jwt_settings()
        refresh_settings = get_refresh_token_settings()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        ) from None

    try:
        refresh_token = generate_refresh_token()
        token_hash = hash_refresh_token(refresh_token)
        now = datetime.now(timezone.utc)
        family_id = uuid4()

        refresh_session = RefreshSession(
            user_id=user.id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=now + timedelta(days=refresh_settings.token_days),
            revoked_at=None,
        )

        session.add(refresh_session)
        session.commit()

    except SQLAlchemyError:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The database operation could not be completed.",
        ) from None

    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        token_type="bearer",
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_api_session)],
):
    """Rotate a refresh token and issue a new access token."""
    _validate_origin(request)

    try:
        refresh_settings = get_refresh_token_settings()
        jwt_settings = get_jwt_settings()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        ) from None

    refresh_token = request.cookies.get(refresh_settings.cookie_name)

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    token_hash = hash_refresh_token(refresh_token)
    now = datetime.now(timezone.utc)

    try:
        # Lock the session row for update if possible.
        refresh_session = session.scalar(
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
        )

        if refresh_session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        if refresh_session.revoked_at is not None:
            # Reuse detected: revoke the entire token family.
            session.execute(
                update(RefreshSession)
                .where(RefreshSession.family_id == refresh_session.family_id)
                .where(RefreshSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )

            session.commit()
            _clear_refresh_cookie(response)

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        expires_at = refresh_session.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= now:
            refresh_session.revoked_at = now
            session.commit()
            _clear_refresh_cookie(response)

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        # Rotate: create a new session in the same family and revoke the old one.
        new_refresh_token = generate_refresh_token()
        new_token_hash = hash_refresh_token(new_refresh_token)

        new_session = RefreshSession(
            user_id=refresh_session.user_id,
            token_hash=new_token_hash,
            family_id=refresh_session.family_id,
            expires_at=now + timedelta(days=refresh_settings.token_days),
            revoked_at=None,
        )

        refresh_session.revoked_at = now
        session.add(new_session)
        session.commit()

        _set_refresh_cookie(response, new_refresh_token)

        return {
            "access_token": create_access_token(
                refresh_session.user_id,
                jwt_settings,
            ),
            "token_type": "bearer",
            "expires_in": jwt_settings.access_token_minutes * 60,
        }

    except HTTPException:
        raise

    except SQLAlchemyError:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The database operation could not be completed.",
        ) from None


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_api_session)],
):
    """Revoke the current refresh session and clear its cookie."""
    _validate_origin(request)

    try:
        refresh_settings = get_refresh_token_settings()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        ) from None

    refresh_token = request.cookies.get(refresh_settings.cookie_name)

    if refresh_token:
        try:
            token_hash = hash_refresh_token(refresh_token)

            refresh_session = session.scalar(
                select(RefreshSession).where(
                    RefreshSession.token_hash == token_hash
                )
            )

            if refresh_session and refresh_session.revoked_at is None:
                refresh_session.revoked_at = datetime.now(timezone.utc)
                session.commit()
            elif refresh_session:
                session.rollback()
            else:
                session.rollback()

        except SQLAlchemyError:
            session.rollback()

        _clear_refresh_cookie(response)
        return {"detail": "Logged out."}

    _clear_refresh_cookie(response)
    return {"detail": "Logged out."}


@router.get("/me", response_model=CurrentUserResponse)
def current_user(
    user: Annotated[User, Depends(get_current_user)],
) -> CurrentUserResponse:
    """Return public account fields only; ORM password hashes are never serialized."""
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
    )



@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    credentials: RegisterRequest,
    session: Annotated[Session, Depends(get_api_session)],
) -> Response:
    """Register a new user with an initial workspace and ADMIN membership.

    All writes occur atomically. No authentication tokens are issued; the user
    must log in separately after registration succeeds.
    """
    normalized_email = credentials.email

    existing = session.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    workspace_slug = generate_workspace_slug(credentials.workspace_name)

    try:
        user = User(
            email=normalized_email,
            password_hash=hash_password(credentials.password),
            full_name=credentials.full_name,
            is_active=True,
        )

        session.add(user)
        session.flush()

        workspace = Workspace(
            name=credentials.workspace_name,
            slug=workspace_slug,
            created_by_id=user.id,
        )

        session.add(workspace)
        session.flush()

        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="ADMIN",
            )
        )

        session.commit()

    except IntegrityError:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        ) from None

    except SQLAlchemyError:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The database operation could not be completed.",
        ) from None

    return Response(status_code=status.HTTP_201_CREATED)
