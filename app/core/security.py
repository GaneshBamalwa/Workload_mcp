"""Security utilities for authentication and encryption."""
import base64
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AuthenticationError

logger = structlog.get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token generation characters
TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class PasswordManager:
    """Password hashing and verification."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error("Password verification failed", error=str(e))
            return False


class TokenManager:
    """JWT token creation and validation."""

    @staticmethod
    def create_access_token(
        user_id: str,
        email: str,
        role: str = "user",
        expires_in: Optional[int] = None,
    ) -> str:
        """Create JWT access token."""
        if expires_in is None:
            expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds

        now = datetime.now(timezone.utc)
        expire = now + timedelta(seconds=expires_in)

        to_encode = {
            "sub": user_id,
            "email": email,
            "role": role,
            "exp": expire,
            "iat": now,
            "type": "access",
        }

        try:
            encoded_jwt = jwt.encode(
                to_encode,
                settings.JWT_SECRET_KEY,
                algorithm=settings.JWT_ALGORITHM,
            )
            logger.info("Access token created", user_id=user_id, expires_in=expires_in)
            return encoded_jwt
        except Exception as e:
            logger.error("Failed to create access token", error=str(e))
            raise

    @staticmethod
    def create_refresh_token(user_id: str) -> str:
        """Create JWT refresh token."""
        expires_in = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400  # Convert to seconds
        now = datetime.now(timezone.utc)
        expire = now + timedelta(seconds=expires_in)

        to_encode = {
            "sub": user_id,
            "exp": expire,
            "iat": now,
            "type": "refresh",
        }

        try:
            encoded_jwt = jwt.encode(
                to_encode,
                settings.JWT_SECRET_KEY,
                algorithm=settings.JWT_ALGORITHM,
            )
            logger.info("Refresh token created", user_id=user_id)
            return encoded_jwt
        except Exception as e:
            logger.error("Failed to create refresh token", error=str(e))
            raise

    @staticmethod
    def verify_token(token: str) -> dict[str, Any]:
        """Verify JWT token and extract payload."""
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid token: missing subject")
            return payload
        except JWTError as e:
            logger.warning("Token verification failed", error=str(e))
            raise AuthenticationError(f"Invalid token: {str(e)}")

    @staticmethod
    def extract_user_id(token: str) -> str:
        """Extract user ID from token."""
        payload = TokenManager.verify_token(token)
        return payload["sub"]


class EncryptionManager:
    """Symmetric encryption for sensitive data (OAuth tokens, etc)."""

    _cipher: Optional[Fernet] = None

    @classmethod
    def _get_cipher(cls) -> Fernet:
        """Get or create cipher."""
        if cls._cipher is None:
            # Ensure key is valid base64
            key = settings.ENCRYPTION_KEY
            if isinstance(key, str):
                # Pad key if necessary
                key = key.encode()
                if len(key) < 32:
                    key = base64.urlsafe_b64encode(key.ljust(32))
                else:
                    key = base64.urlsafe_b64encode(key[:32])
            cls._cipher = Fernet(key)
        return cls._cipher

    @classmethod
    def encrypt_token(cls, token: str) -> str:
        """Encrypt sensitive token."""
        try:
            cipher = cls._get_cipher()
            encrypted = cipher.encrypt(token.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error("Token encryption failed", error=str(e))
            raise

    @classmethod
    def decrypt_token(cls, encrypted_token: str) -> str:
        """Decrypt sensitive token."""
        try:
            cipher = cls._get_cipher()
            encrypted = base64.b64decode(encrypted_token.encode())
            decrypted = cipher.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            logger.error("Token decryption failed", error=str(e))
            raise


class RandomGenerator:
    """Generate random tokens and identifiers."""

    @staticmethod
    def generate_token(length: int = 32) -> str:
        """Generate random token."""
        return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(length))

    @staticmethod
    def generate_state() -> str:
        """Generate OAuth state parameter."""
        return secrets.token_urlsafe(32)


# Convenience exports
hash_password = PasswordManager.hash_password
verify_password = PasswordManager.verify_password
create_access_token = TokenManager.create_access_token
create_refresh_token = TokenManager.create_refresh_token
verify_token = TokenManager.verify_token
extract_user_id = TokenManager.extract_user_id
encrypt_token = EncryptionManager.encrypt_token
decrypt_token = EncryptionManager.decrypt_token
generate_token = RandomGenerator.generate_token
generate_state = RandomGenerator.generate_state
