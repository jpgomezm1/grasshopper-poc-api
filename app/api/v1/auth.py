"""Authentication endpoints."""
from __future__ import annotations

import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel, EmailStr
import bcrypt
from jose import JWTError, jwt

from app.config import get_settings
from app.db.database import get_db
from app.db.models import User, OnboardingStatus, Session

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()
settings = get_settings()


# Pydantic schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: Optional[str]
    onboarding_status: OnboardingStatus
    english_test_completed: bool = False
    english_cefr_level: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class OnboardingUpdateRequest(BaseModel):
    answers: dict
    status: Optional[OnboardingStatus] = None


class OnboardingResponse(BaseModel):
    status: OnboardingStatus
    answers: dict


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    method: str = "email"  # "email" or "phone"


class ForgotPasswordResponse(BaseModel):
    message: str
    # POC only: return reset link directly (in production, only send via email/SMS)
    reset_link: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


logger = logging.getLogger(__name__)


# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: DBSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == UUID(user_id)).first()
    if user is None:
        raise credentials_exception

    return user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: DBSession = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, None otherwise."""
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return db.query(User).filter(User.id == UUID(user_id)).first()
    except JWTError:
        return None


# Endpoints
@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: DBSession = Depends(get_db)):
    """Authenticate user and return JWT token."""
    user = db.query(User).filter(User.email == request.email.lower()).first()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: DBSession = Depends(get_db)):
    """Register a new user."""
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    user = User(
        email=request.email.lower(),
        hashed_password=get_password_hash(request.password),
        name=request.name,
        onboarding_status=OnboardingStatus.NOT_STARTED,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return UserResponse.model_validate(current_user)


@router.get("/me/onboarding", response_model=OnboardingResponse)
def get_onboarding(current_user: User = Depends(get_current_user)):
    """Get user's onboarding status and answers."""
    return OnboardingResponse(
        status=current_user.onboarding_status,
        answers=current_user.onboarding_answers or {}
    )


@router.put("/me/onboarding", response_model=OnboardingResponse)
def update_onboarding(
    request: OnboardingUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """Update user's onboarding progress."""
    # Merge answers
    current_answers = current_user.onboarding_answers or {}
    current_answers.update(request.answers)
    current_user.onboarding_answers = current_answers

    # Update status if provided
    if request.status:
        current_user.onboarding_status = request.status

    db.commit()
    db.refresh(current_user)

    return OnboardingResponse(
        status=current_user.onboarding_status,
        answers=current_user.onboarding_answers
    )


@router.post("/me/complete-onboarding", response_model=UserResponse)
def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """Mark onboarding as completed and create initial journey session."""
    current_user.onboarding_status = OnboardingStatus.COMPLETED

    # Create initial session for user if they don't have one
    existing_session = db.query(Session).filter(Session.user_id == current_user.id).first()
    if not existing_session:
        session = Session(user_id=current_user.id)
        db.add(session)

    db.commit()
    db.refresh(current_user)

    return UserResponse.model_validate(current_user)


@router.get("/me/session")
def get_user_session(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """Get or create user's journey session."""
    session = db.query(Session).filter(Session.user_id == current_user.id).first()

    if not session:
        session = Session(user_id=current_user.id)
        db.add(session)
        db.commit()
        db.refresh(session)

    return {
        "session_id": str(session.id),
        "current_step": session.current_step,
        "current_stage": session.current_stage.value,
        "is_completed": session.is_completed,
    }


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(request: ForgotPasswordRequest, req: Request, db: DBSession = Depends(get_db)):
    """Request a password reset. Generates a token and simulates sending it via email/SMS."""
    user = db.query(User).filter(User.email == request.email.lower()).first()

    # Always return success to prevent email enumeration attacks
    if not user:
        return ForgotPasswordResponse(
            message="Si el correo está registrado, recibirás instrucciones para recuperar tu contraseña."
        )

    # Generate secure reset token
    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    db.commit()

    # Build reset link from the Origin header (handles any port)
    origin = req.headers.get("origin", "http://localhost:5173")
    reset_link = f"{origin}/reset-password/{reset_token}"
    logger.info(f"[POC] Password reset link for {user.email}: {reset_link}")

    if request.method == "phone" and user.phone:
        logger.info(f"[POC] SMS would be sent to {user.phone}")

    return ForgotPasswordResponse(
        message="Si el correo está registrado, recibirás instrucciones para recuperar tu contraseña.",
        reset_link=reset_link if settings.environment == "development" else None,
    )


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: DBSession = Depends(get_db)):
    """Reset password using a valid reset token."""
    user = db.query(User).filter(User.password_reset_token == request.token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado."
        )

    # Check token expiration (treat missing expiry as expired for safety)
    if not user.password_reset_expires or user.password_reset_expires < datetime.utcnow():
        # Clear expired token
        user.password_reset_token = None
        user.password_reset_expires = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace de recuperación ha expirado. Solicita uno nuevo."
        )

    # Validate new password strength (must match frontend rules)
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener al menos 8 caracteres."
        )

    import re
    if not re.search(r'[A-Z]', request.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener al menos una letra mayúscula."
        )
    if not re.search(r'[0-9]', request.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener al menos un número."
        )

    # Update password and clear reset token
    user.hashed_password = get_password_hash(request.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    db.commit()

    return {"message": "Contraseña actualizada exitosamente. Ya puedes iniciar sesión."}
