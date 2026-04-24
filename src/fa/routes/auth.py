"""Authentication endpoints."""

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..cache_service import cache_service
from ..models import AuthResponse, LoginRequest, UserInfo
from ..radius import validate_credentials
from ..session import SessionData, session_manager

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _log_background_refresh_result(task: asyncio.Task[None]) -> None:
    """Log uncaught errors from login-triggered cache refresh tasks."""
    try:
        task.result()
    except asyncio.CancelledError:
        logger.info("Login-triggered cache refresh task was cancelled")
    except Exception:
        logger.exception("Login-triggered cache refresh task failed")


async def get_session_data(request: Request) -> SessionData | None:
    """Get current session from cookie."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    return session_manager.get(session_id)


@router.post("/login", response_model=AuthResponse)
async def login(credentials: LoginRequest, response: Response) -> AuthResponse:
    """
    Authenticate user and create session.

    Validates credentials via RADIUS, creates session with encrypted
    credentials, and sets httpOnly cookie.
    """
    if not await validate_credentials(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = session_manager.create(
        username=credentials.username, password=credentials.password
    )

    mgmt_ip = os.getenv("API_MGMT")
    if mgmt_ip:
        task = asyncio.create_task(
            cache_service.refresh_domains_and_packages(
                credentials.username,
                credentials.password,
                mgmt_ip,
            )
        )
        task.add_done_callback(_log_background_refresh_result)

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # Set True in production with HTTPS
        samesite="lax",
        max_age=8 * 3600,  # 8 hours
    )

    return AuthResponse(message="Logged in successfully", username=credentials.username)


@router.post("/logout", response_model=AuthResponse)
async def logout(
    request: Request,
    response: Response,
    _session: SessionData | None = Depends(get_session_data),
) -> AuthResponse:
    """Destroy user session."""
    session_id = request.cookies.get("session_id")
    if session_id:
        session_manager.delete(session_id)

    response.delete_cookie("session_id")
    return AuthResponse(message="Logged out")


@router.get("/me")
async def get_me(
    session: SessionData | None = Depends(get_session_data),
) -> UserInfo:
    """Get current user information."""
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return UserInfo(username=session.username, logged_in_at=session.created_at.isoformat())
