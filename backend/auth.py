# JWT-based authentication logic

import os
import hashlib
import ipaddress
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel
import json
import threading
import logging

# Configure logging
logger = logging.getLogger(__name__)

from backend.config import settings


# Security
security = HTTPBearer()
# bcrypt is used directly: passlib is unmaintained and breaks on bcrypt>=4.1.


# Pydantic models
VALID_ROLES = ("admin", "lawyer", "user")


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    role: str = "user"  # user, admin, lawyer


class UserLogin(BaseModel):
    username: str
    password: str


class User(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool = True
    created_at: datetime
    last_login: Optional[datetime] = None
    must_change_password: bool = False


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: User


# Simple file-based user store (in production, use a proper database)
USERS_FILE = "data/users.json"
DEFAULT_ADMIN_PASSWORD = "admin123"
MIN_PASSWORD_LENGTH = 8


def validate_new_password(password: str, username: str) -> Optional[str]:
    """Return a human-readable problem with a proposed password, or None if acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if password.lower() == username.lower():
        return "Password cannot be the same as the username"
    if password == DEFAULT_ADMIN_PASSWORD:
        return "Choose a password other than the default"
    return None


class UserManager:
    """Simple user management system."""

    def __init__(self):
        self.users_file = USERS_FILE
        self._lock = threading.RLock()
        self._ensure_data_dir()
        self._ensure_admin_user()
    
    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        os.makedirs(os.path.dirname(self.users_file), exist_ok=True)
    
    def _load_users(self) -> Dict:
        """Load users from JSON file."""
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_users(self, users: Dict):
        """Atomically write the user store (temp file + rename), readable only by the owner."""
        tmp_path = f"{self.users_file}.tmp"
        with open(tmp_path, 'w') as f:
            json.dump(users, f, indent=2, default=str)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self.users_file)
    
    def _ensure_admin_user(self):
        """Create default admin user if no users exist."""
        users = self._load_users()
        if not users:
            admin_user = {
                "id": "admin",
                "username": "admin",
                "email": "admin@legalai.local",
                "hashed_password": self.get_password_hash(DEFAULT_ADMIN_PASSWORD),
                "role": "admin",
                "is_active": True,
                "must_change_password": True,
                "token_version": 0,
                "created_at": datetime.utcnow().isoformat()
            }
            users["admin"] = admin_user
            self._save_users(users)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password (bcrypt only considers the first 72 bytes)."""
        return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False
    
    def get_user(self, username: str) -> Optional[Dict]:
        """Get user by username."""
        users = self._load_users()
        return users.get(username)
    
    def create_user(self, user_data: UserCreate, must_change_password: bool = False) -> User:
        """Create a new user."""
        users = self._load_users()
        
        if user_data.username in users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
        
        user_id = hashlib.md5(user_data.username.encode()).hexdigest()[:8]
        hashed_password = self.get_password_hash(user_data.password)
        
        new_user = {
            "id": user_id,
            "username": user_data.username,
            "email": user_data.email,
            "hashed_password": hashed_password,
            "role": user_data.role,
            "is_active": True,
            "must_change_password": must_change_password,
            "token_version": 0,
            "created_at": datetime.utcnow().isoformat()
        }

        users[user_data.username] = new_user
        self._save_users(users)
        
        return User(**{k: v for k, v in new_user.items() if k != "hashed_password"})
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate a user."""
        user = self.get_user(username)
        if not user:
            return None
        if not self.verify_password(password, user["hashed_password"]):
            return None
        if password == DEFAULT_ADMIN_PASSWORD and not user.get("must_change_password"):
            # Installs created before forced rotation existed: still make them change it.
            user = self.update_user(username, must_change_password=True)
        return user

    @staticmethod
    def public_view(user: Dict) -> Dict:
        """User record without secrets or internal counters."""
        return {k: v for k, v in user.items() if k not in ("hashed_password", "token_version")}

    def list_users(self) -> List[Dict]:
        """All users, without password hashes, sorted by username."""
        return [self.public_view(u) for _, u in sorted(self._load_users().items())]

    def active_admin_count(self, users: Optional[Dict] = None) -> int:
        users = users if users is not None else self._load_users()
        return sum(1 for u in users.values() if u.get("role") == "admin" and u.get("is_active", True))

    def update_user(self, username: str, **changes) -> Dict:
        """Apply field changes to a user. Disabling or demoting revokes existing sessions."""
        allowed = {"email", "role", "is_active", "must_change_password", "last_login"}
        with self._lock:
            users = self._load_users()
            if username not in users:
                raise KeyError(username)
            user = users[username]
            for key, value in changes.items():
                if key in allowed and value is not None:
                    user[key] = value
            if changes.get("is_active") is False or ("role" in changes and changes["role"] is not None):
                user["token_version"] = user.get("token_version", 0) + 1
            self._save_users(users)
            return user

    def set_password(self, username: str, new_password: str, must_change: bool) -> Dict:
        """Replace a password and revoke every token issued before the change."""
        with self._lock:
            users = self._load_users()
            if username not in users:
                raise KeyError(username)
            user = users[username]
            user["hashed_password"] = self.get_password_hash(new_password)
            user["must_change_password"] = must_change
            user["token_version"] = user.get("token_version", 0) + 1
            user["password_changed_at"] = datetime.utcnow().isoformat()
            self._save_users(users)
            return user


# Initialize user manager
user_manager = UserManager()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def issue_token(user: Dict) -> str:
    """Token bound to the user's current token_version, so it dies on password change or disable."""
    return create_access_token(data={"sub": user["username"], "tv": user.get("token_version", 0)})


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
        token_version = payload.get("tv", 0)
    except JWTError:
        raise credentials_exception

    user = user_manager.get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    if user.get("token_version", 0) != token_version:
        # Password changed, account disabled or role changed since this token was issued.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return User(**user_manager.public_view(user))


async def get_current_user_pending_ok(current_user: User = Depends(get_current_user)):
    """Active user who may still have a pending password change (for /auth/me, change-password)."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return current_user


async def get_current_active_user(current_user: User = Depends(get_current_user_pending_ok)):
    """Active user with no outstanding password change; required by every other endpoint."""
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required before continuing",
        )
    return current_user


async def require_role(required_roles: List[str]):
    """Dependency to require specific roles."""
    def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker


async def require_admin(current_user: User = Depends(get_current_active_user)):
    """Dependency to require admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


class IPWhitelistMiddleware:
    """Middleware to check IP whitelist."""
    
    def __init__(self):
        self.configure(settings.get_allowed_ips_list())

    def configure(self, entries: List[str]):
        """Accept single addresses ("10.0.0.5") and networks ("10.0.0.0/24")."""
        self.allowed_ips = entries
        self.networks = []
        for entry in entries:
            try:
                self.networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                logger.warning(f"Ignoring invalid ALLOWED_IPS entry: {entry}")

    def is_allowed(self, client_ip: str) -> bool:
        """Check if IP is allowed."""
        if not self.allowed_ips:  # No restriction if no IPs configured
            return True
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return any(address in network for network in self.networks)


ip_whitelist = IPWhitelistMiddleware()


def check_ip_whitelist(request: Request):
    """Check if client IP is whitelisted."""
    client_ip = request.client.host
    if not ip_whitelist.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IP address not allowed"
        )
    return True
