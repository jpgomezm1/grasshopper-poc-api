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
from pydantic import BaseModel, EmailStr, Field
import bcrypt
from jose import JWTError, jwt

from app.config import get_settings
from app.core.rate_limiter import limiter
from app.core.url_safety import build_safe_url
from app.db.database import get_db
from app.db.models import User, OnboardingStatus, Session, UserRole, School
from app.schemas.school import SchoolSummary

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()
settings = get_settings()


def _rate_limit_login(request: Request) -> None:
    """GH-S11-INFRA-04 · per-IP rate limit for /auth/login."""
    from app.core.rate_limiter import rate_limit
    s = get_settings()
    return rate_limit(s.rate_limit_login)(request)


def _rate_limit_register(request: Request) -> None:
    """GH-S11-INFRA-04 · per-IP rate limit for /auth/register*."""
    from app.core.rate_limiter import rate_limit
    s = get_settings()
    return rate_limit(s.rate_limit_register)(request)


# Pydantic schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class RegisterStudentRequest(BaseModel):
    """Public student registration · GH-S2-BE-04.

    Always creates a user with role=student and school_id=None. School
    membership is granted later by a school_admin via invitation flow.
    """
    email: EmailStr
    password: str
    name: Optional[str] = None


class RegisterSchoolUserRequest(BaseModel):
    """Super-admin-only · creates a psychologist or school_admin attached
    to an existing school. GH-S2-BE-05.
    """
    email: EmailStr
    password: str
    name: Optional[str] = None
    role: UserRole = Field(..., description="Must be psychologist or school_admin")
    school_id: UUID


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: Optional[str]
    role: UserRole = UserRole.STUDENT
    school: Optional[SchoolSummary] = None
    onboarding_status: OnboardingStatus
    english_test_completed: bool = False
    english_cefr_level: Optional[str] = None
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


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
@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(_rate_limit_login)],
)
def login(
    request: Request,
    payload: LoginRequest,
    db: DBSession = Depends(get_db),
):
    """Authenticate user and return JWT token.

    GH-S11-INFRA-04 · rate-limited to ``settings.rate_limit_login`` (default 5/min).
    GH-S11 hardening · failed attempts and super_admin logins are recorded in
    ``audit_logs`` so abuse can be triaged post-hoc (S8 gap closed).
    """
    from app.services.audit_service import log_action

    user = db.query(User).filter(User.email == payload.email.lower()).first()

    def _audit(action: str, target_user, payload_extra: dict) -> None:
        try:
            log_action(
                db,
                user=target_user,
                action=action,
                resource_type="user",
                resource_id=str(target_user.id) if target_user else None,
                payload=payload_extra,
                request=request,
            )
        except Exception:
            pass  # never break login response on audit failure

    if not user or not verify_password(payload.password, user.hashed_password):
        _audit(
            "auth.login_failed",
            user,
            {
                "email": payload.email.lower(),
                "reason": "invalid_credentials",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        _audit("auth.login_failed", user, {"reason": "user_disabled"})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # GH-SUPERADMIN-EXPERIENCE · Bloque A · suspended_at gate
    # Decoupled from is_active: super_admin suspends without flipping legacy flag.
    if user.suspended_at is not None:
        _audit(
            "auth.login_failed",
            user,
            {"reason": "user_suspended", "suspended_at": user.suspended_at.isoformat()},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta fue suspendida. Contacte al administrador.",
        )

    # GH-S8 · D-017 · users from archived schools cannot log in
    if user.school_id and user.role != UserRole.SUPER_ADMIN:
        school = db.query(School).filter(School.id == user.school_id).first()
        if school and school.archived_at is not None:
            _audit(
                "auth.login_failed_archived_school",
                user,
                {"reason": "school_archived", "school_id": str(school.id)},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Su colegio está archivado. Contacte al administrador de Grasshopper.",
            )

    access_token = create_access_token(data={"sub": str(user.id)})

    # GH-SUPERADMIN-EXPERIENCE · stamp last_login_at for DAU/MAU metrics
    try:
        user.last_login_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    # GH-S11 hardening · audit super_admin logins (S8 gap closed)
    if user.role == UserRole.SUPER_ADMIN:
        _audit("auth.login_super_admin", user, {})

    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_rate_limit_register)],
)
def register(
    request: Request,
    payload: RegisterRequest,
    db: DBSession = Depends(get_db),
):
    """Register a new user (legacy public endpoint · always student role).

    Backwards-compatible wrapper that delegates to register_student. The POC
    frontend still calls /auth/register · keeping it alive avoids breaking
    the public landing flow during S2.

    GH-S11-INFRA-04 · rate-limited to ``settings.rate_limit_register`` (default 3/min).
    """
    return _register_student_internal(
        RegisterStudentRequest(
            email=payload.email,
            password=payload.password,
            name=payload.name,
        ),
        db,
    )


