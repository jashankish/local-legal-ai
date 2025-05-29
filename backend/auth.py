# JWT-based authentication logic

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import json

from .config import settings


# Security
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Pydantic models
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"  # user, admin, lawyer


class UserLogin(BaseModel):
    username: str
    password: str


class User(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool = True
    created_at: datetime


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


class UserManager:
    """Simple user management system."""
    
    def __init__(self):
        self.users_file = USERS_FILE
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
        """Save users to JSON file."""
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=2, default=str)
    
    def _ensure_admin_user(self):
        """Create default admin user if no users exist."""
        users = self._load_users()
        if not users:
            admin_user = {
                "id": "admin",
                "username": "admin",
                "email": "admin@legalai.local",
                "hashed_password": self.get_password_hash("admin123"),
                "role": "admin",
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            }
            users["admin"] = admin_user
            self._save_users(users)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_user(self, username: str) -> Optional[Dict]:
        """Get user by username."""
        users = self._load_users()
        return users.get(username)
    
    def create_user(self, user_data: UserCreate) -> User:
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
    except JWTError:
        raise credentials_exception
    
    user = user_manager.get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    
    return User(**{k: v for k, v in user.items() if k != "hashed_password"})


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
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
        self.allowed_ips = settings.get_allowed_ips_list()
    
    def is_allowed(self, client_ip: str) -> bool:
        """Check if IP is allowed."""
        if not self.allowed_ips:  # No restriction if no IPs configured
            return True
        return client_ip in self.allowed_ips


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
