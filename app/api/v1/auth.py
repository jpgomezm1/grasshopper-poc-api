"""Authentication endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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

    user = db.query(User).filter(User.id == user_id).first()
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
        return db.query(User).filter(User.id == user_id).first()
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