@router.post(
    "/register-student",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S2-BE-04 · public student registration",
    dependencies=[Depends(_rate_limit_register)],
)
def register_student(
    request: Request,
    payload: RegisterStudentRequest,
    db: DBSession = Depends(get_db),
):
    """Public endpoint · creates a student-role user without school membership.

    GH-S11-INFRA-04 · rate-limited to ``settings.rate_limit_register`` (default 3/min).
    """
    return _register_student_internal(payload, db)


def _register_student_internal(request: RegisterStudentRequest, db: DBSession) -> TokenResponse:
    """Shared implementation for student registration. Always sets role=student
    and school_id=None regardless of payload to prevent privilege escalation."""
    existing_user = db.query(User).filter(User.email == request.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=request.email.lower(),
        hashed_password=get_password_hash(request.password),
        name=request.name,
        role=UserRole.STUDENT,
        school_id=None,
        onboarding_status=OnboardingStatus.NOT_STARTED,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/register-school-user",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S2-BE-05 · super_admin creates school staff",
)
def register_school_user(
    request: RegisterSchoolUserRequest,
    db: DBSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
):
    """Creates a psychologist or school_admin attached to an existing school.

    Authorization:
    - Caller MUST be super_admin · enforced via require_role inside the function
      (kept inline to avoid circular import with auth_service which imports
      from this file).
    """
    # Inline authorization (mirrors auth_service.require_role)
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can create school staff users.",
        )

    if request.role not in (UserRole.PSYCHOLOGIST, UserRole.SCHOOL_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role must be psychologist or school_admin.",
        )

    school = db.query(School).filter(School.id == request.school_id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )

    existing_user = db.query(User).filter(User.email == request.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered.",
        )

    user = User(
        email=request.email.lower(),
        hashed_password=get_password_hash(request.password),
        name=request.name,
        role=request.role,
        school_id=school.id,
        onboarding_status=OnboardingStatus.COMPLETED,  # staff bypass onboarding
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse.model_validate(user)


class InviteStudentRequest(BaseModel):
    """School-admin invites a new student into their school · GH-S8-BE-05."""
    email: EmailStr
    password: str
    name: Optional[str] = None


@router.post(
    "/invite-student",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S8-BE-05 · school_admin invites a student into its school (seats enforced)",
)
def invite_student(
    request: InviteStudentRequest,
    db: DBSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
):
    """Creates a student attached to the caller's school.

    Caller must be school_admin (super_admin can use the regular flows).
    Enforces the school's active license: not archived, not expired, seats
    not exhausted (GH-S8-BE-05).
    """
    if current_user.role != UserRole.SCHOOL_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only school_admin can invite students.",
        )
    if not current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="School admin must be linked to a school.",
        )

    # license + seats enforcement
    from app.services.license_service import assert_can_register_student
    assert_can_register_student(db, current_user.school_id)

    existing = db.query(User).filter(User.email == request.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered.",
        )

    user = User(
        email=request.email.lower(),
        hashed_password=get_password_hash(request.password),
        name=request.name,
        role=UserRole.STUDENT,
        school_id=current_user.school_id,
        onboarding_status=OnboardingStatus.NOT_STARTED,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse.model_validate(user)


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

    # Build reset link · origin validado contra whitelist (previene phishing via
    # header injection). GH-F1-SECURITY · build_safe_url rechaza origins no
    # registrados y usa settings.frontend_base_url como fallback seguro.
    reset_link = build_safe_url(
        origin_header=req.headers.get("origin"),
        path=f"/reset-password/{reset_token}",
    )
    # Log neutro: solo user_id · NUNCA el token ni el email completo (PII / token hijack)
    logger.info("auth.forgot_password.requested user_id=%s", str(user.id))

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
