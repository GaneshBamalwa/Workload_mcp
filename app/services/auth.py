"""Authentication and authorization services."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DuplicateError,
    NotFoundError,
    ValidationError,
)
from app.core.security import (
    PasswordManager,
    TokenManager,
    create_access_token,
    create_refresh_token,
    encrypt_token,
    verify_password,
)
from app.db.repositories import TokenRepository, UserRepository
from app.models.base import Organization, Token, User

logger = structlog.get_logger(__name__)


class AuthService:
    """Authentication service."""

    def __init__(self, session: AsyncSession):
        """Initialize auth service."""
        self.session = session
        self.user_repo = UserRepository(User, session)
        self.token_repo = TokenRepository(Token, session)

    async def register_user(
        self,
        email: str,
        username: str,
        password: str,
        full_name: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> User:
        """Register new user."""
        # Validate input
        if not email or "@" not in email:
            raise ValidationError("Invalid email address")
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters")
        if len(username) < 3:
            raise ValidationError("Username must be at least 3 characters")

        # Check if user already exists
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            logger.warning("User registration attempted for existing email", email=email)
            raise DuplicateError("User with this email already exists")

        existing_username = await self.user_repo.get_by_username(username)
        if existing_username:
            logger.warning("User registration attempted for existing username", username=username)
            raise DuplicateError("Username already taken")

        # If no organization provided, create one
        if not organization_id:
            org = Organization(
                id=str(uuid4()),
                name=f"{full_name or username}'s Organization",
                slug=f"{username}-org-{str(uuid4())[:8]}",
            )
            self.session.add(org)
            await self.session.flush()
            organization_id = org.id

        # Create user
        user_id = str(uuid4())
        password_hash = PasswordManager.hash_password(password)

        user = await self.user_repo.create(
            id=user_id,
            organization_id=organization_id,
            email=email,
            username=username,
            password_hash=password_hash,
            full_name=full_name,
            role="user",
            is_active=True,
        )

        logger.info("User registered successfully", user_id=user_id, email=email)
        return user

    async def authenticate_user(self, email: str, password: str) -> tuple[User, str, str]:
        """Authenticate user and return access/refresh tokens."""
        # Get user by email
        user = await self.user_repo.get_by_email(email)
        if not user:
            logger.warning("Authentication failed: user not found", email=email)
            raise AuthenticationError("Invalid credentials")

        # Check if user is active
        if not user.is_active:
            logger.warning("Authentication failed: user inactive", user_id=user.id)
            raise AuthenticationError("User account is inactive")

        # Verify password
        if not verify_password(password, user.password_hash or ""):
            logger.warning("Authentication failed: invalid password", user_id=user.id)
            raise AuthenticationError("Invalid credentials")

        # Create tokens
        access_token = create_access_token(user.id, user.email, user.role)
        refresh_token = create_refresh_token(user.id)

        logger.info("User authenticated", user_id=user.id, email=email)
        return user, access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> str:
        """Generate new access token from refresh token."""
        try:
            # Verify refresh token
            payload = TokenManager.verify_token(refresh_token)
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type")

            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid token")

            # Get user
            user = await self.user_repo.get_by_id(user_id)
            if not user or not user.is_active:
                raise AuthenticationError("User not found or inactive")

            # Create new access token
            access_token = create_access_token(user.id, user.email, user.role)
            logger.info("Access token refreshed", user_id=user_id)
            return access_token

        except Exception as e:
            logger.error("Token refresh failed", error=str(e))
            raise AuthenticationError("Failed to refresh token")

    async def validate_token(self, token: str) -> str:
        """Validate token and return user_id."""
        try:
            payload = TokenManager.verify_token(token)
            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid token")
            return user_id
        except Exception as e:
            logger.error("Token validation failed", error=str(e))
            raise AuthenticationError("Invalid token")

    async def store_oauth_token(
        self,
        user_id: str,
        connector_type: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_at: Optional[datetime],
        scopes: Optional[list[str]] = None,
    ) -> Token:
        """Store OAuth token for user."""
        # Check if token already exists
        existing_token = await self.token_repo.get_by_user_and_connector(
            user_id, connector_type
        )

        encrypted_access = encrypt_token(access_token)
        encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

        if existing_token:
            # Update existing token
            await self.token_repo.update(
                existing_token.id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                scopes=scopes or [],
                is_valid=True,
                updated_at=datetime.now(timezone.utc),
            )
            logger.info(
                "OAuth token updated",
                user_id=user_id,
                connector=connector_type,
            )
            return existing_token
        else:
            # Create new token
            token = await self.token_repo.create(
                id=str(uuid4()),
                user_id=user_id,
                connector_type=connector_type,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                token_type="Bearer",
                expires_at=expires_at,
                scopes=scopes or [],
                is_valid=True,
            )
            logger.info(
                "OAuth token stored",
                user_id=user_id,
                connector=connector_type,
            )
            return token


class AuthorizationService:
    """Authorization service for RBAC."""

    ROLE_HIERARCHY = {
        "admin": ["admin", "manager", "user"],
        "manager": ["manager", "user"],
        "user": ["user"],
    }

    @staticmethod
    def check_role(user_role: str, required_role: str) -> bool:
        """Check if user has required role or higher."""
        allowed_roles = AuthorizationService.ROLE_HIERARCHY.get(user_role, [])
        return required_role in allowed_roles

    @staticmethod
    def require_role(user_role: str, required_role: str) -> None:
        """Require specific role or raise exception."""
        if not AuthorizationService.check_role(user_role, required_role):
            raise AuthorizationError(f"Required role: {required_role}")

    @staticmethod
    def require_admin(user_role: str) -> None:
        """Require admin role."""
        AuthorizationService.require_role(user_role, "admin")

    @staticmethod
    def require_manager(user_role: str) -> None:
        """Require manager role or higher."""
        AuthorizationService.require_role(user_role, "manager")
