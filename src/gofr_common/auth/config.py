"""Authentication configuration utilities.

Provides resolve_auth_config() for resolving JWT secret from CLI arguments,
environment variables, and defaults. Storage backends are configured via
create_stores_from_env (Vault-only).
"""

import os
import secrets
import sys
from typing import Optional, Tuple

from gofr_common.logger import Logger, create_logger


def resolve_auth_config(
    env_prefix: str = "GOFR",
    jwt_secret_arg: Optional[str] = None,
    require_auth: bool = True,
    allow_auto_secret: bool = True,
    exit_on_missing: bool = False,
    logger: Optional[Logger] = None,
) -> Tuple[Optional[str], bool]:
    """Resolve authentication configuration from CLI args, environment, and defaults.

    Priority chain:
        1. CLI arguments (jwt_secret_arg)
        2. Environment variables ({PREFIX}_JWT_SECRET)
        3. Auto-generated secret (only if allow_auto_secret=True and not production)

    Args:
        env_prefix: Environment variable prefix (e.g., "GOFR_DIG", "GOFR_PLOT")
        jwt_secret_arg: JWT secret from CLI argument (takes precedence)
        require_auth: Whether authentication is required
        allow_auto_secret: Allow auto-generation of dev secret (default: True)
        exit_on_missing: If True, call sys.exit(1) when secret missing (default: False)
        logger: Optional logger instance

    Returns:
        Tuple of (jwt_secret, require_auth)
        - jwt_secret: Resolved JWT secret or None if auth disabled
        - require_auth: Final auth requirement status

    Raises:
        ValueError: If require_auth=True but no JWT secret could be resolved and
                   auto-generation is disabled or in production environment
    """
    # Normalize prefix
    prefix = env_prefix.upper().replace("-", "_")

    # Setup logger
    if logger is None:
        # Convert prefix to logger name format (e.g., "GOFR_DIG" -> "gofr-dig-auth-config")
        logger_name = prefix.lower().replace("_", "-") + "-auth-config"
        logger = create_logger(name=logger_name)

    # If auth not required, return early
    if not require_auth:
        logger.info("Authentication disabled (--no-auth)")
        return None, False

    # Environment variable names
    # JWT secret is system-wide (tokens shared across all GOFR services)
    secret_env = "GOFR_JWT_SECRET"
    env_env = f"{prefix}_ENV"

    # Resolve JWT secret with priority chain
    resolved_secret: Optional[str] = None
    secret_source = "none"

    # Priority 1: CLI argument
    if jwt_secret_arg:
        resolved_secret = jwt_secret_arg
        secret_source = "CLI argument"

    # Priority 2: Environment variable
    elif os.environ.get(secret_env):
        resolved_secret = os.environ[secret_env]
        secret_source = f"{secret_env} environment variable"

    # Priority 3: Auto-generated (only in development)
    elif allow_auto_secret:
        is_production = os.environ.get(env_env, "").upper() in ("PROD", "PRODUCTION")
        if is_production:
            error_msg = f"No JWT secret provided in production environment. Set {secret_env} environment variable or use --jwt-secret flag"
            logger.error("FATAL: " + error_msg)
            if exit_on_missing:
                sys.exit(1)
            raise ValueError(error_msg)
        else:
            resolved_secret = secrets.token_hex(32)
            secret_source = "auto-generated (DEVELOPMENT ONLY)"
            logger.warning(
                "Auto-generated JWT secret - not suitable for production. "
                "Tokens will be invalidated on server restart",
                hint=f"Set {secret_env} for persistent authentication",
            )

    # If still no secret and auth required, fail
    if not resolved_secret:
        error_msg = (
            f"JWT secret required but not provided. "
            f"Set {secret_env} environment variable or use --jwt-secret flag, "
            f"or use --no-auth to disable authentication"
        )
        logger.error("FATAL: " + error_msg)
        if exit_on_missing:
            sys.exit(1)
        raise ValueError(error_msg)

    # Log resolved configuration
    logger.info(
        "Authentication configuration resolved",
        require_auth=require_auth,
        secret_source=secret_source,
        secret_fingerprint=_fingerprint_secret(resolved_secret),
    )

    return resolved_secret, require_auth


def resolve_jwt_secret_for_cli(
    env_prefix: str = "GOFR",
    cli_secret: Optional[str] = None,
    exit_on_missing: bool = True,
    logger: Optional[Logger] = None,
) -> str:
    """Resolve JWT secret for CLI scripts (token_manager, etc).

    Args:
        env_prefix: Environment variable prefix
        cli_secret: Secret from --secret CLI argument
        exit_on_missing: If True, call sys.exit(1) when missing
        logger: Optional logger instance

    Returns:
        JWT secret string

    Raises:
        ValueError: If no secret can be resolved and exit_on_missing=False
    """
    prefix = env_prefix.upper().replace("-", "_")
    # JWT secret is system-wide (tokens shared across all GOFR services)
    secret_env = "GOFR_JWT_SECRET"

    if logger is None:
        logger_name = prefix.lower().replace("_", "-") + "-auth-config"
        logger = create_logger(name=logger_name)

    secret = cli_secret or os.environ.get(secret_env)

    if not secret:
        error_msg = (
            f"No JWT secret provided. Set {secret_env} environment variable or use --secret flag"
        )
        logger.error("FATAL: " + error_msg)
        if exit_on_missing:
            sys.exit(1)
        raise ValueError(error_msg)

    logger.info(
        "JWT secret resolved",
        source="CLI" if cli_secret else "environment",
        fingerprint=_fingerprint_secret(secret),
    )

    return secret


def _fingerprint_secret(secret: str) -> str:
    """Create a safe fingerprint of the secret for logging (first 12 chars of SHA256)."""
    import hashlib

    digest = hashlib.sha256(secret.encode()).hexdigest()
    return f"sha256:{digest[:12]}"
