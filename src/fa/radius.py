"""Authentication helpers for WebUI login."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from cpapi import APIClient, APIClientArgs  # type: ignore[import-untyped]

_TOO_MANY_LOGINS_CODE = "err_too_many_logins"
_RETRY_SECONDS = 5
_MAX_RETRIES = 10


def _extract_error_code(response_data: Any) -> str:
    """Extract Check Point error code from login response payload."""
    if not isinstance(response_data, dict):
        return ""

    code = response_data.get("code")
    if isinstance(code, str) and code:
        return code

    errors = response_data.get("errors")
    if isinstance(errors, list):
        for error_item in errors:
            if not isinstance(error_item, dict):
                continue
            message = error_item.get("message")
            if not isinstance(message, str):
                continue
            for line in message.splitlines():
                line = line.strip()
                if line.startswith("code:"):
                    return line.replace("code:", "", 1).strip()

    return ""


def _validate_credentials_env(username: str, password: str) -> bool:
    """Validate credentials against local env values for mock mode."""
    env_username = os.getenv("API_USERNAME")
    env_password = os.getenv("API_PASSWORD")
    if not env_username or not env_password:
        return False
    return username == env_username and password == env_password


async def _login_logout_via_mgmt(username: str, password: str) -> bool:
    """Validate credentials via direct Management API login/logout."""
    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        return False

    for attempt in range(_MAX_RETRIES):
        client_args = APIClientArgs(server=mgmt_ip, unsafe_auto_accept=True)
        client = APIClient(client_args)
        try:
            response = await asyncio.to_thread(
                client.login,
                username,
                password,
                False,  # continue_last_session
                None,  # domain (system domain)
                False,  # read_only
                {},
            )

            if (
                response
                and response.success
                and isinstance(response.data, dict)
                and response.data.get("sid")
            ):
                # Keep validation stateless: close the management session immediately.
                await asyncio.to_thread(client.api_call, "logout")
                return True

            response_data = response.data if response else None
            if (
                _extract_error_code(response_data) == _TOO_MANY_LOGINS_CODE
                and attempt < _MAX_RETRIES - 1
            ):
                await asyncio.sleep(_RETRY_SECONDS)
                continue

            return False
        except Exception:
            return False
        finally:
            await asyncio.to_thread(client.close_connection)

    return False


async def validate_credentials(username: str, password: str) -> bool:
    """Validate login credentials using configured auth backend.

    AUTH_BACKEND values:
    - env: compare against API_USERNAME/API_PASSWORD in environment
    - mgmt (default): direct HTTPS login to Check Point Management API
    """
    auth_backend = os.getenv("AUTH_BACKEND", "mgmt").strip().lower()
    if auth_backend == "env":
        return _validate_credentials_env(username, password)
    return await _login_logout_via_mgmt(username, password)
